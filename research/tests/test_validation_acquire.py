import json
from pathlib import Path
import tempfile
import unittest
from research.validation_foundation.acquire import cache, parse_events, parse_tencent, normalization_sources, PROJECT, digest


class AcquisitionIntegrityTests(unittest.TestCase):
    def test_normalization_sources_bind_parser_and_contract_dependencies(self):
        sources = normalization_sources()
        self.assertEqual(set(sources), {
            'research/validation_foundation/acquire.py',
            'backend/src/platform_app/adapters/public_market.py',
            'backend/src/platform_app/contracts/public_backtests.py',
            'backend/src/platform_app/contracts/market_experiments.py',
            'backend/src/platform_app/contracts/models.py',
        })
        for path, sha in sources.items():
            self.assertEqual(sha, digest((PROJECT / path).read_bytes()))

    def test_cache_refuses_url_or_payload_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, receipt = cache(root, 'source.json', 'https://example.test/fixed', supplied=b'original')
            self.assertEqual(cache(root, 'source.json', receipt['url'])[0], raw)
            with self.assertRaisesRegex(ValueError, 'URL/SHA/path mismatch'):
                cache(root, 'source.json', 'https://example.test/other')
            (root / receipt['file']).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'URL/SHA/path mismatch'):
                cache(root, 'source.json', receipt['url'])

    def test_orphan_cache_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'raw').mkdir()
            (root / 'raw/source').write_bytes(b'partial')
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                cache(root, 'source', 'https://example.test/fixed', supplied=b'partial')

    def test_tencent_requires_requested_identity_and_unadjusted_day(self):
        adjusted = json.dumps({'code': 0, 'data': {'sh600036': {'qfqday': [['2020-01-02', '1', '1', '1', '1', '1']]}}}).encode()
        with self.assertRaises(KeyError):
            parse_tencent(adjusted, '600036')
        wrong = json.dumps({'code': 0, 'data': {'sh600519': {'day': []}}}).encode()
        with self.assertRaises(KeyError):
            parse_tencent(wrong, '600036')

    def test_split_events_are_retained_and_symbol_checked(self):
        body = {'chart': {'error': None, 'result': [{'meta': {'symbol': '600276.SS', 'currency': 'CNY', 'exchangeTimezoneName': 'Asia/Shanghai'}, 'events': {'splits': {'a': {'date': 1577928600, 'numerator': 13, 'denominator': 10}}}}]}}
        raw = json.dumps(body).encode()
        dividends, splits = parse_events(raw, '600276')
        self.assertEqual(dividends, [])
        self.assertEqual(splits[0]['ratio'], '1.3')
        with self.assertRaisesRegex(ValueError, 'identity'):
            parse_events(raw, '600036')
