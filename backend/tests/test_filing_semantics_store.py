import json
import tempfile
import unittest
from pathlib import Path


class SemanticsStoreTests(unittest.TestCase):
    def test_empty_and_missing_never_show_metrics(self):
        from platform_app.adapters.filing_semantics_store import FilingSemanticsStore
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=FilingSemanticsStore(root/'backend/data/filing-semantics',root)
            self.assertEqual(store.get()['artifact_status'],'empty')
            folder=store.folder;folder.mkdir(parents=True)
            (folder/'latest.json').write_text(json.dumps({'studies':{'development':{'file':'filingsem-'+('a'*64)+'.json','sha256':'b'*64}}}),'utf8')
            body=store.get();self.assertEqual(body['artifact_status'],'missing');self.assertIsNone(body['record'])

    def test_unsafe_pointer_and_changed_bytes_fail_closed(self):
        from platform_app.adapters.filing_semantics_store import FilingSemanticsStore
        from platform_app.contracts.errors import DomainConflict
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'backend/data/filing-semantics';folder.mkdir(parents=True);store=FilingSemanticsStore(folder,root)
            for name in ['../account.json','C:/secret.json','filingsem-'+('a'*64)+'.json']:
                (folder/'latest.json').write_text(json.dumps({'studies':{'development':{'file':name,'sha256':'b'*64}}}),'utf8')
                if name.startswith('filingsem'): (folder/name).write_text('{}','utf8')
                with self.assertRaises(DomainConflict):store.get()

    def test_pdf_only_from_verified_registered_document(self):
        from platform_app.adapters.filing_semantics_store import FilingSemanticsStore
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=FilingSemanticsStore(root/'backend/data/filing-semantics',root)
            with self.assertRaises(KeyError):store.pdf('../secrets')

if __name__=='__main__':unittest.main()
