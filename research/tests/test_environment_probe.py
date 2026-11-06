import importlib
import unittest


class EnvironmentTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module("research.training.probe_environment")
        except ModuleNotFoundError:
            self.fail("Environment probe implementation is missing")

    def resources(self):
        return {"free_ram_bytes": 6 * 1024**3, "free_disk_bytes": 20 * 1024**3,
                "gpus": [{"free_memory_mib": 7000}], "packages": {"torch": "fixture", "transformers": "fixture"},
                "torch_smoke": {"status": "passed", "finite_backward": True}}

    def test_driver_visibility_without_torch_smoke_is_not_ready(self):
        resources = self.resources()
        resources["torch_smoke"] = {"status": "not_run"}
        self.assertFalse(self.module().assess(resources)["ready_for_small_cuda_trial"])

    def test_low_or_unknown_memory_blocks_training_without_hiding_other_checks(self):
        for free in (200 * 1024**2, None):
            resources = self.resources()
            resources["free_ram_bytes"] = free
            result = self.module().assess(resources)
            self.assertFalse(result["ready_for_small_cuda_trial"])
            self.assertIn("free_system_ram", result["blockers"])

    def test_missing_packages_and_no_gpu_are_explicit(self):
        resources = self.resources()
        resources["packages"] = {}
        resources["gpus"] = []
        result = self.module().assess(resources)
        self.assertFalse(result["ready_for_small_cuda_trial"])
        self.assertIn("torch_installed", result["blockers"])
        self.assertIn("transformers_installed", result["blockers"])
        self.assertIn("free_gpu_memory", result["blockers"])

    def test_pass_means_only_small_trial_not_model_fit_or_data_readiness(self):
        result = self.module().assess(self.resources())
        self.assertTrue(result["ready_for_small_cuda_trial"])
        self.assertEqual(result["minimum_free_ram_bytes"], 4 * 1024**3)
        self.assertIn("not", result["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
