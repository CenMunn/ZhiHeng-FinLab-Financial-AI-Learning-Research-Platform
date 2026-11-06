"""Explicit local B0/B1/B2 stages. No API key, test split, or application dependency."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path: sys.path.insert(0,str(PROJECT))
from research.experiments.ranking import load_inputs, load_labels, training_pairs, evaluate, paired_bootstrap, rerank, file_sha, page_bm25, verified_file
from research.training.probe_environment import memory_info


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8'); temp.replace(path)


def configuration(path):
    config=json.loads(path.read_text(encoding='utf8'))
    if config['schema_version']!='finqa-b012-v1' or config['protocol']!='official_train_dev_development': raise ValueError('Unexpected experiment protocol')
    output=PROJECT/config['output']; output.mkdir(parents=True,exist_ok=True)
    frozen=output/'frozen-config.json'
    if frozen.exists() and json.loads(frozen.read_text(encoding='utf8'))!=config: raise ValueError('Cannot change configuration within an experiment')
    write(frozen,config)
    return config


def training_identity(config):
    prepared=PROJECT/config['preparation']; base=PROJECT/config['model']
    return {'preparation_manifest_sha256':file_sha(prepared/'manifest.json'),
        'train_input_sha256':file_sha(verified_file(prepared,'inference/train.jsonl')),
        'train_labels_sha256':file_sha(verified_file(prepared,'labels/train.jsonl')),
        'base_model_acquisition_sha256':file_sha(base/'acquisition.json')}


def verify_checkpoint(config, checkpoint):
    receipt=json.loads((checkpoint.parent/'receipt.json').read_text(encoding='utf8'))
    if receipt['config']!=config: raise ValueError('Training config mismatch')
    if receipt.get('training_identity')!=training_identity(config): raise ValueError('Training data/model provenance mismatch')
    expected=receipt.get('checkpoint_files_sha256',{})
    if set(expected)!={'model.safetensors','config.json'} or any(file_sha(checkpoint/name)!=value for name,value in expected.items()):
        raise ValueError('Training checkpoint files hash mismatch')
    return True


def model_stack(config, checkpoint=None):
    os.environ.update(TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',CUBLAS_WORKSPACE_CONFIG=':4096:8')
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    torch.set_num_threads(2)
    if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable; no silent CPU substitution')
    if not torch.cuda.is_bf16_supported(): raise RuntimeError('Configured bf16 is not supported')
    model_root=PROJECT/config['model']
    if checkpoint: verify_checkpoint(config,checkpoint)
    acquisition=json.loads((model_root/'acquisition.json').read_text(encoding='utf8'))
    if acquisition['revision']!=config['revision'] or acquisition['model']!=config['model_id']: raise ValueError('Model identity mismatch')
    for name, expected in acquisition['files'].items():
        path=model_root/name
        if not path.resolve().is_relative_to(model_root.resolve()) or file_sha(path)!=expected: raise ValueError('Model file hash mismatch')
    tokenizer=AutoTokenizer.from_pretrained(model_root,local_files_only=True,trust_remote_code=False)
    model=AutoModelForSequenceClassification.from_pretrained(checkpoint or model_root,local_files_only=True,trust_remote_code=False,use_safetensors=True,attn_implementation='eager').to('cuda')
    if model.config.num_labels!=1: raise ValueError('Reranker requires a single logit')
    return torch,tokenizer,model


def encode(tokenizer, pairs, config):
    return tokenizer([p[0] for p in pairs],[p[1] for p in pairs],padding=True,truncation='only_second',max_length=config['max_length'],return_tensors='pt').to('cuda')


def logits_loss(torch, model, batch, labels):
    logits=model(**batch).logits.reshape(-1)
    return torch.nn.functional.binary_cross_entropy_with_logits(logits.float(),labels.float(),reduction='sum')


def pairs_and_rows(config):
    prepared=PROJECT/config['preparation']; rows=load_inputs(prepared,'train'); labels=load_labels(prepared,'train')
    pairs=training_pairs(rows,labels,{r['question_id'] for r in rows},config['negatives_per_positive'])
    return {r['question_id']:r for r in rows}, pairs


def texts_for(pairs, rows):
    return [(rows[q]['question'],rows[q]['candidates'][key]) for q,key,_ in pairs]


def model_smoke(config):
    output=PROJECT/config['output']; torch,tokenizer,model=model_stack(config)
    torch.manual_seed(42); torch.cuda.manual_seed_all(42)
    rows,pairs=pairs_and_rows(config)
    manifest=json.loads((PROJECT/config['preparation']/'manifest.json').read_text(encoding='utf8'))
    pilot=set(manifest['fixed_pilot_question_ids']['train'])
    qid=next(q for q in sorted(pilot) if any(p[0]==q and p[2]==0 for p in pairs))
    selected=[next(p for p in pairs if p[0]==qid and p[2]==1),next(p for p in pairs if p[0]==qid and p[2]==0)]
    batch=encode(tokenizer,texts_for(selected,rows),config); labels=torch.tensor([1.,0.],device='cuda')
    torch.cuda.reset_peak_memory_stats(); model.eval()
    before=next(model.parameters()).detach().clone(); initial=(logits_loss(torch,model,batch,labels)/2).item()
    loss=logits_loss(torch,model,batch,labels)/2; loss.backward()
    grads=[p.grad for p in model.parameters() if p.grad is not None]
    finite=all(bool(torch.isfinite(g).all()) for g in grads)
    grad_norm=math.sqrt(sum(g.float().square().sum().item() for g in grads))
    assert finite and grad_norm>0
    optimizer=torch.optim.AdamW(model.parameters(),lr=1e-4,weight_decay=.01)
    optimizer.step(); model.zero_grad(set_to_none=True)
    changed=not torch.equal(before,next(model.parameters()).detach()); del before
    with torch.autocast('cuda',dtype=torch.bfloat16): mixed=logits_loss(torch,model,batch,labels)/2
    mixed.backward(); assert all(bool(torch.isfinite(p.grad).all()) for p in model.parameters() if p.grad is not None)
    model.zero_grad(set_to_none=True)
    started=time.perf_counter(); losses=[]
    for _ in range(24):
        with torch.autocast('cuda',dtype=torch.bfloat16): loss=logits_loss(torch,model,batch,labels)/2
        loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
        optimizer.step(); model.zero_grad(set_to_none=True); losses.append(loss.item())
    torch.cuda.synchronize(); final=(logits_loss(torch,model,batch,labels)/2).item()
    assert changed and math.isfinite(final) and final<initial*.8,(initial,final)
    result={'status':'passed','torch':torch.__version__,'cuda':torch.version.cuda,'device':torch.cuda.get_device_name(0),
        'capability':list(torch.cuda.get_device_capability(0)),'architectures':torch.cuda.get_arch_list(),
        'bf16_supported':torch.cuda.is_bf16_supported(),'parameters':sum(p.numel() for p in model.parameters()),
        'batch':2,'sequence_length':list(batch['input_ids'].shape),'loss_initial':initial,'loss_final':final,
        'fp32_finite_backward':finite,'bf16_finite_backward':True,'grad_l2_norm':grad_norm,'parameters_changed':changed,
        'overfit_updates':25,'overfit_losses':losses,'seconds_24_updates':time.perf_counter()-started,
        'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved(),
        'host_memory':memory_info(),'question_id':qid,'saved_or_reused_smoke_weights':False,
        'boundary':'Compute/optimization check on one weakly labelled batch, not a model quality result.'}
    write(output/'model-smoke.json',result); print(json.dumps(result,indent=2),flush=True)


def baseline(config):
    prepared=PROJECT/config['preparation']; output=PROJECT/config['output']
    rows=load_inputs(prepared,'dev')
    predictions={}; latencies=[]; started=time.perf_counter()
    for row in rows:
        start=time.perf_counter(); ranked=page_bm25(row)
        if ranked!=row['bm25_top20']: raise ValueError('BM25 differs from frozen candidate pool')
        predictions[row['question_id']]=ranked; latencies.append((time.perf_counter()-start)*1000)
    write(output/'b0-predictions.json',{'method':'B0_BM25','predictions':predictions,'seconds':time.perf_counter()-started,
        'candidate_scope':'provided_page','gold_used_for_prediction':False,
        'question_latency_ms':{'mean':statistics.mean(latencies),'median':statistics.median(latencies),'p95':sorted(latencies)[int(.95*(len(latencies)-1))]},
        'preparation_manifest_sha256':file_sha(prepared/'manifest.json'),'config':config,
        'note':'Actual CPU BM25 recomputation from source-only page candidates; IO excluded.'})
    print('B0 predictions:',len(predictions),flush=True)


def predict(config, checkpoint=None, method='b1'):
    rows=load_inputs(PROJECT/config['preparation'],'dev'); torch,tokenizer,model=model_stack(config,checkpoint)
    model.eval(); predictions={}; latencies=[]; scores_out={}; lengths={'pairs':0,'truncated_pairs':0,'max_untruncated_tokens':0}
    # Warmup is explicit and not included in steady-state question latency.
    first=rows[0]; warm=encode(tokenizer,[(first['question'],first['candidates'][first['bm25_top20'][0]])],config)
    with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16): model(**warm)
    torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats(); started=time.perf_counter()
    for index,row in enumerate(rows):
        torch.cuda.synchronize(); start=time.perf_counter(); texts=[(row['question'],row['candidates'][key]) for key in row['bm25_top20']]; scores=[]
        # Source-only length audit; no gold labels are loaded by this stage.
        full=tokenizer([p[0] for p in texts],[p[1] for p in texts],truncation=False,return_length=True)
        n=full['length']; lengths['pairs']+=len(n); lengths['truncated_pairs']+=sum(x>config['max_length'] for x in n); lengths['max_untruncated_tokens']=max(lengths['max_untruncated_tokens'],max(n))
        for offset in range(0,len(texts),config['inference_batch']):
            batch=encode(tokenizer,texts[offset:offset+config['inference_batch']],config)
            with torch.inference_mode(),torch.autocast('cuda',dtype=torch.bfloat16): values=model(**batch).logits.float().reshape(-1).tolist()
            scores.extend(values)
        predictions[row['question_id']]=rerank(row,scores); scores_out[row['question_id']]=scores
        torch.cuda.synchronize(); latencies.append((time.perf_counter()-start)*1000)
        if (index+1)%100==0: print(f'{method}: {index+1}/{len(rows)} questions, {time.perf_counter()-started:.1f}s',flush=True)
    result={'method':method,'predictions':predictions,'raw_scores_in_bm25_order':scores_out,'gold_used_for_prediction':False,
        'config':config,'preparation_manifest_sha256':file_sha(PROJECT/config['preparation']/'manifest.json'),
        'base_model_acquisition_sha256':file_sha(PROJECT/config['model']/'acquisition.json'),
        'training_receipt':json.loads((checkpoint.parent/'receipt.json').read_text(encoding='utf8')) if checkpoint else None,
        'seconds':time.perf_counter()-started,'question_latency_ms':{'mean':statistics.mean(latencies),'median':statistics.median(latencies),'p95':sorted(latencies)[int(.95*(len(latencies)-1))]},
        'length_audit':lengths,'checkpoint':str(checkpoint) if checkpoint else config['revision'],
        'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()}
    write(PROJECT/config['output']/f'{method}-predictions.json',result)
    print(method,'prediction complete',result['seconds'],flush=True)


def train(config,seed):
    if seed not in config['seeds']: raise ValueError('Seed not frozen in configuration')
    output=PROJECT/config['output']/f'b2-seed-{seed}'
    if output.exists(): raise ValueError('Refuse to overwrite an existing training run')
    identity=training_identity(config)
    rows,pairs=pairs_and_rows(config); torch,tokenizer,model=model_stack(config)
    if training_identity(config)!=identity: raise ValueError('Data/model provenance changed during loading')
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed); random.seed(seed)
    torch.use_deterministic_algorithms(True)
    optimizer=torch.optim.AdamW(model.parameters(),lr=config['learning_rate'],weight_decay=config['weight_decay'])
    effective=config['micro_batch']*config['gradient_accumulation']; steps=math.ceil(len(pairs)/effective)*config['epochs']; warmup=max(1,int(steps*config['warmup_fraction']))
    output.mkdir(); log=(output/'training.jsonl').open('w',encoding='utf8'); started=time.perf_counter(); step=0
    lengths={'positive_pairs':sum(p[2]==1 for p in pairs),'weak_negative_pairs':sum(p[2]==0 for p in pairs),'pairs':len(pairs),'truncated_pairs':0,'truncated_positive_pairs':0}
    model.train(); torch.cuda.reset_peak_memory_stats(); rng=random.Random(seed)
    for epoch in range(config['epochs']):
        order=list(range(len(pairs))); rng.shuffle(order)
        for offset in range(0,len(order),effective):
            window=[pairs[i] for i in order[offset:offset+effective]]; optimizer.zero_grad(set_to_none=True); loss_total=0.0
            for begin in range(0,len(window),config['micro_batch']):
                group=window[begin:begin+config['micro_batch']]; texts=texts_for(group,rows)
                full=tokenizer([p[0] for p in texts],[p[1] for p in texts],truncation=False,return_length=True)['length']
                lengths['truncated_pairs']+=sum(n>config['max_length'] for n in full)
                lengths['truncated_positive_pairs']+=sum(n>config['max_length'] and p[2]==1 for n,p in zip(full,group))
                batch=encode(tokenizer,texts,config); targets=torch.tensor([p[2] for p in group],device='cuda')
                with torch.autocast('cuda',dtype=torch.bfloat16): raw_loss=logits_loss(torch,model,batch,targets)
                if not bool(torch.isfinite(raw_loss)): raise RuntimeError('Non-finite training loss')
                (raw_loss/len(window)).backward(); loss_total+=raw_loss.item()
            norm=torch.nn.utils.clip_grad_norm_(model.parameters(),config['clip_grad_norm'],error_if_nonfinite=True)
            multiplier=min((step+1)/warmup,max(0.,(steps-step)/(steps-warmup)))
            for group in optimizer.param_groups: group['lr']=config['learning_rate']*multiplier
            optimizer.step(); step+=1
            entry={'step':step,'epoch':epoch+1,'mean_bce':loss_total/len(window),'pairs':len(window),'grad_norm_before_clip':norm.item(),'learning_rate':optimizer.param_groups[0]['lr']}
            log.write(json.dumps(entry)+'\n')
            if step%100==0: log.flush(); print(f'seed {seed}: {step}/{steps} updates, loss {entry["mean_bce"]:.4f}, {time.perf_counter()-started:.1f}s',flush=True)
    log.close(); torch.cuda.synchronize()
    if training_identity(config)!=identity: raise ValueError('Data/model provenance changed during training')
    checkpoint=output/'checkpoint'; model.save_pretrained(checkpoint,safe_serialization=True); tokenizer.save_pretrained(checkpoint)
    receipt={'status':'completed','config':config,'seed':seed,'optimizer_updates':step,'training_questions':len(rows),'epochs':config['epochs'],
        'training_identity':identity,'training_code_sha256':file_sha(Path(__file__)),
        'ranking_code_sha256':file_sha(PROJECT/'research/experiments/ranking.py'),
        'seconds':time.perf_counter()-started,'counts_and_truncation':lengths,'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
        'peak_reserved_bytes':torch.cuda.max_memory_reserved(),'host_memory':memory_info(),'model_revision':config['revision'],
        'dev_labels_read_during_training':False,'checkpoint_selection':config['checkpoint_selection'],
        'checkpoint_sha256':file_sha(checkpoint/'model.safetensors'),
        'checkpoint_files_sha256':{name:file_sha(checkpoint/name) for name in ('model.safetensors','config.json')}}
    write(output/'receipt.json',receipt); print(json.dumps(receipt,indent=2),flush=True)


def summarize(config):
    output=PROJECT/config['output']; prepared=PROJECT/config['preparation']; rows=load_inputs(prepared,'dev'); labels=load_labels(prepared,'dev')
    methods=['b0','b1']+[f'b2-seed-{seed}' for seed in config['seeds']]; reports={}; prediction_hashes={}
    for name in methods:
        path=output/f'{name}-predictions.json'; prediction=json.loads(path.read_text(encoding='utf8')); prediction_hashes[name]=file_sha(path)
        if prediction['config']!=config or prediction['preparation_manifest_sha256']!=file_sha(prepared/'manifest.json'):
            raise ValueError('Prediction configuration/data provenance mismatch')
        if name!='b0' and prediction['base_model_acquisition_sha256']!=file_sha(PROJECT/config['model']/'acquisition.json'):
            raise ValueError('Prediction base model provenance mismatch')
        if name.startswith('b2-') and prediction['training_receipt']['training_identity']!=training_identity(config):
            raise ValueError('Prediction training provenance mismatch')
        reports[name]=evaluate(rows,labels,prediction['predictions']); write(output/f'{name}-metrics.json',reports[name])
    comparisons={f'{name}_minus_b1':paired_bootstrap(reports['b1']['per_question'],reports[name]['per_question']) for name in methods if name!='b1'}
    seed_scores=[reports[f'b2-seed-{s}']['summary']['coverage_at_5'] for s in config['seeds']]
    train_rows=load_inputs(prepared,'train')
    train_companies={r['company_id'] for r in train_rows}; dev_companies={r['company_id'] for r in rows}
    train_reports={r['annual_report_id'] for r in train_rows}; dev_reports={r['annual_report_id'] for r in rows}
    report={'schema_version':'finqa-b012-results-v1','recorded_at':datetime.now(timezone.utc).isoformat(),
        'config':config,'config_sha256':file_sha(output/'frozen-config.json'),'preparation_manifest_sha256':file_sha(prepared/'manifest.json'),
        'prediction_sha256':prediction_hashes,'methods':{name:r['summary'] for name,r in reports.items()},'paired_company_bootstrap':comparisons,
        'group_diagnostics':{'train_companies':len(train_companies),'dev_companies':len(dev_companies),'overlap_company_proxies':len(train_companies&dev_companies),
            'overlap_company_year_proxies':len(train_reports&dev_reports),'boundary':'Proxies from IDs, not certified entity/report-version identities. Company-disjoint diagnostic not run in this official protocol.'},
        'b2_seed_variation':{'mean':statistics.mean(seed_scores),'sample_sd':statistics.stdev(seed_scores),'min':min(seed_scores),'max':max(seed_scores)},
        'claim_boundary':'Official development split, not final test or independent-company validation. Weak negatives may contain false negatives. No B3/Chinese production replacement.'}
    write(output/'results.json',report); print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('stage',choices=['bm25','smoke','pretrained','train','predict','summarize'])
    parser.add_argument('--config',type=Path,default=PROJECT/'research/configs/finqa-b012.json'); parser.add_argument('--seed',type=int)
    args=parser.parse_args(); config=configuration(args.config)
    if args.stage=='bm25': baseline(config)
    elif args.stage=='smoke': model_smoke(config)
    elif args.stage=='pretrained': predict(config)
    elif args.stage=='train': train(config,args.seed)
    elif args.stage=='predict': predict(config,PROJECT/config['output']/f'b2-seed-{args.seed}'/'checkpoint',f'b2-seed-{args.seed}')
    else: summarize(config)
