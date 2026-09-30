#!/usr/bin/env python3
"""
Eval helper: Recall@k and nDCG@k from a relevance CSV.

CSV columns: query, tile_id, relevance
  relevance: 0 (irrelevant), 1 (partial), 2 (relevant)

  python scripts/eval_search.py --csv scripts/eval_template.csv --k 5,10 --model fake-hist
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def dcg(rels):
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg_at_k(gains, k):
    gains_k = gains[:k]
    ideal = sorted(gains, reverse=True)[:k]
    idcg = dcg(ideal)
    if idcg == 0:
        return 0.0
    return dcg(gains_k) / idcg


def recall_at_k(retrieved_ids, relevant_ids, k):
    if not relevant_ids:
        return 0.0
    hit = len(set(retrieved_ids[:k]) & relevant_ids)
    return hit / len(relevant_ids)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--k", default="5,10")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    # Force model via env/config override
    import backend.services.embedding_service as es

    if args.model:
        es._config_cache = None
        cfg = es.load_app_config()
        cfg.setdefault("embedding", {})["model"] = args.model
        es._config_cache = cfg
        es._active_model = None
        es._active_model_name = None

    from backend.services.search_service import search_text

    by_query = defaultdict(list)
    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            by_query[row["query"]].append(
                {"tile_id": int(row["tile_id"]), "relevance": int(row["relevance"])}
            )

    ks = [int(x) for x in args.k.split(",")]
    metrics = {k: {"recall": [], "ndcg": []} for k in ks}

    for query, rows in by_query.items():
        rel_map = {r["tile_id"]: r["relevance"] for r in rows}
        relevant = {tid for tid, r in rel_map.items() if r > 0}
        out = search_text(query, k=max(ks), filters={"include_demo": True, "include_legacy": True})
        retrieved = [r["tile_id"] for r in out["results"]]
        gains = [rel_map.get(tid, 0) for tid in retrieved]
        # Pad gains with zeros if needed for ideal list from judgements
        all_gains = [rel_map[tid] for tid in rel_map]
        for k in ks:
            metrics[k]["recall"].append(recall_at_k(retrieved, relevant, k))
            # nDCG uses retrieved gains vs ideal from all judged
            ideal = sorted(all_gains, reverse=True)
            metrics[k]["ndcg"].append(
                (dcg(gains[:k]) / dcg(ideal[:k])) if dcg(ideal[:k]) > 0 else 0.0
            )

    print(f"Queries: {len(by_query)}")
    for k in ks:
        rec = sum(metrics[k]["recall"]) / max(len(metrics[k]["recall"]), 1)
        nd = sum(metrics[k]["ndcg"]) / max(len(metrics[k]["ndcg"]), 1)
        print(f"k={k}  Recall@{k}={rec:.4f}  nDCG@{k}={nd:.4f}")


if __name__ == "__main__":
    main()
