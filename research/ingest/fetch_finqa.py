"""Fetch only allowed development assets from one immutable upstream commit."""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

COMMIT = "0f16e2867befa6840783e58be38c9efb9229d742"
REPOSITORY = "https://github.com/czyssrs/FinQA"
FILES = (
    "dataset/train.json", "dataset/dev.json", "README.md", "LICENSE",
    "code/retriever/finqa_utils.py", "code/utils/general_utils.py",
)
PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT / "research" / "data" / "finqa" / COMMIT
HEADERS = {"User-Agent": "financial-risk-platform-data-audit"}


def fetch(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "acquisition.json"
    previous = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
    previous_files = {entry["path"]: entry for entry in previous.get("files", [])}
    entries = []
    for relative in FILES:
        path = output / relative
        url = f"https://raw.githubusercontent.com/czyssrs/FinQA/{COMMIT}/{relative}"
        if path.exists():
            data = path.read_bytes()
            old = previous_files.get(relative)
            if old is None or hashlib.sha256(data).hexdigest() != old["sha256"]:
                raise ValueError(f"Unverified or changed cached asset: {relative}")
        else:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(128 * 1024 * 1024 + 1)
            if len(data) > 128 * 1024 * 1024:
                raise ValueError(f"Asset exceeds download bound: {relative}")
            if relative.endswith(".json"):
                rows = json.loads(data)
                if not isinstance(rows, list):
                    raise ValueError(f"Expected JSON list: {relative}")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".part")
            temporary.write_bytes(data)
            temporary.replace(path)
        entry = {"path": relative, "url": url, "bytes": len(data),
                 "sha256": hashlib.sha256(data).hexdigest()}
        entries.append(entry)
        previous_files[relative] = entry
        # Persist each verified download, so an interrupted acquisition can resume.
        receipt = {"recorded_date": "2026-10-14", "repository": REPOSITORY,
                   "commit": COMMIT, "allowed_files": list(FILES),
                   "files": [previous_files[name] for name in FILES if name in previous_files],
                   "test_data_fetched": False}
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Verified {relative}: {len(data)} bytes", flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    fetch(arguments.output)
