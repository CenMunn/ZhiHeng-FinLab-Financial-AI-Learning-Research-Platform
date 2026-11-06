"""Auditable, answer-independent binding of filing values to page-local headers.

No PDF runtime dependency. Scope/period remain query constraints, not report-wide
identity recognition. Unknown layout, headers, type or units cannot authorize an
amount. Coordinates are in the PDF's native points; no cross-page inheritance.
"""
import re
import unicodedata
from decimal import Decimal

METRICS = ('revenue', 'net_profit_parent', 'operating_cashflow')
KEYS = ('metric', 'value', 'unit', 'currency', 'period', 'scope', 'page', 'quote')
NUM = re.compile(r'^[（(]?[-−－]?\d[\d,，]*(?:\.\d+)?[)）]?(?:[%％])?$')
UNIT = re.compile(r'(?:单位[:：]?|人民币)(百万元|亿元|万元|千元|元)(?!/股)')
MAX_CANDIDATES = 128
MAX_EVIDENCE_BLOCKS = 24


def _compact(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


def _box(words):
    return [min(w['x0'] for w in words), min(w['top'] for w in words),
            max(w['x1'] for w in words), max(w['bottom'] for w in words)]


def _lines(words):
    rows = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if not rows or abs(w['top']-rows[-1][0]['top']) > 3:
            rows.append([w])
        else:
            rows[-1].append(w)
    return [sorted(r, key=lambda w: w['x0']) for r in rows]


def _cells(row):
    cells = []
    for w in row:
        if cells and w['x0']-cells[-1][-1]['x1'] <= 12:
            cells[-1].append(w)
        else:
            cells.append([w])
    return [dict(text=' '.join(w['text'] for w in ws), bbox=_box(ws)) for ws in cells]


def _period(text, period):
    s = _compact(text)
    if '报告' in s and '报告期' not in s:
        return 'unknown'
    current = bool(re.search(r'本报告期(?!末)|本期|本年|本季度|当期', s))
    prior = bool(re.search(r'上年同期|上期|去年|上年度', s))
    year = int(period[:4])
    # Dates are flow periods only; a balance-sheet year/date is insufficient.
    for y in (year, year-1):
        if re.search(str(y)+r'年?(?:第?一季度|1[-—–至~]3月)', s):
            current |= y == year
            prior |= y != year
    return 'unknown' if current == prior else ('current' if current else 'prior')


def _kind(text):
    s = _compact(text)
    if re.search(r'每股|元/股', s):
        return 'per_share'
    if re.search(r'%|百分|变动|增减|增长|同比|收益率|报告期比', s):
        return 'rate'
    return 'unknown'


def _metric(text, metric):
    s = _compact(text)
    if metric == 'revenue':
        return '营业收入' in s
    if metric == 'net_profit_parent':
        return '净利润' in s
    return bool(re.search(r'经营活动(?:产生的)?现金流量净额', s))


def _null(metric):
    return {k: metric if k == 'metric' else None for k in KEYS}


def _nearest(cells, x):
    return min(cells, key=lambda c: abs((c['bbox'][0]+c['bbox'][2])/2-x)) if cells else None


def _scope(text):
    parent, consolidated = '母公司' in text, '合并' in text
    return 'unknown' if parent == consolidated else ('parent' if parent else 'consolidated')


def _header_coverage(word, anchors):
    """Use observable column anchors and finite outer half-column boundaries.

    A lone header supplies only its actual horizontal span. Multiple header
    centers establish midpoint column boundaries; the two exterior boundaries
    extend by half the adjacent center gap. Wide, right-aligned amounts can
    overlap their header even when their own center lies outside that span.
    """
    if not anchors:
        return False
    if any(word['x0'] <= c['bbox'][2] and word['x1'] >= c['bbox'][0] for c in anchors):
        return True
    centers = sorted({(c['bbox'][0]+c['bbox'][2])/2 for c in anchors})
    if len(centers)<2:
        return False
    x = (word['x0']+word['x1'])/2
    return centers[0]-(centers[1]-centers[0])/2 <= x <= centers[-1]+(centers[-1]-centers[-2])/2


def build_cases(doc):
    """Return three cases with all source candidates and conservative eligibility.

    doc: doc_id/symbol/period/split/pages[{page,text}]/layout_pages[{page,words}].
    Candidate field uses the D30 eight-key codec; semantic and source evidence are
    additional metadata. Refusal uses the same keys with all non-metric null.
    """
    if not re.fullmatch(r'\d{4}Q[1-4]', doc['period']):
        raise ValueError('Unsupported query period')
    cases = [dict(case_id=doc['doc_id']+'/'+m, doc_id=doc['doc_id'], metric=m,
                  query=dict(period=doc['period'], scope='consolidated', symbol=doc['symbol']),
                  blocks=[], candidates=[], eligible_ids=[], rule_field=_null(m), rule_reasons=[],
                  scope_limitation='Scope supplied by query; unknown scope is not independently verified.') for m in METRICS]
    layouts = {p['page']: p['words'] for p in doc.get('layout_pages', [])}
    for page in doc['pages']:
        pn = page['page']
        rows = _lines(layouts.get(pn, []))
        label_left = min((w['x0'] for r in rows for w in r), default=0)
        headers, unit, unit_quote, currency, scope, had_data = [], None, '', None, 'unknown', False
        unit_bbox = None
        currency_unsupported = False
        for ri, row in enumerate(rows):
            text = ' '.join(w['text'] for w in row)
            s = _compact(text)
            cells = _cells(row)
            numeric = [w for w in row if NUM.fullmatch(_compact(w['text']))]
            if re.search(r'(母公司|合并).{0,5}(利润表|现金流量表|资产负债表)', s):
                scope = _scope(s)
                headers, had_data, unit, unit_quote = [], False, None, ''
                currency = None
                currency_unsupported = False
            # Per-share annotations are local type evidence, not a new table's
            # amount unit (e.g. 基本每股收益(人民币元) after 百万元).
            ums = UNIT.findall(s) if _kind(s) != 'per_share' else []
            if '单位' in s:
                unit, unit_quote, unit_bbox = None, text, _box(row)
            if ums:
                unit, unit_quote = (ums[0] if len(set(ums))==1 else None), text
                unit_bbox = _box(row)
            cm = re.search(r'币种[:：]?([^,，;；\s)）]+)', s)
            foreign = bool(re.search(r'美元|港元|港币|欧元|日元|USD|HKD|EUR|JPY',s,re.I))
            if cm:
                currency = 'CNY' if cm[1] == '人民币' else None
                currency_unsupported = currency is None
            elif foreign:
                currency, currency_unsupported = None, True
            elif '人民币' in s:
                currency, currency_unsupported = 'CNY', False
            hc = [c for c in cells if c['bbox'][0] > label_left+60 and (_period(c['text'], doc['period']) != 'unknown'
                  or re.search(r'报告期|上年同期|调整前|调整后|重述前|重述后|%|变动|同比|母公司|合并', _compact(c['text'])))]
            # Headers may contain dates but never standalone financial values.
            if hc and not numeric:
                if had_data:
                    headers, had_data = [], False
                headers.extend(hc)
            if not numeric:
                continue
            # Build wrapped labels from adjacent label-only fragments, bounded
            # to the label column and one row either side (no numeric carryover).
            first_x = min(w['x0'] for w in numeric)
            labels = [w for w in row if w['x1'] <= first_x and w not in numeric]
            label = ' '.join(w['text'] for w in labels)
            extra = []
            label_complete = any(_metric(label, m) for m in METRICS)
            for rj in (ri-1, ri+1):
                if not label_complete and 0 <= rj < len(rows) and abs(rows[rj][0]['top']-row[0]['top']) < 20:
                    fragment = [w for w in rows[rj] if w['x1'] < first_x-5]
                    if fragment and not any(NUM.fullmatch(_compact(w['text'])) for w in rows[rj]):
                        extra.extend(fragment)
            combined = ' '.join(w['text'] for w in sorted(labels+extra, key=lambda w:(w['top'],w['x0'])))
            for case in cases:
                metric = case['metric']
                if not _metric(combined, metric):
                    continue
                block_id = f'{pn}:{ri}'
                row_words = sorted(row+extra, key=lambda w:(w['top'],w['x0']))
                quote = ' '.join(w['text'] for w in row_words)
                block = dict(block_id=block_id,page=pn,row=quote,unit_context=unit_quote,
                             before='',after='',row_clipped=False,distant_values_excluded=0)
                case['blocks'].append(block)
                for w in numeric:
                    token = _compact(w['text'])
                    # A superscript/label footnote before real columns is not
                    # an amount; negative parentheses in amount columns remain.
                    period_anchors = [c for c in headers if _period(c['text'],doc['period']) != 'unknown' and _kind(c['text']) != 'rate']
                    adjustment_anchors = [c for c in headers if re.search(r'调整[前后]|重述[前后]',c['text'])]
                    first_column_left = min((c['bbox'][0] for c in period_anchors+adjustment_anchors),default=first_x)
                    if re.fullmatch(r'\([1-9]\)',token) and w['x1'] < first_column_left-15:
                        continue
                    x = (w['x0']+w['x1'])/2
                    periods = [c for c in headers if re.search(r'本报告期|本期|上年同期|上期|\d{4}年?',_compact(c['text'])) and _kind(c['text']) != 'rate']
                    # Rate anchors belong to the same header tier as periods.
                    primary = periods+[c for c in headers if _kind(c['text']) in ('rate','per_share')]
                    covered = _header_coverage(w,primary+adjustment_anchors)
                    h = _nearest(primary,x)
                    role = _period(h['text'],doc['period']) if h else 'unknown'
                    tied = []
                    if h:
                        distance = abs((h['bbox'][0]+h['bbox'][2])/2-x)
                        tied = [c for c in primary if abs((c['bbox'][0]+c['bbox'][2])/2-x) <= distance+3]
                        if len({_period(c['text'],doc['period']) for c in tied})>1:
                            role = 'unknown'
                    adjustments = [c for c in headers if re.search(r'调整[前后]|重述[前后]',c['text'])]
                    adj = _nearest(adjustments,x)
                    if adj and abs((adj['bbox'][0]+adj['bbox'][2])/2-x)>65:
                        adj = None
                    ar = ('before' if re.search(r'前',adj['text']) else 'after') if adj else 'none'
                    scope_headers = [c for c in headers if re.search(r'母公司|合并',c['text'])]
                    scope_header = _nearest(scope_headers,x)
                    candidate_scope = scope
                    scope_evidence = []
                    if scope_header:
                        distance = abs((scope_header['bbox'][0]+scope_header['bbox'][2])/2-x)
                        scope_evidence = [c for c in scope_headers if abs((c['bbox'][0]+c['bbox'][2])/2-x)<=distance+3]
                        roles = {_scope(c['text']) for c in scope_evidence}
                        candidate_scope = next(iter(roles)) if len(roles)==1 else 'unknown'
                    kind = _kind(combined)
                    if kind == 'unknown':
                        kind = _kind(h['text']) if h else 'unknown'
                    if token.endswith('%'):
                        kind = 'rate'
                    if kind == 'unknown' and h and role != 'unknown':
                        kind = 'amount'
                    reasons = []
                    if kind != 'amount': reasons.append('not_amount:'+kind)
                    if not covered: reasons.append('header_coverage_unknown')
                    if role != 'current': reasons.append('period:'+role)
                    if ar == 'before': reasons.append('before_adjustment')
                    if not unit: reasons.append('unknown_unit')
                    if not currency: reasons.append('unknown_currency')
                    if currency_unsupported: reasons.append('unsupported_currency')
                    if candidate_scope == 'parent': reasons.append('parent_scope')
                    if scope_header and candidate_scope == 'unknown': reasons.append('scope_header_unknown')
                    if metric == 'net_profit_parent':
                        if re.search(r'扣除|扣非|非经常',_compact(combined)): reasons.append('deducted_nonrecurring')
                        if not re.search(r'归属|归于',_compact(combined)): reasons.append('parent_profit_label_unknown')
                    if len(quote)>160: reasons.append('quote_budget_exceeded')
                    value = token.rstrip('%').replace(',','').replace('−','-').replace('－','-')
                    if value.startswith('(') and value.endswith(')'): value = '-'+value[1:-1]
                    field = dict(metric=metric,value=format(Decimal(value),'f'),unit=unit,currency=currency,
                                 period=doc['period'],scope='consolidated',page=pn,quote=quote if len(quote)<=160 else None)
                    evidence_cells = tied+([adj] if adj else [])+scope_evidence
                    evidence = [dict(page=pn,quote=c['text'],bbox=c['bbox']) for c in evidence_cells]
                    candidate = dict(candidate_id=len(case['candidates'])+1, field=field, block_id=block_id,
                                     original_token=w['text'],position=dict(page=pn,bbox=_box([w])),bbox=_box([w]),
                                     semantic=dict(financial_type=kind,period_role=role,adjustment_role=ar,scope_role=candidate_scope),
                                     eligible=not reasons,reasons=reasons,header_evidence=evidence,unit_evidence=unit_quote,
                                     unit_evidence_bbox=unit_bbox)
                    case['candidates'].append(candidate)
                    if len(case['candidates'])>MAX_CANDIDATES or len(case['blocks'])>MAX_EVIDENCE_BLOCKS:
                        raise ValueError('Evidence/candidate budget exceeded; no silent pruning')
            had_data = True
    for case in cases:
        eligible = [c for c in case['candidates'] if c['eligible']]
        case['eligible_ids'] = [c['candidate_id'] for c in eligible]
        distinct = {(Decimal(c['field']['value']),c['field']['unit'],c['field']['currency']) for c in eligible}
        if len(distinct)==1:
            case['rule_field'] = eligible[0]['field'].copy()
            case['rule_reasons'] = ['unique_consistent_source_amount']
        else:
            case['rule_reasons'] = ['conflicting_eligible_amounts' if distinct else 'no_eligible_amount']
        if not layouts:
            case['rule_reasons'].append('layout_unavailable')
    return cases
