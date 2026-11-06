import json
import unittest

from research.filing_development.evidence import build_case, candidate_options
from research.filing_development.model import PrefixTrie, parse_field


def document(text, period='2024Q1', symbol='600036'):
    return {'doc_id': symbol+'-'+period, 'symbol': symbol, 'title': '合成季报',
            'period': period, 'split': 'development', 'pdf_sha256': 'a'*64,
            'pages': [{'page': i, 'text': text if i == 1 else ''} for i in range(1, 7)]}


class EvidenceTests(unittest.TestCase):
    def test_current_and_previous_columns_are_both_candidates_in_either_order(self):
        for header, row in [('2024年1-3月 2023年1-3月', '营业收入 86,417 90,636 -4.65'),
                            ('2023年1-3月 2024年1-3月', '营业收入 90,636 86,417 -4.65')]:
            case = build_case(document('单位：百万元 币种：人民币\n'+header+'\n'+row), 'revenue')
            self.assertEqual([c['field']['value'] for c in case['candidates']],
                             ['86417', '90636', '-4.65'] if row.startswith('营业收入 86') else ['90636', '86417', '-4.65'])
            self.assertIn(header, case['blocks'][0]['before'])
            self.assertNotIn('answer', json.dumps(case))

    def test_declared_note_is_not_negative_money_and_per_share_unit_is_local(self):
        text = ('（人民币百万元，特别注明除外） 2024年1-3月 2023年1-3月\n'
                '基本每股收益(人民币元)(1) 1.51 1.54\n'
                '经营活动产生的现金流量净额 (2) (1,208) (12,618) 90.43\n注：\n(2) 经营活动说明')
        case = build_case(document(text), 'operating_cashflow')
        values = [c['field']['value'] for c in case['candidates']]
        self.assertEqual(values[:2], ['-1208', '-12618'])
        self.assertNotIn('-2', values)
        self.assertTrue(all(c['field']['unit'] == '百万元' for c in case['candidates']))

    def test_small_parenthesized_loss_without_note_remains_candidate(self):
        case = build_case(document('单位：元 币种：人民币\n经营活动产生的现金流量净额 (2) (5)'), 'operating_cashflow')
        self.assertEqual([c['field']['value'] for c in case['candidates']], ['-2', '-5'])

    def test_deducted_profit_and_previous_amounts_remain_distractors(self):
        text = ('单位：万元 币种：人民币\n本期 上期\n'
                '归属于本行股东的净利润 100 90\n扣除非经常性损益后归属于本行股东的净利润 80 70')
        case = build_case(document(text), 'net_profit_parent')
        self.assertEqual([c['field']['value'] for c in case['candidates']], ['100', '90', '80', '70'])
        self.assertTrue(any('扣除' in b['row'] for b in case['blocks']))

    def test_inline_original_unit_is_preserved_and_all_quotes_are_real_short_spans(self):
        text = '本集团实现营业收入864.17亿元，同比下降4.65%。'
        case = build_case(document(text), 'revenue')
        chosen = case['candidates'][0]['field']
        self.assertEqual((chosen['value'], chosen['unit']), ('864.17', '亿元'))
        self.assertTrue(all(c['field']['quote'] in text and len(c['field']['quote']) <= 160 for c in case['candidates']))

    def test_missing_unit_stays_unknown_and_no_row_still_has_abstention(self):
        case = build_case(document('营业收入 100 90'), 'revenue')
        self.assertIsNone(case['candidates'][0]['field']['unit'])
        missing = build_case(document('没有相关字段'), 'operating_cashflow')
        options = [json.loads(x) for x in candidate_options(missing)]
        self.assertEqual(len(options), 1)
        self.assertIsNone(options[0]['value'])

    def test_report_currency_context_is_shared_with_both_methods(self):
        doc = document('单位：百万元 币种：人民币\n')
        doc['pages'][1]['text'] = '本集团实现营业收入864.17亿元。'
        case = build_case(doc, 'revenue')
        self.assertEqual(case['candidates'][0]['field']['currency'], 'CNY')
        self.assertEqual(case['currency_context'][0]['page'], 1)
        self.assertIn('人民币', case['currency_context'][0]['quote'])
        from research.filing_development.model import build_prompt
        self.assertIn('currency_context', build_prompt(case))

    def test_no_evaluation_or_new_company_can_enter_development(self):
        for doc in [document('营业收入 1', period='2025Q1'), document('营业收入 1', symbol='000333')]:
            with self.assertRaises(ValueError):
                build_case(doc, 'revenue')

    def test_budget_overflow_is_explicit_not_silent_candidate_pruning(self):
        text = '单位：元 币种：人民币\n'+'\n'.join('营业收入 10 20' for _ in range(25))
        with self.assertRaises(ValueError):
            build_case(document(text), 'revenue')

    def test_candidate_and_abstention_serialization_survives_sorted_json_storage(self):
        case = build_case(document('单位：元 币种：人民币\n营业收入 100 90'), 'revenue')
        roundtrip = json.loads(json.dumps(case, ensure_ascii=False, sort_keys=True))
        self.assertEqual(candidate_options(case), candidate_options(roundtrip))
        expected_order = ['metric', 'value', 'unit', 'currency', 'period', 'scope', 'page', 'quote']
        for option in candidate_options(roundtrip):
            self.assertEqual(list(json.loads(option)), expected_order)
            self.assertTrue(option.startswith('{\n  "metric": "revenue",\n  "value":'))


class OutputTests(unittest.TestCase):
    def field(self):
        return {'metric': 'revenue', 'value': '100', 'unit': '元', 'currency': 'CNY',
                'period': '2024Q1', 'scope': 'consolidated', 'page': 1, 'quote': '营业收入 100'}

    def test_strict_json_keeps_failures_without_cleaning_or_repair(self):
        raw = json.dumps(self.field(), ensure_ascii=False)
        self.assertEqual(parse_field(raw, 'revenue'), self.field())
        for bad in ['```json\n'+raw+'\n```', raw.replace('"100"', '"1,000"'),
                    raw[:-1]+',"value":"99"}', raw.replace('"quote":', '"wrong_quote":')]:
            with self.assertRaises(ValueError):
                parse_field(bad, 'revenue')

    def test_short_quote_null_fields_and_identity_are_validated(self):
        f = self.field(); f.update(value=None, unit=None, currency=None, page=None, quote=None)
        self.assertIsNone(parse_field(json.dumps(f), 'revenue')['value'])
        for key, value in [('quote', '字'*161), ('page', True), ('metric', 'net_profit_parent'), ('unit', '千元')]:
            bad = {**self.field(), key: value}
            with self.assertRaises(ValueError):
                parse_field(json.dumps(bad), 'revenue')

    def test_trie_only_allows_registered_prefixes_and_explicit_terminal(self):
        trie = PrefixTrie([[10, 20], [10, 30], [40]], eos_token_id=99)
        self.assertEqual(trie.allowed([]), [10, 40])
        self.assertEqual(trie.allowed([10]), [20, 30])
        self.assertEqual(trie.allowed([10, 20]), [99])
        self.assertEqual(trie.allowed([40]), [99])
        with self.assertRaises(ValueError):
            trie.allowed([10, 70])
        with self.assertRaises(ValueError):
            PrefixTrie([], eos_token_id=99)

    def test_complete_option_may_also_prefix_another_option(self):
        trie = PrefixTrie([[10], [10, 20]], eos_token_id=99)
        self.assertEqual(trie.allowed([10]), [20, 99])


if __name__ == '__main__':
    unittest.main()
