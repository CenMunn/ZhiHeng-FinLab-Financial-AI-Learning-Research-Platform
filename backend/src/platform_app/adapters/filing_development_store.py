"""Read-only development publication. No model, research import, fetch or writes."""
import hashlib
import csv
import io
import json
import math
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath

from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash

METHODS = ('baseline_rule', 'baseline_model', 'single_free', 'single_constrained')
METRICS = ('revenue', 'net_profit_parent', 'operating_cashflow')
CHECKS = ('numeric', 'unit', 'currency', 'period', 'scope', 'evidence', 'complete', 'answered', 'correct_abstention')
BASELINE_PATH = 'backend/data/filing-extraction/filing-eea0bd9c4721f14a19f11b8fc49245c00ca9f57347509b787f53658e0c01d3cc.json'
BASELINE_RECORD_SHA256 = '4340739bbebb77de426fd2538d9848e56df4ce436c9b4fa2fe7454232611514c'
EVIDENCE_ROOTS = ('research/artifacts/filing-development', 'research/artifacts/filing-extraction', 'docs/research/human-review')
SAFE_SOURCE_SUFFIXES = {'.py', '.json', '.md', '.txt', '.ts', '.tsx', '.yaml', '.yml', '.toml', '.lock'}
REVIEW_COLUMNS = {'case_id','doc_id','company','metric','source_url','local_pdf','manual_value','manual_unit','manual_currency','manual_period','manual_scope','value_page','header_pages','quote','status','reviewer','reviewed_at','notes'}
REVIEW_BLANKS = ('manual_value','manual_unit','manual_currency','manual_period','manual_scope','value_page','header_pages','quote','reviewer','reviewed_at','notes')
GENERATION = dict(max_input_tokens=4096, max_new_tokens=384, dtype='bfloat16', do_sample=False, seed=0, batch_size=1)


def require(value):
    if not value:
        raise ValueError('Invalid filing development publication')


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def strings(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def count(value):
    return type(value) is int and value >= 0


def financial_fields(value):
    if value['value'] is not None:
        require(isinstance(value['value'], str) and re.fullmatch(r'-?\d+(\.\d+)?', value['value']) and Decimal(value['value']).is_finite())
    require(value['page'] is None or (type(value['page']) is int and value['page'] > 0))
    require(all(value[key] is None or isinstance(value[key], str) for key in ('unit', 'currency', 'period', 'scope', 'quote')))


def value_record(value, metric):
    require(isinstance(value, dict) and set(value) == {'metric', 'value', 'unit', 'currency', 'period', 'scope', 'page', 'quote'})
    require(value['metric'] == metric)
    financial_fields(value)


def reference_variant(value):
    # D29 reference variants are preserved verbatim, including later-page evidence.
    require(isinstance(value, dict) and set(value) == {'value', 'unit', 'currency', 'period', 'scope', 'page', 'quote', 'unit_evidence_pages', 'scope_evidence_pages'})
    financial_fields(value)
    for key in ('unit_evidence_pages', 'scope_evidence_pages'):
        pages = value[key]
        require(isinstance(pages, list) and all(type(page) is int and page > 0 for page in pages) and len(set(pages)) == len(pages))


def strict_output(raw, metric):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result); result[key] = value
        return result
    require(isinstance(raw, str))
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    value_record(value, metric)
    for key, allowed in (('unit', ('元', '万元', '百万元', '亿元')), ('currency', ('CNY',)), ('scope', ('consolidated', 'parent'))):
        require(value[key] is None or value[key] in allowed)
    require(value['period'] is None or re.fullmatch(r'20\d{2}Q[1-4]', value['period']))
    require(value['page'] is None or value['page'] <= 6)
    require(value['quote'] is None or (value['quote'].strip() and len(value['quote']) <= 160))
    return value


class FilingDevelopmentStore:
    def __init__(self, folder, project):
        self.folder, self.project = Path(folder), Path(project).resolve()

    def _path(self, name, *, artifact):
        require(isinstance(name, str) and name and '\\' not in name and ':' not in name)
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts and relative.as_posix() == name)
        require(not any(part.startswith('.') for part in relative.parts))
        path = (self.project / name).resolve()
        require(path != self.project and path.is_relative_to(self.project))
        if artifact:
            require(name == BASELINE_PATH or any(path != (self.project / root).resolve() and path.is_relative_to((self.project / root).resolve()) for root in EVIDENCE_ROOTS))
        else:
            require(relative.suffix in SAFE_SOURCE_SUFFIXES and not name.startswith(('backend/data/', 'research/artifacts/', '.local/')))
        return path

    def _files(self, registered, *, artifact):
        require(isinstance(registered, dict) and registered)
        missing = []
        for name, sha in registered.items():
            require(valid_hash(sha)); path = self._path(name, artifact=artifact)
            if not path.exists():
                missing.append(name); continue
            require(path.is_file())
            with path.open('rb') as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == sha)
        return missing

    def _artifact_json(self, name, artifacts):
        require(name in artifacts)
        path = self._path(name, artifact=True)
        if not path.exists():
            return None
        raw = path.read_bytes(); require(hashlib.sha256(raw).hexdigest() == artifacts[name])
        return json.loads(raw)

    def _baseline(self, r):
        protocol = r['protocol']; require(protocol['baseline_path'] == BASELINE_PATH)
        require(valid_hash(protocol['baseline_file_sha256']) and r['artifacts'].get(BASELINE_PATH) == protocol['baseline_file_sha256'])
        baseline = r['baseline']; require(valid_hash(baseline['record_sha256']) and isinstance(baseline['run_id'], str))
        require(baseline['record_sha256'] == BASELINE_RECORD_SHA256 and baseline['run_id'] == PurePosixPath(BASELINE_PATH).stem)
        body = self._artifact_json(BASELINE_PATH, r['artifacts'])
        if body is None:
            return
        old = body['record']; require(stable_hash(old) == body['sha256'] == baseline['record_sha256'])
        require(old['schema'] == 'filing-extraction-publication-v1' and old['run_id'] == baseline['run_id'])
        old_docs = {d['doc_id']: d for d in old['documents'] if d['split'] == 'development'}
        for doc in r['documents']:
            original = old_docs[doc['doc_id']]
            require(all(doc[k] == original[k] for k in ('doc_id', 'symbol', 'name', 'period', 'split', 'pdf_url', 'input_pages')))
        old_rows = {(row['doc_id'], row['metric'], row['method']): row for row in old['rows'] if row['split'] == 'development'}
        for row in r['rows']:
            original = old_rows[(row['doc_id'], row['metric'], 'rule')]
            require(row['reference'] == original['reference'])
            if row['method'].startswith('baseline_'):
                original = old_rows[(row['doc_id'], row['metric'], row['method'].replace('baseline_', ''))]
                require(all(row[k] == original[k] for k in ('status', 'prediction', 'checks', 'error_reasons')))

    def _prediction_rows(self, r):
        run = 'research/artifacts/filing-development/runs/'+r['run_id']
        for method in METHODS[2:]:
            name = run+'/'+method+'-predictions.json'
            require(r['artifacts'].get(name) == r['prediction_sha256'][method])
            body = self._artifact_json(name, r['artifacts'])
            if body is None:
                continue
            require(body['schema'] == 'filing-development-predictions-v1' and body['method'] == method)
            require(body['inputs_sha256'] == r['input_sha256'] and body['model_manifest_sha256'] == r['protocol']['model_manifest_sha256'])
            require(all(body[key] == r['model_details'][key] for key in ('model_id', 'revision', 'generation', 'runtime')))
            published = {row['case_id']: row for row in r['rows'] if row['method'] == method}
            outputs = body['predictions']; require(isinstance(outputs, list) and len(outputs) == 9 and {row['case_id'] for row in outputs} == set(published))
            for output in outputs:
                row = published[output['case_id']]
                require(all(output[key] == row[key] for key in ('case_id', 'doc_id', 'metric', 'method', 'status', 'input_tokens', 'output_tokens', 'latency_seconds', 'candidate_count')))
                require(output['field'] == row['prediction'])
                require(isinstance(output['token_ids'], list) and all(type(token) is int and token >= 0 for token in output['token_ids']) and len(output['token_ids']) == row['output_tokens'])
                if row['status'] == 'ok':
                    require(strict_output(output['raw_output'], row['metric']) == output['field'])
                elif row['status'] == 'invalid_output':
                    try:
                        strict_output(output['raw_output'], row['metric'])
                    except (ValueError, TypeError):
                        pass
                    else:
                        require(False)

    def _scoring(self, r):
        name = 'research/artifacts/filing-development/runs/'+r['run_id']+'/scored-rows.json'
        require(r['scoring_path'] == name)
        body = self._artifact_json(name, r['artifacts'])
        if body is None:
            return
        require(body['schema'] == 'filing-development-scoring-v1' and body['protocol_sha256'] == stable_hash(r['protocol']))
        require(body['prediction_sha256'] == r['prediction_sha256'] and body['inputs_sha256'] == r['input_sha256'] and body['reference_sha256'] == r['reference_sha256'])
        require(stable_hash(body['rows']) == stable_hash(r['rows']) and stable_hash(body['metrics']) == stable_hash(r['metrics']))

    def _model_verification(self, r):
        model = r['model_details']; verification = model['verification']
        name = 'research/artifacts/filing-development/runs/'+r['run_id']+'/model-verification.json'
        require(verification['receipt_path'] == name and verification['stage'] == 'post_prediction_pre_scoring' and verification['current_assets_checked_on_request'] is False)
        verified_at = datetime.fromisoformat(verification['verified_at'])
        require(verified_at.tzinfo is not None and verified_at <= datetime.fromisoformat(r['created_at']))
        manifest_name = r['protocol']['model_manifest_path']
        require(r['artifacts'].get(manifest_name) == r['protocol']['model_manifest_sha256'])
        manifest = self._artifact_json(manifest_name, r['artifacts'])
        body = self._artifact_json(name, r['artifacts'])
        if body is None:
            return
        require(body['schema'] == 'filing-development-model-verification-v1' and body['model_id'] == model['model_id'] and body['revision'] == model['revision'])
        require(body['model_manifest_sha256'] == r['protocol']['model_manifest_sha256'] and body['verified_at'] == verification['verified_at'] and body['stage'] == verification['stage'])
        if manifest is not None:
            require(manifest['model_id'] == model['model_id'] and manifest['revision'] == model['revision'])
            files = manifest['files']; require(isinstance(files, dict) and len(files) == 9)
            for filename, metadata in files.items():
                require(isinstance(filename, str) and PurePosixPath(filename).name == filename and not filename.startswith('.') and '\\' not in filename and ':' not in filename)
                require(valid_hash(metadata['sha256']) and type(metadata['size']) is int and metadata['size'] > 0)
            expected = {filename: {'sha256': metadata['sha256'], 'size': metadata['size']} for filename, metadata in files.items()}
            require(stable_hash(body['files']) == stable_hash(expected))
        # Receipt and manifest are archive evidence. Do not open the multi-GB weights here.

    def _preparation(self, r):
        sealed = r['new_evaluation']; require(sealed['status'] in ('sealed', 'partial', 'blocked') and sealed['content_accessed'] is False)
        require(isinstance(sealed['documents'], list) and len(sealed['documents']) == 3)
        require({d['symbol'] for d in sealed['documents']} == {'000333', '601318', '600887'})
        for doc in sealed['documents']:
            require(doc['period'] == '2025Q1' and doc['status'] in ('sealed', 'failed') and isinstance(doc['name'], str))
            # Metadata alone may be shown. Answers, text and predictions cannot be smuggled into a sealed entry.
            require(not {'value', 'prediction', 'reference', 'rows', 'text', 'pages', 'extracted_text', 'score', 'metrics'}.intersection(doc))
            if doc['status'] == 'sealed':
                require(valid_hash(doc['pdf_sha256']) and r['artifacts'].get(doc['pdf_path']) == doc['pdf_sha256'])
                require(doc['pdf_path'].startswith('research/artifacts/filing-development/sealed-evaluation/') and doc['pdf_path'].endswith('.pdf'))
                require(isinstance(doc['pdf_url'], str) and doc['pdf_url'].startswith('https://static.cninfo.com.cn/finalpage/'))
        prepared = sum(doc['status'] == 'sealed' for doc in sealed['documents'])
        require(sealed['status'] == ('sealed' if prepared == 3 else 'blocked' if prepared == 0 else 'partial'))
        require(sealed['manifest_path'].startswith('research/artifacts/filing-development/sealed-evaluation/'))
        manifest = self._artifact_json(sealed['manifest_path'], r['artifacts'])
        if manifest is not None:
            require(manifest['content_accessed'] is False and manifest['documents'] == sealed['documents'])
            if 'status' in manifest:
                require(manifest['status'] == sealed['status'])
        human = r['human_review']
        require(human['item_count'] == 18 and type(human['item_count']) is int and human['completed'] == 0 and type(human['completed']) is int and human['status'] == 'pending_human_review')
        for key, filename in (('manifest_path', 'manifest.json'), ('checklist_path', 'checklist.csv'), ('guide_path', 'guide.md')):
            name = human[key]; require(name.startswith('docs/research/human-review/') and PurePosixPath(name).name == filename and name in r['artifacts'])
        manifest = self._artifact_json(human['manifest_path'], r['artifacts'])
        if manifest is not None:
            require(manifest['item_count'] == 18 and manifest['completed'] == 0 and manifest['status'] == 'pending_human_review')
            require(isinstance(manifest['artifacts'], dict))
            require(all(manifest['artifacts'][filename] == r['artifacts'][human[key]] for filename, key in (('checklist.csv', 'checklist_path'), ('guide.md', 'guide_path'))))
        checklist = self._path(human['checklist_path'], artifact=True)
        if checklist.exists():
            raw = checklist.read_bytes(); require(hashlib.sha256(raw).hexdigest() == r['artifacts'][human['checklist_path']])
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
            require(reader.fieldnames is not None and len(reader.fieldnames) == len(REVIEW_COLUMNS) and set(reader.fieldnames) == REVIEW_COLUMNS)
            rows = list(reader)
            expected = {f'{symbol}-{period}:{metric}' for symbol in ('600519', '600036', '600585') for period in ('2024Q1', '2025Q1') for metric in METRICS}
            require(len(rows) == 18 and {row['case_id'] for row in rows} == expected)
            require(all(set(row) == REVIEW_COLUMNS and row['case_id'] == row['doc_id']+':'+row['metric'] and row['status'] == 'unreviewed' and all(row[key] == '' for key in REVIEW_BLANKS) for row in rows))

    def _record(self, r):
        require(isinstance(r, dict) and r['schema'] == 'filing-development-publication-v1')
        p = r['protocol']; require(isinstance(p, dict) and r['run_id'] == 'filingdev-' + stable_hash(p))
        model = r['model_details']; design = p['design']
        require(isinstance(model['model_id'], str) and model['model_id'] == design['model_id'])
        require(isinstance(model['revision'], str) and re.fullmatch('[a-f0-9]{40}', model['revision']) and model['revision'] == design['model_revision'])
        require(isinstance(model['generation'], dict) and stable_hash(model['generation']) == stable_hash(design['generation']) == stable_hash(GENERATION) and isinstance(model['runtime'], dict))
        require(datetime.fromisoformat(r['created_at']).tzinfo is not None)
        require(r['sources'] == p['sources'] and isinstance(r['sources'], dict) and r['sources'])
        require(valid_hash(r['input_sha256']) and r['input_sha256'] == p['inputs_sha256'])
        require(valid_hash(r['reference_sha256']) and r['reference_sha256'] == p['reference_sha256'])
        require(set(r['prediction_sha256']) == set(METHODS[2:]) and all(valid_hash(v) for v in r['prediction_sha256'].values()))
        require(isinstance(r['artifacts'], dict) and r['artifacts'])
        require(all(sha in r['artifacts'].values() for sha in (r['input_sha256'], r['reference_sha256'], *r['prediction_sha256'].values())))
        docs = r['documents']; require(isinstance(docs, list) and len(docs) == 3)
        require({d['symbol'] for d in docs} == {'600519', '600036', '600585'})
        for doc in docs:
            require(doc['doc_id'] == doc['symbol']+'-2024Q1' and doc['period'] == '2024Q1' and doc['split'] == 'development')
            require(isinstance(doc['name'], str) and isinstance(doc['pdf_url'], str) and doc['pdf_url'].startswith('https://'))
            require(doc['input_pages'] == [1,2,3,4,5,6])
        methods = r['methods']; require(isinstance(methods, list) and len(methods) == 4 and {m['id'] for m in methods} == set(METHODS))
        require(all(isinstance(m['label'], str) and isinstance(m['description'], str) for m in methods))
        rows = r['rows']; require(isinstance(rows, list) and len(rows) == 36)
        require({(row['doc_id'], row['metric'], row['method']) for row in rows} == {(d['doc_id'], metric, method) for d in docs for metric in METRICS for method in METHODS})
        for row in rows:
            require(row['case_id'] == row['doc_id']+'/'+row['metric'] and row.get('split', 'development') == 'development')
            require(isinstance(row['label'], str) and row['status'] in ('ok', 'invalid_output', 'input_too_long', 'error'))
            c = row['checks']; require(isinstance(c, dict) and set(c) == set(CHECKS) and all(type(c[k]) is bool for k in CHECKS))
            require(c['complete'] == all(c[k] for k in CHECKS[:6]))
            if row['prediction'] is not None:
                value_record(row['prediction'], row['metric'])
            require(row['status'] != 'ok' or row['prediction'] is not None)
            require(c['answered'] == (row['status'] == 'ok' and row['prediction'] is not None and row['prediction']['value'] is not None))
            if row['status'] != 'ok':
                require(row['prediction'] is None and not any(c.values()))
            reference = row['reference']; require(reference['status'] in ('verified', 'unavailable', 'ambiguous') and type(reference['input_context_complete']) is bool)
            require(isinstance(reference['variants'], list))
            for value in reference['variants']:
                reference_variant(value)
            require(strings(row['error_reasons']))
            require(row['candidate_count'] is None or count(row['candidate_count']))
            require(row['candidate_covered'] is None or type(row['candidate_covered']) is bool)
            require((row['candidate_count'] is None) == (row['candidate_covered'] is None))
            if row['method'].startswith('baseline_'):
                require(row['candidate_count'] is None and row['candidate_covered'] is None)
            for key in ('input_tokens', 'output_tokens'):
                require(row[key] is None or count(row[key]))
            require(row['latency_seconds'] is None or (type(row['latency_seconds']) in (int, float) and math.isfinite(row['latency_seconds']) and row['latency_seconds'] >= 0))
            if row['method'] in METHODS[2:]:
                if row['status'] == 'ok':
                    require(row['prediction']['quote'] is None or len(row['prediction']['quote']) <= 160)
                    require(row['input_tokens'] is not None and row['input_tokens'] <= GENERATION['max_input_tokens'])
                    require(row['output_tokens'] is not None and row['output_tokens'] <= GENERATION['max_new_tokens'])
                if row['status'] == 'input_too_long':
                    require(row['output_tokens'] == 0)
        summaries = r['metrics']; require(isinstance(summaries, list) and len(summaries) == 4 and {s['method'] for s in summaries} == set(METHODS))
        for summary in summaries:
            group = [row for row in rows if row['method'] == summary['method']]
            counts = dict(total=9, format_valid=sum(row['status'] == 'ok' for row in group), answered=sum(row['checks']['answered'] for row in group), correct_abstentions=sum(row['checks']['correct_abstention'] for row in group))
            counts.update({key+'_correct': sum(row['checks'][key] for row in group) for key in CHECKS[:7]})
            require(all(type(summary[k]) is int and summary[k] == v for k, v in counts.items()))
            coverage = [row['candidate_covered'] for row in group]
            require(summary['candidate_covered'] == (None if all(v is None for v in coverage) else sum(v is True for v in coverage)))
            if summary['candidate_covered'] is not None:
                require(type(summary['candidate_covered']) is int)
        require(strings(r['limitations']) and r['limitations'])
        self._baseline(r)
        self._prediction_rows(r)
        self._scoring(r)
        self._model_verification(r)
        self._preparation(r)

    def get(self):
        path = self.folder/'latest.json'
        if not path.exists():
            return dict(record=None, record_sha256=None, artifact_status='empty', missing_artifacts=[])
        try:
            require(path.resolve().is_relative_to(self.folder.resolve()) and path.is_file())
            body = json.loads(path.read_text('utf8')); r = body['record']; require(stable_hash(r) == body['sha256'])
            # File byte checks are repeated on every request; an old acceptance is never cached.
            missing = self._files(r['sources'], artifact=False) + self._files(r['artifacts'], artifact=True)
            self._record(r)
            return dict(record=r, record_sha256=body['sha256'], artifact_status='missing' if missing else 'verified', missing_artifacts=sorted(set(missing)))
        except (ValueError, KeyError, TypeError, AttributeError, OSError, ArithmeticError, csv.Error):
            raise DomainConflict('filing_development_corrupt', '开发验证记录或来源完整性校验失败，未展示为有效成绩。') from None

    def review(self, file):
        if file not in ('checklist', 'guide'):
            raise KeyError(file)
        body = self.get()
        if body['artifact_status'] != 'verified':
            raise DomainConflict('filing_development_missing', '开发验证来源尚未齐备，暂不能下载人工核验包。')
        r = body['record']; name = r['human_review'][file+'_path']
        try:
            raw = self._path(name, artifact=True).read_bytes()
        except OSError:
            raise DomainConflict('filing_development_review_changed', '人工核验包在读取期间发生变化，请刷新后重试。') from None
        if hashlib.sha256(raw).hexdigest() != r['artifacts'][name]:
            raise DomainConflict('filing_development_review_changed', '人工核验包在读取期间发生变化，请刷新后重试。')
        return raw
