import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


class CommitteeStatusTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('platform_app.integrations.committee')
        except ModuleNotFoundError:
            self.fail('Committee integration status is missing')

    def test_only_fixed_loopback_origins_are_accepted(self):
        m = self.module()
        for origin in ('https://example.com', 'http://127.0.0.1:3155/else', 'http://user@127.0.0.1:3155', 'file:///test'):
            with self.assertRaises(ValueError):
                m.get_committee_status(origin, 'build', lambda url: {})

    def test_offline_and_wrong_service_do_not_claim_available(self):
        m = self.module()
        def offline(url):
            raise TimeoutError()
        self.assertFalse(m.get_committee_status('http://127.0.0.1:3155', 'build', offline)['available'])
        self.assertFalse(m.get_committee_status('http://127.0.0.1:3155', 'build', lambda url: {'ready':True})['available'])

    def test_build_mismatch_is_distinct_from_healthy(self):
        m = self.module()
        body = {'module':'committee','buildId':'old','ready':True}
        result = m.get_committee_status('http://127.0.0.1:3155', 'new', lambda url: body)
        self.assertFalse(result['available'])
        self.assertEqual(result['state'], 'version_mismatch')
        body['buildId'] = 'new'
        self.assertTrue(m.get_committee_status('http://127.0.0.1:3155', 'new', lambda url: body)['available'])

    def test_unready_upstream_and_missing_manifest_stay_offline(self):
        m = self.module()
        self.assertFalse(m.get_committee_status('http://127.0.0.1:3155', '', lambda url: self.fail('must not probe'))['available'])
        self.assertFalse(m.get_committee_status('http://127.0.0.1:3155', 'x', lambda url: {'module':'committee','buildId':'x','ready':False})['available'])


if __name__ == '__main__':
    unittest.main()
