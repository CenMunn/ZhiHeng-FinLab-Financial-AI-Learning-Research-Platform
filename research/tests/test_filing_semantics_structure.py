"""Hand-built layout challenges: amounts must follow headers, never value order."""
import unittest
from research.filing_semantics.structure import build_cases


def doc(rows, second=None):
    def page(n, entries):
        words = []
        for y, cells in enumerate(entries):
            for x, text in cells:
                words.append(dict(text=text, x0=x, x1=x+max(20, len(text)*6), top=y*20, bottom=y*20+10))
        return dict(page=n, words=words)
    layouts = [page(1, rows)] + ([page(2, second)] if second else [])
    return dict(doc_id='test-2024Q1', symbol='test', period='2024Q1', split='development',
                pages=[dict(page=p['page'], text='\n'.join(' '.join(t for _,t in r) for r in (rows if p['page']==1 else second))) for p in layouts], layout_pages=layouts)


def revenue(d):
    return build_cases(d)[0]


class StructureTests(unittest.TestCase):
    def test_current_nonfirst_and_swapped(self):
        for headers, values in [(['上年同期','本报告期'],['800','2']), (['本报告期','上年同期'],['2','800'])]:
            case = revenue(doc([[(0,'单位：万元 币种：人民币')],[(200,headers[0]),(400,headers[1])],[(0,'营业收入'),(200,values[0]),(400,values[1])]]))
            self.assertEqual(case['rule_field']['value'], '2')
            self.assertEqual(case['rule_field']['unit'], '万元')
    def test_adjusted_multilevel_headers(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'上年同期'),(500,'本报告期')],[(170,'调整前'),(300,'调整后')],[(0,'营业收入'),(170,'800'),(300,'700'),(500,'2')]]))
        self.assertEqual(case['rule_field']['value'], '2')
        self.assertEqual([c['semantic']['period_role'] for c in case['candidates']], ['prior','prior','current'])
        self.assertEqual([c['semantic']['adjustment_role'] for c in case['candidates']], ['before','after','none'])
    def test_percentage_and_per_share_excluded(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期'),(400,'增减变动幅度(%)')],[(0,'营业收入'),(200,'2'),(400,'80')],[(0,'营业收入每股(元/股)'),(200,'0.01')]]))
        self.assertEqual(case['rule_field']['value'],'2')
        self.assertEqual(sum(c['eligible'] for c in case['candidates']),1)
    def test_missing_conflicting_header_refuses(self):
        for header in ['', '本报告期 上年同期']:
            case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,header)],[(0,'营业收入'),(200,'2')]]))
            self.assertIsNone(case['rule_field']['value'])
    def test_duplicate_values_in_distinct_columns_retained(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'上年同期'),(400,'本报告期')],[(0,'营业收入'),(200,'2'),(400,'2')]]))
        self.assertEqual(len(case['candidates']),2)
        self.assertEqual(len(case['eligible_ids']),1)
    def test_conflicting_sources_refuse(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'营业收入'),(200,'2')],[(0,'营业收入'),(200,'3')]]))
        self.assertIsNone(case['rule_field']['value'])
        self.assertIn('conflicting_eligible_amounts',case['rule_reasons'])
    def test_consistent_sources_answer(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'营业收入'),(200,'2')],[(0,'营业收入'),(200,'2')]]))
        self.assertEqual(case['rule_field']['value'],'2')
    def test_unit_switch_and_parent_scope(self):
        case = revenue(doc([[(0,'合并利润表')],[(0,'单位：千元 币种：人民币')],[(200,'本报告期')],[(0,'营业收入'),(200,'-2.00')],[(0,'母公司利润表')],[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'营业收入'),(200,'300')]]))
        self.assertEqual(case['rule_field']['value'],'-2.00')
        self.assertEqual(case['rule_field']['unit'],'千元')
        self.assertIn('parent_scope',case['candidates'][-1]['reasons'])
    def test_crosspage_no_header_or_unit_inheritance(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')]], [[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
    def test_net_profit_deducted_interference(self):
        cases = build_cases(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'归属于上市公司股东的净利润'),(200,'2')],[(0,'归属于上市公司股东的扣除非经常性损益的净利润'),(200,'900')]]))
        self.assertEqual(cases[1]['rule_field']['value'],'2')
        self.assertIn('deducted_nonrecurring',cases[1]['candidates'][-1]['reasons'])
    def test_unknown_unit_refuses(self):
        self.assertIsNone(revenue(doc([[(200,'本报告期')],[(0,'营业收入'),(200,'2')]]))['rule_field']['value'])
    def test_budget_never_silently_drops(self):
        rows = [[(0,'单位：元 币种：人民币')],[(200,'本报告期')]] + [[(0,'营业收入'),(200,str(i))] for i in range(257)]
        with self.assertRaisesRegex(ValueError,'budget'):
            revenue(doc(rows))
    def test_wrapped_deducted_label_does_not_contaminate_adjacent_rows(self):
        cases = build_cases(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'归属于上市公司股东的净利润'),(200,'2')],[(0,'归属于上市公司股东的扣除非经常性损')],[(0,'益的净利润'),(200,'3')],[(0,'经营活动产生的现金流量净额'),(200,'4')]]))
        self.assertEqual(cases[1]['rule_field']['value'],'2')
        self.assertEqual(cases[2]['rule_field']['value'],'4')
    def test_wrapped_rate_header_and_label_are_not_amount_headers(self):
        cases = build_cases(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期'),(400,'本报告期比上年同')],[(400,'期增减变动幅度(%)')],[(0,'营业收入'),(200,'2'),(400,'80')],[(0,'年化加权平均净资产')],[(0,'收益率(%)(1)')],[(0,'经营活动产生的现金流量净额'),(200,'(2)'),(400,'90')]]))
        self.assertEqual(cases[0]['rule_field']['value'],'2')
        self.assertEqual(cases[2]['rule_field']['value'],'-2')
    def test_report_title_cannot_supply_missing_column_header(self):
        case = revenue(doc([[(200,'2024年第一季度报告')],[(0,'单位：元 币种：人民币')],[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
    def test_unsupported_new_unit_clears_old_unit(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'单位：美元')],[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
    def test_current_adjusted_after_only_and_negative_amount_not_footnote(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(300,'本报告期')],[(200,'调整前'),(400,'调整后')],[(0,'营业收入'),(200,'(2)'),(400,'(3)')]]))
        self.assertEqual(len(case['candidates']),2)
        self.assertEqual(case['rule_field']['value'],'-3')
    def test_label_note_excluded_and_negative_amount_kept(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期'),(400,'上年同期')],[(0,'营业收入'),(100,'(2)'),(220,'(3)'),(420,'50')]]))
        self.assertEqual(len(case['candidates']),2)
        self.assertEqual(case['rule_field']['value'],'-3')
    def test_quote_budget_retains_candidate_but_refuses(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(1500,'本报告期')],[(0,'营业收入'+'附注'*90),(1500,'2')]]))
        self.assertEqual(len(case['candidates']),1)
        self.assertIsNone(case['rule_field']['value'])
        self.assertIn('quote_budget_exceeded',case['candidates'][0]['reasons'])
    def test_text_without_layout_refuses_explicitly(self):
        d = doc([[(0,'营业收入 本报告期 单位：元 币种：人民币 2')]])
        d.pop('layout_pages')
        case = revenue(d)
        self.assertIsNone(case['rule_field']['value'])
        self.assertIn('layout_unavailable',case['rule_reasons'])
    def test_stacked_conflicting_periods_refuse(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(200,'上年同期')],[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
    def test_conflicting_units_in_same_evidence_refuse(self):
        case = revenue(doc([[(0,'单位：元 单位：万元 币种：人民币')],[(200,'本报告期')],[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
    def test_evidence_block_budget_24_is_enforced(self):
        rows = [[(0,'单位：元 币种：人民币')],[(200,'本报告期')]] + [[(0,'营业收入'),(200,str(i))] for i in range(25)]
        with self.assertRaisesRegex(ValueError,'budget'):
            revenue(doc(rows))
    def test_candidate_budget_128_is_enforced(self):
        # 22 rows x 6 columns = 132 candidates, under the evidence-block cap.
        rows = [[(0,'单位：元 币种：人民币')],[(200,'本报告期')]] + [[(0,'营业收入')]+[(200+i*100,str(i)) for i in range(6)] for _ in range(22)]
        with self.assertRaisesRegex(ValueError,'budget'):
            revenue(doc(rows))
    def test_per_share_currency_unit_does_not_override_table_unit(self):
        cases = build_cases(doc([[(0,'单位：百万元 币种：人民币')],[(200,'本报告期')],[(0,'基本每股收益(人民币元)'),(200,'0.1')],[(0,'经营活动产生的现金流量净额'),(200,'2')]]))
        self.assertEqual(cases[2]['rule_field']['unit'],'百万元')
    def test_per_share_slash_unit_does_not_override_table_unit(self):
        cases = build_cases(doc([[(0,'单位：百万元 币种：人民币')],[(200,'本报告期')],[(0,'基本每股收益(人民币元/股)'),(200,'0.1')],[(0,'经营活动产生的现金流量净额'),(200,'2')]]))
        self.assertEqual(cases[2]['rule_field']['unit'],'百万元')
    def test_new_table_explicit_foreign_currency_is_not_cny(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'合并利润表')],[(0,'单位：元 币种：美元')],[(200,'本报告期')],[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
        self.assertIn('unsupported_currency',case['candidates'][0]['reasons'])
        self.assertIsNone(case['candidates'][0]['field']['currency'])
    def test_parallel_parent_and_consolidated_headers_bind_scope(self):
        for scopes, values in [(['母公司','合并'],['2','3']),(['合并','母公司'],['3','2'])]:
            case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,scopes[0]),(400,scopes[1])],[(200,'本报告期'),(400,'本报告期')],[(0,'营业收入'),(200,values[0]),(400,values[1])]]))
            self.assertEqual(case['rule_field']['value'],'3')
            self.assertEqual(sum(c['eligible'] for c in case['candidates']),1)
    def test_ambiguous_scope_header_refuses_even_equal_values(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'母公司及合并')],[(200,'本报告期')],[(0,'营业收入'),(200,'2')]]))
        self.assertIsNone(case['rule_field']['value'])
    def test_far_unheaded_value_never_becomes_model_eligible(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,'营业收入'),(200,'2'),(700,'800')]]))
        self.assertEqual(case['rule_field']['value'],'2')
        self.assertEqual(case['eligible_ids'],[1])
        self.assertIn('header_coverage_unknown',case['candidates'][1]['reasons'])
    def test_column_outer_boundary_excludes_unheaded_value(self):
        case = revenue(doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期'),(400,'上年同期')],[(0,'营业收入'),(200,'2'),(400,'3'),(700,'800')]]))
        self.assertEqual(case['eligible_ids'],[1])
        self.assertIn('header_coverage_unknown',case['candidates'][-1]['reasons'])
    def test_right_aligned_amount_wider_than_header_is_covered(self):
        d = doc([[(0,'单位：元 币种：人民币')],[(300,'本报告期')],[(0,'营业收入'),(260,'123456789.12')]])
        # Amount ends at 326, overlapping the centered 300..324 header.
        self.assertEqual(revenue(d)['rule_field']['value'],'123456789.12')


if __name__ == '__main__':
    unittest.main()
