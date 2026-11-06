import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts/import_committee.py"


class ImportTests(unittest.TestCase):
    def test_local_rebuild_preserves_upstream_manifest_and_account_bindings(self):
        source, runtime, project = self.fixture()
        project.mkdir()
        app = project / 'apps/committee'
        app.parent.mkdir()
        source.rename(app)
        external = app / 'node_modules/pdf-parse'
        external.mkdir(parents=True)
        (external / 'package.json').write_text('{"name":"pdf-parse","main":"index.js"}')
        (external / 'index.js').write_text('module.exports="pdf-parser-fixture"')
        build = app / '.next-fixture'
        build.mkdir()
        runtime.rename(build / 'standalone')
        (build / 'static').mkdir()
        (build / 'static/chunk.js').write_text('new browser code')
        (project / 'integrations').mkdir()
        upstream = {'release': 'upstream', 'build_id': 'old', 'source_files': {}}
        (project / 'integrations/committee-manifest.json').write_text(json.dumps(upstream))
        local = project / '.local/committee'
        local.mkdir(parents=True)
        config = {'runtimeDir': str(local / 'old'), 'databasePath': 'DO_NOT_TOUCH', 'envFile': 'NEVER_READ'}
        (local / 'config.json').write_text(json.dumps(config))
        result = self.module().package_local_build(project, '.next-fixture', 'local-fix')
        self.assertEqual(result['release'], 'local-fix')
        self.assertEqual(result['upstream_build_id'], 'old')
        self.assertEqual(json.loads((project / 'integrations/committee-upstream-manifest.json').read_text()), upstream)
        current = json.loads((local / 'config.json').read_text())
        self.assertEqual(current['databasePath'], 'DO_NOT_TOUCH')
        self.assertEqual(current['envFile'], 'NEVER_READ')
        self.assertTrue((Path(current['runtimeDir']) / '.next-fixture/static/chunk.js').is_file())
        self.assertTrue((Path(current['runtimeDir']) / 'public/logo.svg').is_file())
        self.assertTrue((Path(current['runtimeDir']) / 'node_modules/pdf-parse/index.js').is_file())
        self.assertFalse((Path(current['runtimeDir']) / '.env').exists())
        with self.assertRaises(ValueError):
            self.module().package_local_build(project, '.next-fixture', 'overwrite')

    def module(self):
        if not MODULE.exists():
            self.fail("Committee importer is missing")
        spec = importlib.util.spec_from_file_location("committee_import", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        source, runtime, target = root / "source", root / "runtime", root / "project"
        files = {source / "src/app/page.tsx": "export default function Page(){}",
                 source / "src/app/api/auth/me/route.ts": "auth route",
                 source / "src/app/forecast/page.tsx": "forecast page",
                 source / "public/logo.svg": "logo", source / "package.json": '{"dependencies":{"next":"16","react":"19"}}',
                 source / ".env": "SECRET", source / "db/research.db": "PRIVATE",
                 source / 'prisma/research.db': 'PRIVATE_DATABASE',
                 source / 'src/private.pdf': 'PRIVATE_PDF',
                 source / "src/.env.local": "SECRET", source / "src/heldout/answers.json": "HOLDOUT",
                 runtime / "server.js": "server", runtime / ".next-fixture/BUILD_ID": "fixture-build",
                 runtime / ".next-fixture/server/app/page.js": "built page", runtime / ".env": "SECRET"}
        for p, content in files.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return source, runtime, target

    def test_only_application_assets_are_copied_and_secrets_never_read(self):
        source, runtime, target = self.fixture()
        result = self.module().import_snapshot(source, runtime, target, ".next-fixture")
        paths = [p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()]
        self.assertTrue((target / "apps/committee/src/app/page.tsx").exists())
        self.assertTrue((target / ".local/committee/runtime/server.js").exists())
        self.assertFalse(any(".env" in p or "heldout" in p or "research.db" in p or p.endswith('.pdf') for p in paths))
        self.assertEqual(result["build_id"], "fixture-build")
        self.assertIn("/forecast", result["pages"])
        self.assertIn("/api/auth/me", result["api_routes"])

    def test_rerun_is_identical_and_changed_target_is_not_overwritten(self):
        source, runtime, target = self.fixture()
        first = self.module().import_snapshot(source, runtime, target, ".next-fixture")
        self.assertEqual(first, self.module().import_snapshot(source, runtime, target, ".next-fixture"))
        (target / "apps/committee/src/app/page.tsx").write_text("local edits")
        with self.assertRaisesRegex(ValueError, "Changed"):
            self.module().import_snapshot(source, runtime, target, ".next-fixture")
        self.assertEqual((target / "apps/committee/src/app/page.tsx").read_text(), "local edits")

    def test_output_must_not_overlap_source_and_build_id_is_required(self):
        source, runtime, target = self.fixture()
        with self.assertRaises(ValueError):
            self.module().import_snapshot(source, runtime, source, ".next-fixture")
        (runtime / ".next-fixture/BUILD_ID").unlink()
        with self.assertRaises(ValueError):
            self.module().import_snapshot(source, runtime, target, ".next-fixture")

    def test_runtime_dependency_links_are_materialized_only_from_allowed_package_root(self):
        source, runtime, target = self.fixture()
        dependency = source / "node_modules/next"
        dependency.mkdir(parents=True)
        (dependency / "package.json").write_text('{"name":"next","dependencies":{"fixture-helper":"1"},"peerDependencies":{"fixture-peer":"1"}}')
        helper=source / 'node_modules/fixture-helper'
        helper.mkdir()
        (helper / 'package.json').write_text('{"name":"fixture-helper"}')
        (helper / 'index.js').write_text('module.exports=1')
        peer=source / 'node_modules/fixture-peer'
        peer.mkdir()
        (peer/'package.json').write_text('{"name":"fixture-peer"}')
        (runtime / "node_modules").mkdir()
        try:
            (runtime / "node_modules/next").symlink_to(dependency, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("Directory symlink creation unavailable")
            subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(runtime / "node_modules/next"), str(dependency)],
                           check=True, capture_output=True)
        self.module().import_snapshot(source, runtime, target, ".next-fixture")
        self.assertTrue((target / ".local/committee/runtime/node_modules/next/package.json").is_file())
        self.assertFalse((target / ".local/committee/runtime/node_modules/next").is_symlink())
        self.assertTrue((target / '.local/committee/runtime/node_modules/next/node_modules/fixture-helper/index.js').is_file())
        self.assertTrue((target / '.local/committee/runtime/node_modules/next/node_modules/fixture-peer/package.json').is_file())

    def test_parent_directory_link_cannot_escape_destination(self):
        source, runtime, target = self.fixture()
        outside=target.parent/'outside'
        outside.mkdir()
        parent=target/'apps/committee'
        parent.mkdir(parents=True)
        link=parent/'src'
        try:
            link.symlink_to(outside,target_is_directory=True)
        except OSError:
            if os.name != 'nt':self.skipTest('Directory links unavailable')
            subprocess.run(['cmd.exe','/c','mklink','/J',str(link),str(outside)],check=True,capture_output=True)
        with self.assertRaisesRegex(ValueError,'destination'):
            self.module().import_snapshot(source,runtime,target,'.next-fixture')
        self.assertEqual(list(outside.iterdir()),[])

    def test_generated_prisma_client_follows_package_realpath_without_database_copy(self):
        source,runtime,target=self.fixture()
        package=source/'node_modules/.pnpm/client/node_modules/@prisma/client'
        package.mkdir(parents=True)
        (package/'package.json').write_text('{"name":"@prisma/client"}')
        generated=package.parent.parent/'.prisma/client'
        generated.mkdir(parents=True)
        (generated/'default.js').write_text('generated client')
        (generated/'private.db').write_text('must never copy')
        link=runtime/'node_modules/@prisma/client'
        link.parent.mkdir(parents=True)
        try:link.symlink_to(package,target_is_directory=True)
        except OSError:
            if os.name!='nt':self.skipTest('Directory links unavailable')
            subprocess.run(['cmd.exe','/c','mklink','/J',str(link),str(package)],check=True,capture_output=True)
        self.module().import_snapshot(source,runtime,target,'.next-fixture')
        copied=target/'.local/committee/runtime/node_modules/@prisma/client/node_modules/.prisma/client'
        self.assertTrue((copied/'default.js').is_file())
        self.assertFalse((copied/'private.db').exists())


if __name__ == "__main__":
    unittest.main()
