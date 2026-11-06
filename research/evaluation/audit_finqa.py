"""Train/dev-only structure audit and 60-question lexical pilot; not final scoring."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[2]
COMMIT = "0f16e2867befa6840783e58be38c9efb9229d742"
TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?")


def parse_id(identifier: str) -> dict[str, str]:
    match = re.fullmatch(r"([^/]+)/(\d{4})/(page_\d+\.pdf)-(\d+)", identifier)
    if not match:
        raise ValueError(f"Unsupported FinQA ID: {identifier}")
    company, year, page, number = match.groups()
    return {"company_id": company, "annual_report_id": f"{company}/{year}",
            "page_id": f"{company}/{year}/{page}", "question_id": identifier}


def build_candidates(record: dict) -> dict[str, str]:
    """Use source only. Match upstream's header-aware row template for ALL rows.

    Template attribution: FinQA code/utils/general_utils.py at COMMIT (MIT).
    Gold texts and upstream retrieved/model_input fields are deliberately unused.
    """
    candidates = {}
    text = record["pre_text"] + record["post_text"]
    for index, sentence in enumerate(text):
        if not isinstance(sentence, str):
            raise ValueError("Non-string source text")
        candidates[f"text_{index}"] = sentence
    table = record["table"]
    if table:
        header = table[0]
        if not header or not all(isinstance(cell, str) for cell in header):
            raise ValueError("Invalid table header")
        for index, row in enumerate(table):
            if len(row) != len(header) or not all(isinstance(cell, str) for cell in row):
                raise ValueError("Ragged or non-string table row")
            prefix = header[0] + " " if header[0] else ""
            clauses = [f"the {row[0]} of {head} is {cell} ; "
                       for head, cell in zip(header[1:], row[1:])]
            candidates[f"table_{index}"] = " ".join((prefix + "".join(clauses)).split())
    return candidates


def coverage(gold: set[str], ranked: list[str]) -> int:
    if not gold:
        raise ValueError("Empty evidence labels cannot define coverage")
    return int(gold.issubset(set(ranked)))


def bm25_rank(question: str, candidates: dict[str, str]) -> list[str]:
    """Page-local Robertson positive-IDF BM25, k1=1.2,b=.75; stable source ties."""
    keys = list(candidates)
    documents = [Counter(TOKEN.findall(candidates[key].lower())) for key in keys]
    query = Counter(TOKEN.findall(question.lower()))
    n = len(documents)
    if not n:
        return []
    lengths = [sum(doc.values()) for doc in documents]
    average = sum(lengths) / n or 1.0
    df = Counter(term for doc in documents for term in doc)
    scores = []
    for index, doc in enumerate(documents):
        score = 0.0
        for term, query_frequency in query.items():
            frequency = doc[term]
            if frequency:
                idf = math.log(1 + (n - df[term] + .5) / (df[term] + .5))
                denominator = frequency + 1.2 * (1 - .75 + .75 * lengths[index] / average)
                score += query_frequency * idf * frequency * 2.2 / denominator
        scores.append(score)
    return [keys[i] for i in sorted(range(n), key=lambda i: (-scores[i], i))]


def normalized(text: str) -> str:
    return " ".join(text.lower().split())


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def profile(rows: list[dict]) -> tuple[dict, dict[str, set[str]]]:
    problems = Counter()
    ids = Counter()
    groups = {key: set() for key in ("company_id", "annual_report_id", "page_id", "question_id",
                                    "question_text", "context_hash")}
    gold_sizes = Counter()
    candidate_sizes = []
    mismatches = []
    for record in rows:
        identifier = record.get("id", "")
        ids[identifier] += 1
        try:
            parsed = parse_id(identifier)
            for key, value in parsed.items():
                groups[key].add(value)
        except ValueError:
            problems["unparsed_id"] += 1
        qa = record.get("qa", {})
        question = qa.get("question", "")
        groups["question_text"].add(normalized(question))
        if not question.strip():
            problems["missing_question"] += 1
        gold = qa.get("gold_inds", {})
        if not isinstance(gold, dict) or not gold:
            problems["empty_or_invalid_gold"] += 1
            gold = {}
        gold_sizes[len(gold)] += 1
        try:
            candidates = build_candidates(record)
        except (ValueError, KeyError, TypeError):
            problems["candidate_construction_error"] += 1
            continue
        candidate_sizes.append(len(candidates))
        groups["context_hash"].add(digest(candidates))
        missing = set(gold) - set(candidates)
        if missing:
            problems["question_with_missing_gold_id"] += 1
        unequal = [key for key, text in gold.items() if key in candidates
                   and normalized(text) != normalized(candidates[key])]
        if unequal:
            problems["question_with_gold_source_text_difference"] += 1
            same_tokens = all(re.findall(r"\w+|[^\w\s]", normalized(gold[key])) ==
                              re.findall(r"\w+|[^\w\s]", normalized(candidates[key])) for key in unequal)
            problems["difference_with_same_punctuation_tokens" if same_tokens else
                     "difference_with_changed_tokens"] += 1
            if len(mismatches) < 8:
                mismatches.append({"id": identifier, "evidence_ids": unequal})
    return ({"questions": len(rows), "duplicate_id_extra_rows": sum(v-1 for v in ids.values()),
             "groups": {key: len(value) for key, value in groups.items()},
             "gold_count_distribution": dict(sorted(gold_sizes.items())),
             "candidate_count_min": min(candidate_sizes, default=0),
             "candidate_count_max": max(candidate_sizes, default=0),
             "candidate_count_mean": sum(candidate_sizes) / len(candidate_sizes) if candidate_sizes else 0,
             "problems": dict(problems), "gold_text_difference_examples": mismatches}, groups)


def pilot(rows: list[dict], split: str) -> tuple[dict, list[dict]]:
    selected = sorted(rows, key=lambda row: digest([COMMIT, split, row["id"]]))[:30]
    records = []
    total5 = total20 = errors = 0
    for record in selected:
        qa = record["qa"]
        gold = set(qa.get("gold_inds", {}))
        try:
            candidates = build_candidates(record)
            ranked = bm25_rank(qa["question"], candidates)
            found5, found20 = coverage(gold, ranked[:5]), coverage(gold, ranked[:20])
            error = None
        except (ValueError, KeyError, TypeError) as exc:
            candidates, ranked, found5, found20 = {}, [], 0, 0
            error = str(exc)
            errors += 1
        total5 += found5
        total20 += found20
        records.append({"split": split, **parse_id(record["id"]), "question": qa["question"],
                        "candidate_scope": "provided_page", "gold_ids": sorted(gold),
                        "gold_texts_for_review_only": qa.get("gold_inds", {}),
                        "top20": [{"id": key, "text": candidates[key]} for key in ranked[:20]],
                        "candidate_count": len(candidates), "complete_coverage_at_5": found5,
                        "complete_coverage_at_20": found20, "error": error,
                        "negative_label_review_status": "unreviewed"})
    return ({"questions": len(selected), "complete_gold_coverage_at_5_count": total5,
             "candidate_gold_coverage_at_20_count": total20, "errors_counted_as_failure": errors}, records)


def audit(data: Path, output: Path) -> dict:
    receipt = json.loads((data / "acquisition.json").read_text(encoding="utf-8"))
    if receipt["commit"] != COMMIT:
        raise ValueError("Unexpected dataset commit")
    metadata = {entry["path"]: entry for entry in receipt["files"]}
    profiles, sets, pilots, records = {}, {}, {}, []
    for split in ("train", "dev"):
        path = data / "dataset" / f"{split}.json"
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata[f"dataset/{split}.json"]["sha256"]:
            raise ValueError(f"Changed source: {split}")
        rows = json.loads(raw)
        profiles[split], sets[split] = profile(rows)
        pilots[split], selected = pilot(rows, split)
        records.extend(selected)
    overlaps = {key: len(sets["train"][key] & sets["dev"][key]) for key in sets["train"]}
    result = {"date": "2026-10-14", "repository": receipt["repository"], "commit": COMMIT,
              "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "python_version": sys.version.split()[0],
              "source_files": receipt["files"], "splits_accessed": ["train", "dev"],
              "test_content_accessed": False, "candidate_scope": "provided_page",
              "group_definitions": {"annual_report_id": "company/year proxy from source ID, not verified filing-version identity",
                                    "page_id": "company/year/page_N.pdf"},
              "serialization": "header-aware upstream row template; strict row widths; includes header row",
              "profiles": profiles, "train_dev_overlap_counts": overlaps,
              "pilot_sampling": "30 per split by ascending SHA256(commit,split,question_id)",
              "pilot": pilots, "bm25": {"k1": 1.2, "b": .75,
              "tokenization": "lowercase English words and decimal numbers; no stemming/stopword removal",
              "idf_scope": "provided page", "gold_added_to_candidates": False},
              "claim_boundary": "Development pilot only; no trained models, final test, or confirmed negative labels."}
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (output / "pilot-review.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=PROJECT / "research/data/finqa" / COMMIT)
    parser.add_argument("--output", type=Path, default=PROJECT / "research/artifacts/finqa-audit-20261014")
    args = parser.parse_args()
    result = audit(args.data, args.output)
    print(json.dumps({"profiles": result["profiles"], "overlap": result["train_dev_overlap_counts"],
                      "pilot": result["pilot"]}, ensure_ascii=False, indent=2))
