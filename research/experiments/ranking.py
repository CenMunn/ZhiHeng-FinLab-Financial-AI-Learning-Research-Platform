"""Standard-library experiment contracts. Prediction inputs never load gold labels."""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
from research.evaluation.audit_finqa import bm25_rank

COMMIT = '0f16e2867befa6840783e58be38c9efb9229d742'
INPUT_KEYS = {'question_id','company_id','annual_report_id','page_id','split','question',
              'candidate_scope','serialization','candidates','bm25_top20'}


def file_sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verified_file(prepared: Path, relative: str) -> Path:
    allowed = {f'{directory}/{split}.jsonl' for directory in ('inference','labels') for split in ('train','dev')} | {'splits.json'}
    if relative not in allowed:
        raise ValueError('File outside experiment allowlist')
    manifest = json.loads((prepared/'manifest.json').read_text(encoding='utf8'))
    if (manifest.get('schema_version') != 'm2-preparation-v1' or manifest.get('commit') != COMMIT
            or manifest.get('serialization') != 'finqa-header-aware-v1'
            or manifest.get('test_content_accessed') is not False
            or manifest.get('gold_added_to_inference_candidates') is not False):
        raise ValueError('Unexpected preparation identity')
    path = prepared/relative
    if not path.resolve().is_relative_to(prepared.resolve()) or file_sha(path) != manifest['outputs_sha256'].get(relative):
        raise ValueError('Prepared file hash mismatch')
    return path


def validate_input(row: dict, split: str) -> None:
    if set(row) != INPUT_KEYS:
        raise ValueError('Inference whitelist mismatch')
    if split not in ('train','dev') or row['split'] != split or row['candidate_scope'] != 'provided_page' or row['serialization'] != 'finqa-header-aware-v1':
        raise ValueError('Inference split/serialization mismatch')
    candidates, ranked = row['candidates'], row['bm25_top20']
    if (not row['question'].strip() or not isinstance(candidates,dict) or not candidates
            or not all(isinstance(k,str) and isinstance(v,str) for k,v in candidates.items())
            or len(ranked) != min(20,len(candidates)) or len(ranked) != len(set(ranked))
            or not set(ranked).issubset(candidates)):
        raise ValueError('Invalid inference candidates')


def load_inputs(prepared: Path, split: str) -> list[dict]:
    if split not in ('train','dev'):
        raise ValueError('Only train/dev may be accessed')
    path = verified_file(prepared,f'inference/{split}.jsonl')
    rows = [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
    for row in rows: validate_input(row,split)
    if len({r['question_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate question IDs')
    return rows


def load_labels(prepared: Path, split: str) -> dict[str,list[str]]:
    if split not in ('train','dev'): raise ValueError('Only train/dev labels may be accessed')
    path=verified_file(prepared,f'labels/{split}.jsonl')
    rows=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
    labels={row['question_id']: row['gold_ids'] for row in rows}
    if len(labels)!=len(rows) or any(not gold or len(gold)!=len(set(gold)) for gold in labels.values()):
        raise ValueError('Invalid labels')
    return labels


def training_pairs(rows: list[dict], labels: dict, fit_ids: set[str], negatives_per_positive: int = 3) -> list[tuple]:
    if any(row['split']!='train' for row in rows): raise ValueError('Only train rows may produce fitting pairs')
    if negatives_per_positive<1: raise ValueError('Need weak negatives')
    by_id={r['question_id']:r for r in rows}
    if not fit_ids.issubset(by_id): raise ValueError('Unknown fitting IDs')
    pairs=[]
    for qid in sorted(fit_ids):
        row=by_id[qid]; gold=set(labels[qid])
        if not gold or not gold.issubset(row['candidates']): raise ValueError('Invalid training gold')
        pairs.extend((qid,key,1.0) for key in sorted(gold))
        weak=[key for key in row['bm25_top20'] if key not in gold][:len(gold)*negatives_per_positive]
        pairs.extend((qid,key,0.0) for key in weak)
    return pairs


def rerank(row: dict, scores: list[float]) -> list[str]:
    candidates=row['bm25_top20']
    if len(scores)!=len(candidates) or not all(math.isfinite(s) for s in scores): raise ValueError('Invalid prediction scores')
    return [candidates[i] for i in sorted(range(len(scores)),key=lambda i:(-scores[i],i))]


def page_bm25(row: dict) -> list[str]:
    # M2.1 JSON is key-sorted. Restore the upstream text-then-table numeric source
    # order before resolving lexical ties; lexicographic text_10/text_2 is different.
    def source_order(key):
        kind,index=key.split('_')
        if kind not in ('text','table') or not index.isdecimal(): raise ValueError('Unknown source candidate ID')
        return (0 if kind=='text' else 1,int(index))
    candidates={key:row['candidates'][key] for key in sorted(row['candidates'],key=source_order)}
    return bm25_rank(row['question'],candidates)[:20]


def evaluate(rows: list[dict], labels: dict, predictions: dict[str,list[str]]) -> dict:
    ids={r['question_id'] for r in rows}
    if set(labels)!=ids or not set(predictions).issubset(ids): raise ValueError('Scoring ID mismatch')
    records=[]
    for row in rows:
        qid=row['question_id']; gold=set(labels[qid]); candidates=row['bm25_top20']; ranked=predictions.get(qid,[])
        if not gold or not gold.issubset(row['candidates']): raise ValueError('Invalid scoring gold')
        if len(set(ranked))!=len(ranked) or not set(ranked).issubset(candidates): raise ValueError('Prediction outside shared candidates')
        top=ranked[:5]; hits=len(gold.intersection(top))
        dcg=sum(1/math.log2(i+2) for i,key in enumerate(top) if key in gold)
        ideal=sum(1/math.log2(i+2) for i in range(min(5,len(gold))))
        records.append({'question_id':qid,'company_id':row['company_id'],'annual_report_id':row['annual_report_id'],
            'coverage_at_5':int(gold.issubset(top)), 'candidate_coverage_at_20':int(gold.issubset(candidates)),
            'recall_at_5':hits/len(gold),'hit_at_5':int(hits>0),'ndcg_at_5':dcg/ideal,'gold_count':len(gold),
            'prediction_missing':qid not in predictions})
    if not records: raise ValueError('Empty scoring set')
    summary={key:sum(r[key] for r in records)/len(records) for key in
             ('coverage_at_5','candidate_coverage_at_20','recall_at_5','hit_at_5','ndcg_at_5')}
    covered=[r for r in records if r['candidate_coverage_at_20']]
    summary.update(questions=len(records),candidate_covered_questions=len(covered),
        conditional_coverage_at_5=sum(r['coverage_at_5'] for r in covered)/len(covered) if covered else None,
        gold_over_five=sum(r['gold_count']>5 for r in records), missing_predictions=sum(r['prediction_missing'] for r in records))
    return {'summary':summary,'per_question':records}


def paired_bootstrap(left: list[dict], right: list[dict], replicates: int=2000, seed: int=20261030) -> dict:
    a={r['question_id']:r for r in left}; b={r['question_id']:r for r in right}
    if not a or a.keys()!=b.keys() or any(a[q]['company_id']!=b[q]['company_id'] for q in a):
        raise ValueError('Paired groups/IDs must match')
    groups=defaultdict(lambda:[0.0,0])
    for q in a:
        g=groups[a[q]['company_id']]; g[0]+=b[q]['coverage_at_5']-a[q]['coverage_at_5']; g[1]+=1
    values=[groups[g] for g in sorted(groups)]; rng=random.Random(seed); samples=[]
    for _ in range(replicates):
        chosen=rng.choices(values,k=len(values)); samples.append(sum(g[0] for g in chosen)/sum(g[1] for g in chosen))
    samples.sort()
    def quantile(p):
        x=(len(samples)-1)*p; low=int(x); high=min(low+1,len(samples)-1)
        return samples[low]+(samples[high]-samples[low])*(x-low)
    return {'difference':sum(g[0] for g in values)/len(a),'ci95':[quantile(.025),quantile(.975)],
            'groups':len(values),'questions':len(a),'replicates':replicates,'seed':seed,
            'group':'company_id proxy','estimand':'paired question-mean coverage difference',
            'boundary':'Development uncertainty; proxy companies are not certified independent entities.'}
