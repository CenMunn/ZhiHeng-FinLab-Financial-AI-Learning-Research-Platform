"""Deterministic source-only inputs and separate labels for FinQA page ranking."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from research.evaluation.audit_finqa import build_candidates, bm25_rank, digest, parse_id
from research.ingest.fetch_finqa import COMMIT, FILES, REPOSITORY

SERIALIZATION = "finqa-header-aware-v1"


def file_sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def json_line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"


def verified_receipt(data: Path) -> dict:
    receipt = json.loads((data / "acquisition.json").read_text(encoding="utf-8"))
    if (receipt.get("commit") != COMMIT or receipt.get("repository") != REPOSITORY
            or receipt.get("test_data_fetched") is not False):
        raise ValueError("Unexpected source identity")
    entries = receipt.get("files", [])
    names = [entry["path"] for entry in entries]
    if (len(names) != len(FILES) or set(names) != set(FILES)
            or set(receipt.get("allowed_files", [])) != set(FILES)):
        raise ValueError("Source allowlist mismatch")
    for entry in entries:
        path = data / entry["path"]
        expected_url = f"https://raw.githubusercontent.com/czyssrs/FinQA/{COMMIT}/{entry['path']}"
        if (entry.get("url") != expected_url or path.stat().st_size != entry.get("bytes")
                or file_sha(path) != entry.get("sha256")):
            raise ValueError(f"Changed source: {entry['path']}")
    return receipt


def company_diagnostic(ids: list[str]) -> dict:
    companies = sorted({parse_id(q)["company_id"] for q in ids},
                       key=lambda c: digest([COMMIT, "company-diagnostic-v1", c]))
    count = min(len(companies) - 1, max(1, math.ceil(len(companies) * .2))) if len(companies) > 1 else 0
    validation = set(companies[:count])
    return {"protocol": "train-only-company-holdout-v1", "available": len(companies) > 1,
            "group_semantics": "company proxy from FinQA ID; not certified filing identity",
            "validation_companies": sorted(validation),
            "fit_ids": sorted(q for q in ids if parse_id(q)["company_id"] not in validation),
            "validation_ids": sorted(q for q in ids if parse_id(q)["company_id"] in validation)}


def prepare(data: Path, output: Path) -> dict:
    data, output = data.resolve(), output.resolve()
    if data.is_relative_to(output) or output.is_relative_to(data):
        raise ValueError("Source and output directories must be disjoint")
    receipt = verified_receipt(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    ids, over_five, quarantine_counts, frozen_pilot_ids = {}, {}, Counter(), {}
    with tempfile.TemporaryDirectory(prefix="m2-prep-", dir=output.parent) as scratch:
        stage = Path(scratch)
        (stage / "inference").mkdir()
        (stage / "labels").mkdir()
        with (stage / "quarantine.jsonl").open("w", encoding="utf-8", newline="\n") as quarantined:
            for split in ("train", "dev"):
                rows = json.loads((data / "dataset" / f"{split}.json").read_text(encoding="utf-8"))
                if not isinstance(rows, list):
                    raise ValueError("Expected source list")
                # Match the original pilot BEFORE eligibility filtering. Never replenish exclusions.
                frozen_pilot_ids[split] = [record["id"] for record in sorted(
                    rows, key=lambda record: digest([COMMIT, split, record["id"]]))[:30]]
                duplicates = Counter(record.get("id", "") for record in rows)
                ids[split], over_five[split] = [], 0
                with (stage / f"inference/{split}.jsonl").open("w", encoding="utf-8", newline="\n") as inputs, \
                     (stage / f"labels/{split}.jsonl").open("w", encoding="utf-8", newline="\n") as labels:
                    for record in rows:
                        identifier = record.get("id", "")
                        reasons, missing = [], []
                        try:
                            groups = parse_id(identifier)
                            candidates = build_candidates(record)
                        except (ValueError, KeyError, TypeError) as exc:
                            reasons.append(f"invalid_source_structure:{type(exc).__name__}")
                            groups, candidates = {}, {}
                        qa = record.get("qa", {})
                        question, gold = qa.get("question"), qa.get("gold_inds")
                        if duplicates[identifier] != 1:
                            reasons.append("duplicate_question_id")
                        if not isinstance(question, str) or not question.strip():
                            reasons.append("empty_or_invalid_question")
                        if not isinstance(gold, dict) or not gold:
                            reasons.append("empty_or_invalid_gold")
                        else:
                            missing = sorted(set(gold) - set(candidates))
                            if missing:
                                reasons.append("missing_gold_id")
                        if not candidates:
                            reasons.append("empty_candidates")
                        if reasons:
                            quarantine_counts[split] += 1
                            quarantined.write(json_line({"split": split, "question_id": identifier,
                                "reasons": reasons, "missing_gold_ids": missing, "source_record_sha256": digest(record)}))
                            continue
                        ranked = bm25_rank(question, candidates)
                        ids[split].append(identifier)
                        over_five[split] += int(len(gold) > 5)
                        inputs.write(json_line({**groups, "split": split, "question": question,
                            "candidate_scope": "provided_page", "serialization": SERIALIZATION,
                            "candidates": candidates, "bm25_top20": ranked[:20]}))
                        labels.write(json_line({"question_id": identifier, "gold_ids": sorted(gold),
                            "label_origin": "upstream_gold_ids_not_exhaustive_relevance", "split": split}))
                del rows
        if set(ids["train"]) & set(ids["dev"]):
            raise ValueError("Question IDs overlap between official splits")
        splits = {"official": {split: sorted(value) for split, value in ids.items()},
                  "train_company_diagnostic": company_diagnostic(ids["train"])}
        write_json(stage / "splits.json", splits)
        files = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*.json*"))
        manifest = {"schema_version": "m2-preparation-v1", "repository": REPOSITORY, "commit": COMMIT,
            "source_files": receipt["files"], "source_receipt_sha256": file_sha(data / "acquisition.json"),
            "preparation_script_sha256": file_sha(Path(__file__)),
            "serialization_script_sha256": file_sha(PROJECT / "research/evaluation/audit_finqa.py"),
            "serialization": SERIALIZATION, "candidate_scope": "provided_page",
            "eligible_counts": {split: len(value) for split, value in ids.items()},
            "quarantine_counts": {split: quarantine_counts[split] for split in ids},
            "gold_over_five_counts": over_five,
            "fixed_pilot_question_ids": frozen_pilot_ids,
            "outputs_sha256": {name: file_sha(stage / name) for name in files},
            "test_content_accessed": False, "gold_added_to_inference_candidates": False,
            "negative_labels_confirmed": 0,
            "claim_boundary": "Prepared data, not training or model performance. Official and company diagnostic protocols are distinct."}
        write_json(stage / "manifest.json", manifest)
        # Publish only after all sources/rows validate; manifest is the final commit marker.
        for name in files + ["manifest.json"]:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            (stage / name).replace(target)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=PROJECT / "research/data/finqa" / COMMIT)
    parser.add_argument("--output", type=Path, default=PROJECT / "research/artifacts/m2-preparation-20261015")
    args = parser.parse_args()
    result = prepare(args.data, args.output)
    print(json.dumps({key: result[key] for key in ("eligible_counts", "quarantine_counts", "gold_over_five_counts")}, indent=2))
