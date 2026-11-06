import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def fixture(revenue="3650000", year=2025):
    from platform_app.contracts.models import CaseSnapshot, EvidenceLocator
    start, end = date(year, 1, 1), date(year, 12, 31)
    return CaseSnapshot(snapshot_id="fixture", snapshot_sha256="a"*64,
        company_id="fixture", company_name="合成测试企业", report_id="fixture",
        period_start=start, period_end=end, days=(end-start).days+1,
        revenue=revenue, evidence=EvidenceLocator(source_id="fixture", source_url="https://example.com/report.pdf",
        source_sha256="b"*64, value_page=1, header_pages=(1,), excerpt="Synthetic revenue",
        review_status="synthetic", availability_status="not_applicable", version_status="synthetic"),
        limitations=("合成测试夹具",), source_kind="synthetic")


class ReceivablesTests(unittest.TestCase):
    def calculate(self, revenue="3650000", q="0.8", delay="15", year=2025):
        from platform_app.contracts.models import DelayAssumptions
        from platform_app.risk.receivables import calculate_delay
        return calculate_delay(fixture(revenue, year), DelayAssumptions(credit_share=q, delay_days=delay))

    def test_reference_and_round_only_at_end(self):
        self.assertEqual(self.calculate().occupancy_change, "120000.00")
        self.assertEqual(self.calculate().cash_equivalent_change, "-120000.00")
        self.assertEqual(self.calculate("100", "1", "90").occupancy_change, "24.66")

    def test_zero_leap_year_and_monotonicity(self):
        from decimal import Decimal
        self.assertEqual(self.calculate(q="0").occupancy_change, "0.00")
        self.assertEqual(self.calculate(delay="0").occupancy_change, "0.00")
        self.assertEqual(self.calculate("3660000", "1", "1", 2024).occupancy_change, "10000.00")
        amounts=[Decimal(self.calculate(delay=str(day)).occupancy_change) for day in (0,1,15,30,90)]
        self.assertEqual(amounts, sorted(amounts))

    def test_canonical_parameters_and_hash(self):
        self.assertEqual(self.calculate(q="0.80",delay="15.00").input_hash, self.calculate().input_hash)
        self.assertEqual(self.calculate(q="-0").assumptions.credit_share, "0")
        self.assertNotEqual(self.calculate(q="0.7").input_hash, self.calculate().input_hash)
        self.assertNotEqual(self.calculate(revenue="3650001").input_hash, self.calculate().input_hash)

    def test_parameter_boundaries_reject_coercion_and_unsupported_syntax(self):
        from platform_app.contracts.models import DelayAssumptions
        from pydantic import ValidationError
        for q in (None, True, 0.8, "", "1.1", "-0.1", "1e-1", "NaN", "Infinity", "0.1234567", " 0.8", "0"*33):
            with self.subTest(q=q), self.assertRaises(ValidationError):
                DelayAssumptions(credit_share=q, delay_days="15")
        for day in (15, "-1", "91", "0.001", "1e1"):
            with self.subTest(day=day), self.assertRaises(ValidationError):
                DelayAssumptions(credit_share="0.8", delay_days=day)

    def test_snapshot_period_and_money_constraints(self):
        from pydantic import ValidationError
        for revenue in ("-1", "1234567890123456789", "0.1234567", 3650000):
            with self.subTest(revenue=revenue), self.assertRaises(ValidationError):
                fixture(revenue)
        payload=fixture().model_dump(mode="json")
        payload["days"]=366
        with self.assertRaises(ValidationError):
            type(fixture())(**payload)
        payload=fixture().model_dump(mode="json")
        payload["scope"]="parent"
        with self.assertRaises(ValidationError):
            type(fixture())(**payload)

    def test_frozen_snapshot_nested_evidence_and_forbidden_request_fields(self):
        from platform_app.contracts.models import CalculationRequest
        from pydantic import ValidationError
        case=fixture()
        with self.assertRaises(ValidationError): case.revenue="100"
        with self.assertRaises(ValidationError): case.evidence.value_page=999
        with self.assertRaises(ValidationError):
            CalculationRequest(snapshot_id="fixture",expected_snapshot_sha256="a"*64,
                assumptions={"credit_share":"0.8","delay_days":"15"},revenue="1")

    def test_server_curve_matches_current_result_without_frontend_math(self):
        result=self.calculate()
        points={point.delay_days:point.occupancy_change for point in result.sensitivity_curve}
        self.assertEqual(points["15"],result.occupancy_change)
        self.assertEqual(points["0"],"0.00")
        self.assertEqual(points["90"],"720000.00")


if __name__ == "__main__": unittest.main()
