"""Lightweight resource inventory; optional explicit CUDA forward/backward check."""
from __future__ import annotations

import argparse
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
GIB = 1024**3


def assess(resources: dict) -> dict:
    packages = resources.get("packages", {})
    ram, disk = resources.get("free_ram_bytes"), resources.get("free_disk_bytes")
    smoke = resources.get("torch_smoke", {})
    checks = {"free_system_ram": ram is not None and ram >= 4 * GIB,
              "free_disk": disk is not None and disk >= 10 * GIB,
              "free_gpu_memory": bool(resources.get("gpus")) and resources["gpus"][0].get("free_memory_mib", 0) >= 4096,
              "torch_installed": bool(packages.get("torch")),
              "transformers_installed": bool(packages.get("transformers")),
              "cuda_forward_backward": smoke.get("status") == "passed" and smoke.get("finite_backward") is True}
    return {"ready_for_small_cuda_trial": all(checks.values()), "checks": checks,
            "blockers": [name for name, passed in checks.items() if not passed],
            "minimum_free_ram_bytes": 4 * GIB, "minimum_free_disk_bytes": 10 * GIB,
            "minimum_free_gpu_memory_mib": 4096,
            "claim_boundary": "Heuristic gate for a small CUDA trial, not model-specific memory fit, dataset approval, or a training result."}


def memory_info() -> dict:
    if os.name != "nt":
        return {"total_ram_bytes": None, "free_ram_bytes": None, "memory_measurement": "unsupported_platform"}
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ("total_phys", "avail_phys", "total_page", "avail_page",
                                                  "total_virtual", "avail_virtual", "avail_extended")]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return {"total_ram_bytes": None, "free_ram_bytes": None, "memory_measurement": "failed"}
    return {"total_ram_bytes": status.total_phys, "free_ram_bytes": status.avail_phys,
            "memory_measurement": "GlobalMemoryStatusEx instantaneous available physical bytes"}


def gpu_info() -> tuple[list[dict], str | None]:
    command = shutil.which("nvidia-smi")
    if command is None:
        return [], "nvidia-smi not found"
    try:
        result = subprocess.run([command, "--query-gpu=name,memory.total,memory.free,driver_version,compute_cap",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15, check=True)
        gpus = []
        for fields in csv.reader(result.stdout.splitlines(), skipinitialspace=True):
            name, total, free, driver, capability = fields
            gpus.append({"name": name, "total_memory_mib": int(total), "free_memory_mib": int(free),
                         "driver_version": driver, "compute_capability": capability})
        return gpus, None
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [], f"GPU query failed: {type(exc).__name__}"


def cuda_smoke() -> dict:
    try:
        import torch
        if not torch.cuda.is_available():
            return {"status": "failed", "reason": "torch.cuda.is_available=False"}
        device = torch.device("cuda:0")
        with torch.enable_grad():
            value = torch.randn(64, 64, device=device, requires_grad=True)
            loss = (value @ value.T).square().mean()
            loss.backward()
            torch.cuda.synchronize()
            finite = bool(torch.isfinite(loss).item() and torch.isfinite(value.grad).all().item())
        return {"status": "passed" if finite else "failed", "finite_backward": finite,
                "torch_version": torch.__version__, "torch_cuda_runtime": torch.version.cuda,
                "device": torch.cuda.get_device_name(0), "device_capability": list(torch.cuda.get_device_capability(0)),
                "compiled_architectures": torch.cuda.get_arch_list(),
                "bf16_supported": torch.cuda.is_bf16_supported(),
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(0)}
    except Exception as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def probe(output: Path, torch_smoke: bool = False) -> dict:
    packages = {}
    for package in ("torch", "transformers", "tokenizers", "safetensors", "sentence-transformers", "numpy"):
        try:
            packages[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            packages[package] = None
    gpus, gpu_error = gpu_info()
    resources = {**memory_info(), "free_disk_bytes": shutil.disk_usage(PROJECT).free,
                 "gpus": gpus, "gpu_query_error": gpu_error, "packages": packages,
                 "torch_smoke": {"status": "not_run"}}
    if torch_smoke:
        if packages["torch"] is None:
            resources["torch_smoke"] = {"status": "skipped", "reason": "torch not installed"}
        elif resources["free_ram_bytes"] is None or resources["free_ram_bytes"] < 4 * GIB:
            resources["torch_smoke"] = {"status": "skipped", "reason": "insufficient or unknown free physical RAM"}
        else:
            resources["torch_smoke"] = cuda_smoke()
    report = {"schema_version": "training-environment-probe-v1", "recorded_at": datetime.now(timezone.utc).isoformat(),
              "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "platform": platform.system(), "platform_release": platform.release(),
              "python": platform.python_version(), "logical_processors": os.cpu_count(),
              "resources": resources, "assessment": assess(resources)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "research/artifacts/m2-preparation-20261015/environment.json")
    parser.add_argument("--torch-smoke", action="store_true", help="Explicitly import torch and exercise CUDA forward/backward if RAM permits")
    args = parser.parse_args()
    print(json.dumps(probe(args.output, args.torch_smoke), indent=2))
