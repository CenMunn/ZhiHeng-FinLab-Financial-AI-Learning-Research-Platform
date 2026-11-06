import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class LauncherTests(unittest.TestCase):
    def test_restarting_completed_experiment_cannot_overwrite_its_state(self):
        shell=shutil.which('pwsh') or shutil.which('powershell')
        if shell is None: self.skipTest('PowerShell unavailable')
        source=Path(__file__).resolve().parents[1]/'run_b012.ps1'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); research=root/'research'; output=research/'artifacts/b012-20261030'
            (output/'b2-seed-42').mkdir(parents=True)
            state=output/'pipeline-state.json'; state.write_text('{"status":"completed"}')
            script=research/'run_b012.ps1'; shutil.copyfile(source,script)
            # No Python executable or wheel exists in the fixture: this must fail
            # before dependency installation, model loading or any real dataset access.
            process=subprocess.run([shell,'-NoProfile','-File',str(script)],capture_output=True,timeout=20)
            self.assertNotEqual(process.returncode,0)
            self.assertEqual(json.loads(state.read_text()),{'status':'completed'})


if __name__=='__main__': unittest.main()
