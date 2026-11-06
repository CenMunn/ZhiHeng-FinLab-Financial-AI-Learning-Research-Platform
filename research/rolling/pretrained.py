"""Frozen time-series representations and supervised readout, not zero-shot returns."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
from pathlib import Path
import hashlib,json,time
import numpy as np
import torch
from safetensors.torch import save_file
from chronos import ChronosPipeline
from chronos.chronos import ChronosConfig,ChronosModel
from transformers import AutoConfig,AutoModelForSeq2SeqLM
from research.market.models import ridge_fit,ridge_predict
from research.market.runner import seed_all
from research.rolling.acquire import MODEL,acquire
from research.market.common import file_sha,write_json,digest


def encoder(random_control=False):
    acquire();seed_all(42)
    if random_control:
        config=AutoConfig.from_pretrained(str(MODEL),local_files_only=True,trust_remote_code=False)
        inner=AutoModelForSeq2SeqLM.from_config(config,trust_remote_code=False,attn_implementation='eager').cuda()
        cc=ChronosConfig(**config.chronos_config)
        pipeline=ChronosPipeline(cc.create_tokenizer(),ChronosModel(cc,inner))
    else:pipeline=ChronosPipeline.from_pretrained(str(MODEL),device_map='cuda',torch_dtype=torch.float32,local_files_only=True,trust_remote_code=False,use_safetensors=True,attn_implementation='eager')
    pipeline.model.model.eval()
    for p in pipeline.model.model.parameters():p.requires_grad_(False)
    return pipeline


def state_sha(pipeline):
    h=hashlib.sha256()
    for name,p in pipeline.model.model.named_parameters():h.update(name.encode());h.update(p.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def embed(pipeline,x,batch=32):
    result=[];x=np.asarray(x,dtype=np.float32)
    if x.ndim!=2 or not np.isfinite(x).all():raise ValueError('编码器仅接收有限的已知历史窗口')
    for start in range(0,len(x),batch):
        context=torch.tensor(x[start:start+batch],dtype=torch.float32)
        vectors,scale=pipeline.embed(context)
        # All contexts have 60 finite observations. Exclude the appended EOS.
        pooled=vectors[:,:x.shape[1]].mean(dim=1).numpy().astype(np.float64)
        result.append(np.c_[pooled,np.log1p(scale.cpu().numpy().reshape(-1))])
    features=np.concatenate(result)
    if not np.isfinite(features).all():raise ValueError('预训练嵌入非有限')
    return features


def readout(train_x,train_y,predict_x,alpha=10):
    x=np.asarray(train_x);z=np.asarray(predict_x);y=np.asarray(train_y,dtype=np.float64)
    mean=x.mean(axis=0);std=x.std(axis=0);std[std<1e-10]=1.
    ym=float(y.mean());ys=float(y.std()) or 1.
    model=ridge_fit((x-mean)/std,(y-ym)/ys,alpha)
    prediction=ridge_predict(model,(z-mean)/std)*ys+ym
    return prediction,{'x_mean':mean.tolist(),'x_std':std.tolist(),'y_mean':ym,'y_std':ys,'ridge':model,'fit_rows':len(y)}


def cache(root,contexts):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);result={}
    contexts=np.asarray(contexts,dtype=np.float32);context_sha=hashlib.sha256(contexts.tobytes()+str(contexts.shape).encode()).hexdigest()
    acquisition=acquire()
    for kind in ('chronos','random_encoder'):
        encoder_identity=digest({'kind':kind,'revision':acquisition['revision'],'files':{k:v['sha256'] for k,v in acquisition['files'].items()},
            'seed':42,'context_width':contexts.shape[1],'pooling':'observed-token mean excluding EOS + log1p scale','dtype':'float32'})
        file=root/(kind+'.npz');meta=root/(kind+'.json')
        if file.exists() and meta.exists():
            receipt=json.loads(meta.read_text('utf8'))
            if receipt['sha256']!=file_sha(file) or receipt.get('context_sha256')!=context_sha or receipt.get('encoder_identity_sha256')!=encoder_identity:raise ValueError('嵌入缓存、输入或编码器身份已变化')
            if kind=='random_encoder' and (not (root/'random-encoder.safetensors').is_file() or file_sha(root/'random-encoder.safetensors')!=receipt.get('random_weights_sha256')):raise ValueError('随机控制权重缺失或变化')
            result[kind]=np.load(file,allow_pickle=False)['features'];continue
        p=encoder(kind=='random_encoder');before=state_sha(p);start=time.perf_counter();features=embed(p,contexts)
        if state_sha(p)!=before:raise ValueError('冻结编码器权重被更新')
        if file.exists():raise ValueError('缓存不完整，不能覆盖')
        np.savez_compressed(file,features=features)
        if kind=='random_encoder':
            weights=root/'random-encoder.safetensors'
            if weights.exists():raise ValueError('拒绝覆盖随机控制权重')
            save_file({k:v.detach().cpu().clone().contiguous() for k,v in p.model.model.state_dict().items()},str(weights))
        receipt={'kind':kind,'sha256':file_sha(file),'context_sha256':context_sha,'encoder_identity_sha256':encoder_identity,'random_weights_sha256':file_sha(root/'random-encoder.safetensors') if kind=='random_encoder' else None,'rows':len(features),'width':features.shape[1],'state_sha256':before,'frozen_parameters':sum(x.numel() for x in p.model.model.parameters()),
            'trainable_base_parameters':sum(x.numel() for x in p.model.model.parameters() if x.requires_grad),'elapsed_seconds':time.perf_counter()-start,
            'context_only':True,'pooling':'mean of observed tokens, excludes EOS; append log1p(mean absolute context scale)','dtype':'float32','device':torch.cuda.get_device_name(0)}
        write_json(meta,receipt);result[kind]=features;print(json.dumps({'encoder':kind,**receipt},ensure_ascii=False),flush=True)
        del p;torch.cuda.empty_cache()
    return result


if __name__=='__main__':
    p=encoder();x=np.array([[.01,-.01,.02,0.]*15,[.02,0.,-.01,.03]*15],dtype=np.float32)
    before=state_sha(p);a=embed(p,x,batch=2);b=embed(p,x,batch=1)
    assert np.allclose(a,b,atol=1e-5,rtol=1e-5) and state_sha(p)==before
    print(json.dumps({'smoke':'passed','shape':list(a.shape),'base_frozen':True,'parameter_count':sum(v.numel() for v in p.model.model.parameters())}))
