"""Answer-independent financial row retrieval and finite source candidates."""
import json
import re
import unicodedata
from pathlib import Path

from research.filing_extraction.common import METRICS, NUMBER, number
from research.market.common import PROJECT

CONFIG = PROJECT / 'research/configs/filing-development-v1.json'
UNIT = r'(百万元|亿元|万元|元)'
PATTERNS = {'revenue': r'营\s*业\s*收\s*入',
            'net_profit_parent': r'净\s*利\s*润',
            'operating_cashflow': r'经\s*营\s*活\s*动(?:\s*产\s*生\s*的)?\s*现\s*金\s*流\s*量\s*净\s*额'}


def config():
    return json.loads(CONFIG.read_text('utf8'))


def unit_before(text, position):
    pattern = r'单位\s*[:：]\s*'+UNIT+r'|(?m:^[ \t]*[（(]?\s*人民币\s*'+UNIT+r'\s*[,，]?\s*特别注明除外)'
    matches = list(re.finditer(pattern, text[:position]))
    if not matches:
        return None, ''
    match = matches[-1]
    return next(g for g in match.groups() if g), match.group()


def _note(token, prefix, suffix, page):
    match = re.fullmatch(r'\(([1-9])\)', token)
    return bool(match and not prefix.strip() and re.match(r'\s*'+NUMBER, suffix)
                and re.search(r'注\s*[:：]', page)
                and re.search(r'(?m)^\s*\('+match[1]+r'\)\s*[^\d\s]', page))


def build_case(doc, metric):
    design = config()
    if (metric not in METRICS or doc.get('split') != 'development'
            or doc.get('period') != design['development_period']
            or doc.get('symbol') not in design['development_symbols']
            or doc.get('doc_id') != doc['symbol']+'-'+doc['period']
            or len(doc.get('pages', [])) != 6
            or [p['page'] for p in doc['pages']] != list(range(1, 7))):
        raise ValueError('Only the three fixed 2024 development reports are admitted')
    blocks, candidates, seen, currency_context = [], [], set(), []
    for page in doc['pages']:
        for match in re.finditer(r'币种\s*[:：]\s*人民币|人民币\s*(?:百万元|亿元|万元|元)', page['text']):
            currency_context.append({'page': page['page'], 'quote': match.group()})
            break
    for page in doc['pages']:
        original = page['text']
        parts, offsets = [], []
        for index, char in enumerate(original):
            normalized = unicodedata.normalize('NFKC', char)
            parts.append(normalized)
            offsets.extend([index]*len(normalized))
        text = ''.join(parts)
        for match in re.finditer(PATTERNS[metric], text):
            line_start = text.rfind('\n', 0, match.start()) + 1
            start = max(line_start, match.start()-60)
            end = text.find('\n', match.end())
            if end < 0:
                end = len(text)
            # A wrapped financial label can have its amount on the next line.
            for _ in range(2):
                tail = text[match.end():end]
                tokens = list(re.finditer(NUMBER, tail))
                if tokens or end >= len(text):
                    break
                next_end = text.find('\n', end+1)
                end = len(text) if next_end < 0 else next_end
            row = text[start:end]
            if not re.search(NUMBER, text[match.end():end]):
                continue
            if len(blocks) >= design['max_evidence_blocks']:
                raise ValueError('Evidence-block budget exceeded; no silent pruning')
            block_id = str(page['page'])+':'+str(match.start())
            unit, unit_quote = unit_before(text, start)
            block = {'block_id': block_id, 'page': page['page'], 'row': row[:600],
                     'before': text[max(0, start-design['context_before']):start],
                     'after': text[end:end+design['context_after']], 'unit_context': unit_quote,
                     'row_clipped': len(row) > 600, 'distant_values_excluded': 0}
            blocks.append(block)
            for token in re.finditer(NUMBER, text[match.end():end]):
                a, b = match.end()+token.start(), match.end()+token.end()
                if _note(token.group(), text[match.end():a], text[b:end], text):
                    continue
                if (page['page'], a, b) in seen:
                    continue
                seen.add((page['page'], a, b))
                # Quotes contain the complete financial label and selected number.
                qend = min(end, start+design['quote_characters'])
                if b > qend:
                    block['distant_values_excluded'] += 1
                    continue
                inline = re.match(r'\s*'+UNIT+r'(?!/股)', text[b:end])
                chosen_unit = inline[1] if inline else unit
                field = {'metric': metric, 'value': format(number(token.group()), 'f'),
                         'unit': chosen_unit,
                         'currency': 'CNY' if currency_context else None,
                         'period': doc['period'], 'scope': 'consolidated',
                         'page': page['page'], 'quote': original[offsets[start]:offsets[qend-1]+1].strip()}
                candidates.append({'candidate_id': len(candidates)+1, 'field': field,
                                   'block_id': block_id, 'original_token': token.group(),
                                   'position': {'start': a, 'end': b}, 'unit_evidence': unit_quote})
                if len(candidates) > design['max_candidates']:
                    raise ValueError('Candidate budget exceeded; no silent pruning')
    return {'case_id': doc['doc_id']+'/'+metric, 'doc_id': doc['doc_id'], 'metric': metric,
            'query': {'period': doc['period'], 'scope': 'consolidated', 'symbol': doc['symbol']},
            'currency_context': currency_context, 'blocks': blocks, 'candidates': candidates}


def candidate_options(case):
    refusal = {k: None for k in ('value', 'unit', 'currency', 'period', 'scope', 'page', 'quote')}
    refusal = {'metric': case['metric'], **refusal}
    fields = [c['field'] for c in case['candidates']] + [refusal]
    order = ('metric', 'value', 'unit', 'currency', 'period', 'scope', 'page', 'quote')
    # Persistence sorts dictionary keys. Rebuild every branch, including abstain,
    # in the same order so decoding cannot choose on an accidental first key.
    return list(dict.fromkeys(json.dumps({k: f[k] for k in order}, ensure_ascii=False, indent=2) for f in fields))
