"""Evaluation-only aggregate clipping audit. Its gold flags never enter model features."""
from __future__ import annotations
import json
import os
from pathlib import Path
import statistics
import sys

PROJECT=Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path: sys.path.insert(0,str(PROJECT))
from research.experiments.ranking import load_inputs,load_labels,training_pairs
from research.training.run_ranking import configuration,write


def audit(config):
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(PROJECT/config['model'],local_files_only=True,trust_remote_code=False)
    prepared=PROJECT/config['preparation']; report={}
    for split in ('train','dev'):
        rows=load_inputs(prepared,split); labels=load_labels(prepared,split); by_id={r['question_id']:r for r in rows}
        if split=='train':
            pairs=training_pairs(rows,labels,set(by_id),config['negatives_per_positive'])
        else:
            pairs=[(r['question_id'],key,float(key in labels[r['question_id']])) for r in rows for key in r['bm25_top20']]
        lengths=[]; gold_pairs=gold_clipped=0; max_question=0
        for offset in range(0,len(pairs),256):
            batch=pairs[offset:offset+256]
            questions=[by_id[q]['question'] for q,_,_ in batch]
            evidence=[by_id[q]['candidates'][key] for q,key,_ in batch]
            result=tokenizer(questions,evidence,truncation=False,return_length=True)['length']; lengths.extend(result)
            qlength=tokenizer(questions,add_special_tokens=False,return_length=True)['length']; max_question=max(max_question,max(qlength))
            gold_pairs+=sum(label==1 for _,_,label in batch)
            gold_clipped+=sum(label==1 and n>config['max_length'] for (_,_,label),n in zip(batch,result))
        assert max_question+3<config['max_length'],'Question cannot fit without truncation'
        values=sorted(lengths)
        report[split]={'pairs':len(values),'maximum_question_tokens':max_question,'maximum_pair_tokens':max(values),
            'median_pair_tokens':statistics.median(values),'p95_pair_tokens':values[int(.95*(len(values)-1))],
            'clipped_pairs':sum(x>config['max_length'] for x in values),'annotated_positive_pairs_in_this_pool':gold_pairs,
            'clipped_annotated_positive_pairs':gold_clipped,'max_length':config['max_length'],'truncation':'only_second',
            'note':'Clipping tail tokens may remove useful details; token counts do not certify preserved financial meaning. Dev pool is BM25 top20, not injected gold.'}
    write(PROJECT/config['output']/'token-audit.json',report); print(json.dumps(report,indent=2))


if __name__=='__main__': audit(configuration(PROJECT/'research/configs/finqa-b012.json'))
