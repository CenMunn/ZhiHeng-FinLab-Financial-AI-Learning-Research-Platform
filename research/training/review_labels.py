"""Create training-only review tasks; validate human labels before negative export."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from research.evaluation.audit_finqa import digest
from research.training.prepare_finqa import COMMIT, REPOSITORY, SERIALIZATION, file_sha, json_line, write_json

CONFLICT_TYPES = {"metric", "year", "currency", "unit", "scope"}
IMMUTABLE = ("task_id", "split", "question_id", "evidence_id", "question", "evidence_text",
             "source_context", "annotated_gold_ids", "serialization", "commit")


def make_review_queue(records: list[dict], split: str, gold_by_id: dict[str, list[str]]) -> list[dict]:
    if split != "train":
        raise ValueError("Review queue is train-only")
    queue = []
    for record in sorted(records, key=lambda r: r["question_id"]):
        if record["split"] != "train" or record["serialization"] != SERIALIZATION:
            raise ValueError("Unexpected train record or serialization")
        gold = gold_by_id[record["question_id"]]
        if not gold or not set(gold).issubset(record["candidates"]):
            raise ValueError("Invalid source labels")
        possible = [eid for eid in record["bm25_top20"] if eid not in gold][:3]
        for eid in possible:
            task = {"split": split, "question_id": record["question_id"], "evidence_id": eid,
                    "question": record["question"], "evidence_text": record["candidates"][eid],
                    "source_context": copy.deepcopy(record["candidates"]), "annotated_gold_ids": sorted(gold),
                    "serialization": SERIALIZATION, "commit": COMMIT}
            task["task_id"] = digest(task)
            task.update(label="uncertain", review_status="pending", reviewer=None,
                        reviewer_type=None, rationale=None, conflict_type=None)
            queue.append(task)
    if len({r["task_id"] for r in queue}) != len(queue):
        raise ValueError("Duplicate review task")
    return queue


def validate_reviews(reviews: list[dict], queue: list[dict]) -> dict:
    expected = {row["task_id"]: row for row in queue}
    if len(expected) != len(queue):
        raise ValueError("Duplicate queue task")
    seen, negatives = set(), []
    counts = {"pending": 0, "support": 0, "uncertain": 0, "confirmed_conflict": 0}
    for row in reviews:
        task_id = row.get("task_id")
        if task_id in seen:
            raise ValueError("Duplicate reviewed task")
        seen.add(task_id)
        original = expected.get(task_id)
        if original is None or any(row.get(k) != original[k] for k in IMMUTABLE) or row.get("split") != "train":
            raise ValueError("Review source binding mismatch or non-train task")
        label, status = row.get("label"), row.get("review_status")
        if status == "pending":
            if label != "uncertain" or row.get("conflict_type") is not None:
                raise ValueError("Pending task cannot assert a negative label")
            counts["pending"] += 1
            continue
        if status != "completed" or label not in {"support", "uncertain", "confirmed_conflict"}:
            raise ValueError("Invalid review status or label")
        if (row.get("reviewer_type") != "human" or not isinstance(row.get("reviewer"), str)
                or not row["reviewer"].strip() or not isinstance(row.get("rationale"), str)
                or not row["rationale"].strip()):
            raise ValueError("Completed label requires human reviewer and rationale")
        if label == "confirmed_conflict":
            if row.get("conflict_type") not in CONFLICT_TYPES:
                raise ValueError("Confirmed conflict requires a supported conflict type")
            negatives.append({key: row[key] for key in ("task_id", "question_id", "evidence_id",
                "question", "evidence_text", "reviewer", "rationale", "conflict_type", "serialization", "commit")})
        elif row.get("conflict_type") is not None:
            raise ValueError("Non-conflict label cannot carry conflict type")
        counts[label] += 1
    return {**counts, "missing": len(expected) - len(seen), "tasks": len(expected),
            "confirmed_negatives": negatives, "claim_boundary": "Structural label validation; reviewer identity and financial judgment require external human accountability."}


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def create_package(prepared: Path, pilot: Path, output: Path) -> dict:
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    identity = {"schema_version": "m2-preparation-v1", "repository": REPOSITORY, "commit": COMMIT,
                "serialization": SERIALIZATION, "candidate_scope": "provided_page",
                "test_content_accessed": False, "gold_added_to_inference_candidates": False}
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise ValueError("Prepared manifest identity mismatch")
    for name in ("inference/train.jsonl", "labels/train.jsonl"):
        if file_sha(prepared / name) != manifest["outputs_sha256"][name]:
            raise ValueError("Changed prepared training source")
    pilot_rows = [r for r in json.loads(pilot.read_text(encoding="utf-8")) if r["split"] == "train"]
    selected = {r["question_id"] for r in pilot_rows}
    expected = manifest.get("fixed_pilot_question_ids", {}).get("train", [])
    if len(pilot_rows) != 30 or len(selected) != 30 or selected != set(expected):
        raise ValueError("Expected existing fixed 30-question training pilot; no substitutions allowed")
    records = [r for r in read_lines(prepared / "inference/train.jsonl") if r["question_id"] in selected]
    if {r["question_id"] for r in records} != selected:
        raise ValueError("Pilot contains ineligible or missing questions")
    labels = {r["question_id"]: r["gold_ids"] for r in read_lines(prepared / "labels/train.jsonl")}
    queue = make_review_queue(records, "train", labels)
    serialized = "".join(json_line(row) for row in queue)
    output.mkdir(parents=True, exist_ok=True)
    queue_path = output / "queue.jsonl"
    if queue_path.exists() and queue_path.read_text(encoding="utf-8") != serialized:
        raise ValueError("Existing queue differs; create a new versioned review package")
    queue_path.write_text(serialized, encoding="utf-8", newline="\n")
    draft_path = output / "reviews.jsonl"
    if not draft_path.exists():
        draft_path.write_text(serialized, encoding="utf-8", newline="\n")
    receipt = {"commit": COMMIT, "serialization": SERIALIZATION,
               "prepared_manifest_sha256": file_sha(prepared / "manifest.json"),
               "pilot_sha256": file_sha(pilot), "queue_sha256": file_sha(queue_path),
               "questions": len(records), "tasks": len(queue), "sampling": "existing fixed train pilot, up to three non-gold BM25 top20 candidates per question",
               "labels_confirmed_by_generation": 0}
    write_json(output / "receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("queue", "check"))
    parser.add_argument("--prepared", type=Path, default=PROJECT / "research/artifacts/m2-preparation-20261015")
    parser.add_argument("--pilot", type=Path, default=PROJECT / "research/artifacts/finqa-audit-20261014/pilot-review.json")
    parser.add_argument("--output", type=Path, default=PROJECT / "research/artifacts/m2-preparation-20261015/review")
    args = parser.parse_args()
    if args.action == "queue":
        result = create_package(args.prepared, args.pilot, args.output)
    else:
        receipt = json.loads((args.output / "receipt.json").read_text(encoding="utf-8"))
        if file_sha(args.output / "queue.jsonl") != receipt["queue_sha256"]:
            raise ValueError("Changed immutable review queue")
        result = validate_reviews(read_lines(args.output / "reviews.jsonl"), read_lines(args.output / "queue.jsonl"))
        result["reviews_sha256"] = file_sha(args.output / "reviews.jsonl")
        result["receipt_sha256"] = file_sha(args.output / "receipt.json")
        write_json(args.output / "validation.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "confirmed_negatives"}, indent=2))
