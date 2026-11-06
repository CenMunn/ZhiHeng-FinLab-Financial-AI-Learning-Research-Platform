"""D30 prepare -> predict/freeze -> independently score a development-only run."""
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from research.market.common import PROJECT, file_sha, digest, write_json
from research.filing_extraction.common import METRICS, LABELS, NAMES
from research.filing_extraction.score import score_field, error_reasons
from research.filing_development.evidence import CONFIG, build_case, candidate_options
from research.filing_development.model import SYSTEM, build_prompt, parse_field, PrefixTrie, run_predictions
from research.filing_extraction.download_model import verify_model

ROOT = PROJECT/'research/artifacts/filing-development'
CORPUS = PROJECT/'research/artifacts/filing-extraction/corpus/v2/manifest.json'
REFERENCE = PROJECT/'research/artifacts/filing-extraction/reference/v2/references.json'
MODEL = PROJECT/'research/artifacts/filing-extraction/model/989aa7980e4cf806f80c7fef2b1adb7bc71aa306/manifest.json'
BASELINE = PROJECT/'backend/data/filing-extraction/filing-eea0bd9c4721f14a19f11b8fc49245c00ca9f57347509b787f53658e0c01d3cc.json'
HUMAN = PROJECT/'docs/research/human-review/2026-11-06/manifest.json'
DESIGN = PROJECT/'docs/superpowers/specs/2026-11-06-filing-development-design.md'
METHODS = ('single_free', 'single_constrained')


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    return Path(path).resolve().relative_to(PROJECT.resolve()).as_posix()


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def verify_files(artifacts):
    allowed = [ROOT.resolve(), (PROJECT/'research/artifacts/filing-extraction').resolve(), HUMAN.parent.resolve()]
    require(isinstance(artifacts, dict) and artifacts, 'Empty source manifest')
    for name, sha in artifacts.items():
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts and ':' not in name and '\\' not in name, 'Unsafe source path')
        path = (PROJECT/name).resolve()
        require(path == BASELINE.resolve() or any(path.is_relative_to(root) and path != root for root in allowed), 'Source outside owned roots')
        require(path.is_file() and file_sha(path) == sha, 'Source missing or changed: '+name)


def source_files():
    paths = [*Path(__file__).parent.glob('*.py'), *PROJECT.joinpath('research/filing_extraction').glob('*.py'),
             PROJECT/'research/market/common.py', CONFIG, DESIGN]
    return {rel(path): file_sha(path) for path in sorted(paths)}


def project_development(corpus, project=PROJECT):
    """Skip evaluation metadata before opening page files; no labels enter cases."""
    selected = [d for d in corpus['documents'] if d.get('split') == 'development']
    require(len(selected) == 3 and {d['doc_id'] for d in selected} == {s+'-2024Q1' for s in NAMES}, 'Fixed development documents changed')
    documents = []
    for d in selected:
        require(d['period'] == '2024Q1' and d['doc_id'] == d['symbol']+'-2024Q1', 'Development period mismatch')
        path = (Path(project)/d['pages_path']).resolve()
        require(path.is_relative_to(Path(project).resolve()) and file_sha(path) == d['pages_sha256'], 'Development page text changed')
        pages = read(path)
        require(pages['pdf_sha256'] == d['pdf_sha256'] and len(pages['pages']) >= 6, 'Development PDF text binding differs')
        documents.append({**{k: d[k] for k in ('doc_id', 'symbol', 'title', 'period', 'split', 'pdf_sha256')},
                          'pages': [{'page': i+1, 'text': text} for i, text in enumerate(pages['pages'][:6])]})
    cases = [build_case(doc, metric) for doc in documents for metric in METRICS]
    return {'schema': 'filing-development-inputs-v1', 'documents': documents, 'cases': cases}


def validate_predictions(body, inputs, inputs_sha, model_sha, tokenizer=None):
    method = body['method']
    require(method in METHODS and body['inputs_sha256'] == inputs_sha and body['model_manifest_sha256'] == model_sha, 'Frozen prediction input/model mismatch')
    cases = {case['case_id']: case for case in inputs['cases']}
    require(len(body['predictions']) == 9 and {r['case_id'] for r in body['predictions']} == set(cases), 'Missing/duplicate development predictions')
    for row in body['predictions']:
        case = cases[row['case_id']]; prompt = {'system': SYSTEM, 'user': build_prompt(case)}
        require(row['method'] == method and row['doc_id'] == case['doc_id'] and row['metric'] == case['metric'], 'Prediction ownership differs')
        require(row['prompt'] == prompt and row['prompt_sha256'] == digest(prompt), 'Saved prompt differs from frozen builder')
        options = candidate_options(case)
        require(row['allowed_options_sha256'] == digest(options), 'Finite candidate identity changed')
        if row['status'] == 'ok':
            field = parse_field(row['raw_output'], case['metric'])
            require(field == row['field'], 'Saved field differs from raw output')
            if method == 'single_constrained':
                require(row['raw_output'] in options, 'Constrained output is not an exact registered option')
        elif row['status'] == 'invalid_output':
            require(row['field'] is None, 'Invalid output must not be filled by rules')
            try:
                parse_field(row['raw_output'], case['metric'])
            except ValueError:
                pass
            else:
                raise ValueError('Invalid status contradicts a valid raw field')
        else:
            require(row['status'] in ('error', 'input_too_long') and row['field'] is None, 'Unsupported prediction failure')
        if tokenizer is not None:
            chat = tokenizer.apply_chat_template([{'role': k, 'content': v} for k, v in prompt.items()], tokenize=False, add_generation_prompt=True)
            require(len(tokenizer.encode(chat)) == row['input_tokens'], 'Saved input token count differs')
            tokens = row['token_ids']
            require(len(tokens) == row['output_tokens'] and tokenizer.decode(tokens, skip_special_tokens=True) == row['raw_output'], 'Saved raw/token sequence differs')
            if method == 'single_constrained' and tokens:
                trie = PrefixTrie([tokenizer.encode(x, add_special_tokens=False) for x in options], tokenizer.eos_token_id)
                for i, token in enumerate(tokens):
                    require(token in trie.allowed(tokens[:i]), 'Token escaped the finite prefix constraint')


def preparation_artifacts(sealed_path):
    sealed_path = Path(sealed_path).resolve()
    require(sealed_path.is_relative_to(ROOT.resolve()/'sealed-evaluation'), 'Unregistered evaluation root')
    sealed, human = read(sealed_path), read(HUMAN)
    require(sealed['content_accessed'] is False and sealed['config_sha256'] == file_sha(CONFIG)
            and sealed['design_sha256'] == file_sha(DESIGN), 'Sealed evaluation preregistration differs')
    require(human['completed'] == 0 and human['item_count'] == 18 and human['status'] == 'pending_human_review', 'Blank human kit must remain unreviewed')
    artifacts = {**sealed['artifacts'], rel(sealed_path): file_sha(sealed_path), rel(HUMAN): file_sha(HUMAN)}
    for name, sha in human['artifacts'].items():
        require(Path(name).name == name, 'Unsafe human kit file')
        artifacts[rel(HUMAN.parent/name)] = sha
    verify_files(artifacts)
    return artifacts


def prepare(sealed_path, attempt):
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,40}', attempt), 'Invalid attempt')
    design = read(CONFIG); corpus = read(CORPUS)
    public = project_development(corpus)
    input_path = ROOT/'inputs'/('development-'+digest(public)+'.json'); write_json(input_path, public)
    # A preparation-only projection separates the permitted 2024 labels. Neither
    # model configuration reads this reference or the original combined file.
    reference = read(REFERENCE)
    dev_reference = {**{k: reference[k] for k in ('schema', 'status')},
                     'documents': [d for d in reference['documents'] if d['doc_id'].endswith('-2024Q1')],
                     'origin_sha256': file_sha(REFERENCE)}
    require(len(dev_reference['documents']) == 3, 'Development reference missing')
    reference_path = ROOT/'references'/('development-'+digest(dev_reference)+'.json'); write_json(reference_path, dev_reference)
    model = read(MODEL)
    require(model['model_id'] == design['model_id'] and model['revision'] == design['model_revision'], 'Model revision differs')
    require(model['files']['model.safetensors']['sha256'] == 'dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee', 'Unexpected model weights')
    artifacts = preparation_artifacts(sealed_path)
    data_artifacts = {}
    for doc in corpus['documents']:
        if doc['split'] == 'development':
            for key in ('pdf', 'pages'):
                data_artifacts[doc[key+'_path']] = doc[key+'_sha256']
    development_ids = {doc['doc_id'] for doc in public['documents']}
    data_artifacts.update({name: sha for name, sha in reference['artifacts'].items()
                           if any('/'+doc_id+'/' in name for doc_id in development_ids)})
    verify_files(data_artifacts)
    protocol = {'schema': 'filing-development-protocol-v1', 'attempt': attempt, 'design': design,
                'design_sha256': file_sha(CONFIG), 'corpus_path': rel(CORPUS), 'corpus_sha256': file_sha(CORPUS),
                'inputs_path': rel(input_path), 'inputs_sha256': file_sha(input_path),
                'reference_path': rel(reference_path), 'reference_sha256': file_sha(reference_path),
                'reference_origin_path': rel(REFERENCE), 'reference_origin_sha256': file_sha(REFERENCE),
                'baseline_path': rel(BASELINE), 'baseline_file_sha256': file_sha(BASELINE),
                'model_manifest_path': rel(MODEL), 'model_manifest_sha256': file_sha(MODEL),
                'sealed_manifest_path': rel(sealed_path), 'preparation_artifacts': artifacts,
                'data_artifacts': data_artifacts, 'sources': source_files()}
    run = ROOT/'runs'/('filingdev-'+digest(protocol)); write_json(run/'protocol.json', protocol)
    registration = run/'registration.json'
    if not registration.exists():
        write_json(registration, {'registered_at': now(), 'protocol_sha256': digest(protocol), 'references_excluded_from_model_inputs': True})
    for name, sha in protocol['sources'].items():
        raw = (PROJECT/name).read_bytes(); target = run/'source-code'/name
        require(file_sha(PROJECT/name) == sha, 'Source changed before registration')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(target.read_bytes() == raw, 'Archived source changed')
        else:
            with target.open('xb') as stream: stream.write(raw)
    for filename, raw in [('design-source.json', CONFIG.read_bytes())]:
        target = run/filename
        if target.exists(): require(target.read_bytes() == raw, 'Archived design changed')
        else:
            with target.open('xb') as stream: stream.write(raw)
    verify_run(run)
    print(json.dumps({'run_id': run.name, 'run_path': str(run), 'development_fields': 9, 'new_evaluation_opened': False}, ensure_ascii=False), flush=True)
    return run


def verify_run(run):
    run = Path(run).resolve(); require(run.is_relative_to(ROOT.resolve()/'runs'), 'Unsafe run path')
    p = read(run/'protocol.json')
    require(run.name == 'filingdev-'+digest(p) and read(run/'registration.json')['protocol_sha256'] == digest(p), 'Run registration differs')
    for pathkey, shakey in [('corpus_path', 'corpus_sha256'), ('inputs_path', 'inputs_sha256'), ('reference_path', 'reference_sha256'),
                            ('reference_origin_path', 'reference_origin_sha256'), ('baseline_path', 'baseline_file_sha256'), ('model_manifest_path', 'model_manifest_sha256')]:
        verify_files({p[pathkey]: p[shakey]})
    verify_files(p['preparation_artifacts'])
    verify_files(p['data_artifacts'])
    for name, sha in p['sources'].items():
        require(file_sha(PROJECT/name) == sha and file_sha(run/'source-code'/name) == sha, 'Frozen source changed: '+name)
    require(file_sha(run/'design-source.json') == p['design_sha256'] and file_sha(CONFIG) == p['design_sha256'], 'Frozen design changed')
    require(read(PROJECT/p['inputs_path']) == project_development(read(PROJECT/p['corpus_path'])), 'Inputs differ from original development evidence')
    return p, read(PROJECT/p['inputs_path'])


def tokenizer_for(p):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained((PROJECT/p['model_manifest_path']).parent, local_files_only=True, trust_remote_code=False)


def predict(run):
    run = Path(run); p, inputs = verify_run(run); stage = run/'frozen-predictions.json'
    if stage.exists():
        frozen = read(stage)
        for method, sha in frozen['files'].items():
            require(file_sha(run/(method+'-predictions.json')) == sha, 'Previously frozen output changed')
        return frozen
    require(not (run/'generation-progress.jsonl').exists(), 'Partial run retained; select a fresh attempt')
    run_predictions(PROJECT/p['inputs_path'], PROJECT/p['model_manifest_path'], run, p['design']['generation'])
    verify_run(run); tokenizer = tokenizer_for(p); files = {}
    for method in METHODS:
        path = run/(method+'-predictions.json')
        validate_predictions(read(path), inputs, p['inputs_sha256'], p['model_manifest_sha256'], tokenizer)
        files[method] = file_sha(path)
    frozen = {'frozen_at': now(), 'protocol_sha256': digest(p), 'files': files}
    write_json(stage, frozen); return frozen


def summarize(rows):
    summaries = []
    for method in ('baseline_rule', 'baseline_model', *METHODS):
        group = [row for row in rows if row['method'] == method]
        require(len(group) == 9, 'Fixed development denominator differs')
        summary = {'method': method, 'total': 9, 'format_valid': sum(r['status'] == 'ok' for r in group),
                   'answered': sum(r['checks']['answered'] for r in group),
                   'correct_abstentions': sum(r['checks']['correct_abstention'] for r in group),
                   'candidate_covered': None if method.startswith('baseline_') else sum(r['candidate_covered'] for r in group)}
        for check in ('numeric', 'unit', 'currency', 'period', 'scope', 'evidence', 'complete'):
            summary[check+'_correct'] = sum(r['checks'][check] for r in group)
        summaries.append(summary)
    return summaries


def model_verification_for_scoring(run, protocol):
    """Recheck full assets offline; web GET verifies this archived receipt only."""
    model_path = PROJECT/protocol['model_manifest_path']
    model = verify_model(model_path)
    require(file_sha(model_path) == protocol['model_manifest_sha256'], 'Model manifest changed before scoring')
    receipt = {'schema': 'filing-development-model-verification-v1', 'model_id': model['model_id'],
               'revision': model['revision'], 'model_manifest_sha256': protocol['model_manifest_sha256'],
               'verified_at': now(), 'stage': 'post_prediction_pre_scoring',
               'files': {name: {k: spec[k] for k in ('sha256', 'size')} for name, spec in model['files'].items()},
               'upstream_sha256': model['upstream_sha256']}
    path = Path(run)/'model-verification.json'
    if path.exists():
        old = read(path)
        require({k: v for k, v in old.items() if k != 'verified_at'} == {k: v for k, v in receipt.items() if k != 'verified_at'}, 'Archived model verification differs')
        receipt = old
    write_json(path, receipt)
    return {'receipt_path': rel(path), 'verified_at': receipt['verified_at'], 'stage': receipt['stage'],
            'current_assets_checked_on_request': False}


def publish(run):
    run = Path(run); p, inputs = verify_run(run); frozen = read(run/'frozen-predictions.json')
    require(frozen['protocol_sha256'] == digest(p) and set(frozen['files']) == set(METHODS), 'Incomplete frozen generation stage')
    predictions = {}; tokenizer = tokenizer_for(p)
    for method in METHODS:
        path = run/(method+'-predictions.json')
        require(file_sha(path) == frozen['files'][method], 'Raw output changed after freezing')
        predictions[method] = read(path)
        validate_predictions(predictions[method], inputs, p['inputs_sha256'], p['model_manifest_sha256'], tokenizer)
    verification = model_verification_for_scoring(run, p)
    # References and baseline result content are consumed for scoring only now.
    ref = read(PROJECT/p['reference_path']); refs = {d['doc_id']: {f['metric']: f for f in d['fields']} for d in ref['documents']}
    old_envelope = read(BASELINE); old = old_envelope['record']
    require(digest(old) == old_envelope['sha256'] == '4340739bbebb77de426fd2538d9848e56df4ce436c9b4fa2fe7454232611514c', 'D29 immutable baseline changed')
    rows = []
    for original in old['rows']:
        if original['split'] != 'development': continue
        rows.append({**original, 'case_id': original['doc_id']+'/'+original['metric'], 'method': 'baseline_'+original['method'],
                     'candidate_count': None, 'candidate_covered': None, 'input_tokens': None, 'output_tokens': None, 'latency_seconds': None})
    docs = {doc['doc_id']: doc for doc in inputs['documents']}
    for case in inputs['cases']:
        reference = refs[case['doc_id']][case['metric']]; doc = docs[case['doc_id']]
        covered = any(score_field(c['field'], reference, doc, case['metric'], 'ok')['complete'] for c in case['candidates'])
        for method in METHODS:
            output = next(r for r in predictions[method]['predictions'] if r['case_id'] == case['case_id'])
            checks = score_field(output['field'], reference, doc, case['metric'], output['status'])
            rows.append({'case_id': case['case_id'], 'doc_id': case['doc_id'], 'split': 'development', 'metric': case['metric'],
                         'label': LABELS[case['metric']], 'method': method, 'status': output['status'], 'prediction': output['field'],
                         'checks': checks, 'reference': reference, 'error_reasons': error_reasons(checks, output['status'], reference),
                         'candidate_count': len(case['candidates']), 'candidate_covered': covered,
                         **{k: output[k] for k in ('input_tokens', 'output_tokens', 'latency_seconds')}})
    scoring_path = run/'scored-rows.json'
    write_json(scoring_path, {'schema': 'filing-development-scoring-v1', 'protocol_sha256': digest(p),
               'prediction_sha256': frozen['files'], 'inputs_sha256': p['inputs_sha256'],
               'reference_sha256': p['reference_sha256'], 'rows': rows, 'metrics': summarize(rows)})
    corpus = read(CORPUS); artifacts = {**p['preparation_artifacts'], **p['data_artifacts']}
    for name in (p['inputs_path'], p['reference_path'], p['reference_origin_path'], p['model_manifest_path'], p['baseline_path'], p['corpus_path']):
        artifacts[name] = file_sha(PROJECT/name)
    for doc in corpus['documents']:
        if doc['split'] == 'development':
            for key in ('pdf', 'pages'): artifacts[doc[key+'_path']] = doc[key+'_sha256']
    for path in run.rglob('*'):
        if path.is_file(): artifacts[rel(path)] = file_sha(path)
    verify_files(artifacts)
    sealed = read(PROJECT/p['sealed_manifest_path']); success = sum(d['status'] == 'sealed' for d in sealed['documents'])
    record = {'schema': 'filing-development-publication-v1', 'run_id': run.name, 'created_at': now(), 'protocol': p,
              'sources': p['sources'], 'artifacts': artifacts, 'input_sha256': p['inputs_sha256'], 'reference_sha256': p['reference_sha256'],
              'prediction_sha256': frozen['files'], 'documents': [d for d in old['documents'] if d['split'] == 'development'],
              'methods': [{'id': 'baseline_rule', 'label': 'D29固定规则', 'description': '原开发记录，未重跑或修改。'},
                          {'id': 'baseline_model', 'label': 'D29整篇模型', 'description': '原三字段一次生成，格式失败保留。'},
                          {'id': 'single_free', 'label': '单字段自由JSON', 'description': '同一字段证据块，短引用，严格解析；不清洗原始输出。'},
                          {'id': 'single_constrained', 'label': '单字段候选约束', 'description': '相同证据块，前缀树限制来源候选JSON；格式由构造保证，语义仍需核对。'}],
              'metrics': summarize(rows), 'rows': rows, 'scoring_path': rel(scoring_path),
              'model_details': {**{k: predictions['single_free'][k] for k in ('model_id', 'revision', 'generation', 'runtime')}, 'verification': verification},
              'baseline': {'run_id': old['run_id'], 'record_sha256': old_envelope['sha256']},
              'new_evaluation': {'manifest_path': p['sealed_manifest_path'], 'status': 'sealed' if success == 3 else 'partial' if success else 'blocked',
                                 'content_accessed': False, 'documents': sealed['documents']},
              'human_review': {'manifest_path': rel(HUMAN), 'checklist_path': rel(HUMAN.parent/'checklist.csv'), 'guide_path': rel(HUMAN.parent/'guide.md'),
                               'item_count': 18, 'completed': 0, 'status': 'pending_human_review'},
              'limitations': ['仅2024开发检查，固定三公司9字段；同一开发集用于理解格式和验证方法，不能当新评估或公司外泛化。',
                  'D29原始结果保留；新方法增加了确定性证据检索，不能将相对D29变化完全归因于受限解码。只有两种新方法的输入一致。',
                  '有限来源候选前缀树保证结构合法；错误上期列、扣非或比率仍可能被选中，语义正确性须独立评分。',
                  '候选覆盖是评分时参考检查出的可达上限，既非模型预测成绩，也不是经过校准的置信度。',
                  '期间与合并范围来自查询约束；工业报告范围仍需后页确认。助手参考待人工审计，不能称专家金标。',
                  '三家新公司的2025Q1仅预登记和封存字节，未打开内容/标注/预测/评分；来源失败明确保留。',
                  '人工表18项均为空白待填写，审核结果另存；此轮无金融微调或付费模型API调用。',
                  '权重在离线推理前后及评分前完整校验；网页核验归档证据和该收据，不重复散列3GB权重，也不保证当前权重仍可重新运行。']}
    verify_run(run); verify_files(artifacts)
    destination = PROJECT/'backend/data/filing-development'; archive = destination/(run.name+'.json')
    if archive.exists(): record['created_at'] = read(archive)['record']['created_at']
    envelope = {'record': record, 'sha256': digest(record)}; write_json(archive, envelope)
    destination.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.development-', dir=destination)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(envelope, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, destination/'latest.json')
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(json.dumps({'run_id': run.name, 'sha256': envelope['sha256'], 'metrics': record['metrics']}, ensure_ascii=False), flush=True)
    return envelope


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest='stage', required=True)
    task = sub.add_parser('prepare'); task.add_argument('--sealed', type=Path, required=True); task.add_argument('--attempt', required=True)
    for name in ('predict', 'publish'):
        task = sub.add_parser(name); task.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    if args.stage == 'prepare': prepare(args.sealed, args.attempt)
    elif args.stage == 'predict': predict(args.run)
    else: publish(args.run)
