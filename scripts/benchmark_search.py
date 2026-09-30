#!/usr/bin/env python3
"""
Benchmark tile search latency.

  python scripts/benchmark_search.py --queries scripts/queries.txt --k 10,20,50

Writes reports/search_benchmark.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def percentile(vals, p):
    if not vals:
        return None
    return float(np.percentile(np.asarray(vals, dtype=np.float64), p))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default=str(ROOT / "scripts" / "queries.txt"))
    parser.add_argument("--k", default="10,20,50")
    parser.add_argument("--image-dir", default=None, help="Optional folder of query images")
    parser.add_argument("--with-filters", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "reports" / "search_benchmark.json"))
    args = parser.parse_args()

    from backend.services.embedding_service import get_index_status, get_model, get_embedding_config
    from backend.services.search_service import search_text, search_image, encode_text_query, _run_vector_search

    model = get_model()
    ks = [int(x) for x in args.k.split(",")]
    qpath = Path(args.queries)
    queries = [ln.strip() for ln in qpath.read_text(encoding="utf-8").splitlines() if ln.strip()]

    filters = None
    if args.with_filters:
        filters = {"include_legacy": False, "include_demo": False, "max_cloud_fraction": 0.5}

    report = {
        "model": model.name,
        "model_version": model.version,
        "index_status": get_index_status(model.name),
        "text": {},
        "image": {},
    }

    # Rough RAM: index file size + vectors npy
    st = report["index_status"]
    report["index_size_bytes"] = st.get("index_file_size_bytes", 0)
    vp = Path(st.get("vectors_path") or "")
    report["vectors_size_bytes"] = vp.stat().st_size if vp.exists() else 0

    for k in ks:
        enc_times, search_times, total_times = [], [], []
        for q in queries:
            t0 = time.perf_counter()
            vec = encode_text_query(q, model=model)
            t1 = time.perf_counter()
            from backend.services.search_service import _run_vector_search

            out = _run_vector_search(vec, k=k, filters=filters, model_name=model.name, model_version=model.version)
            t2 = time.perf_counter()
            enc_times.append((t1 - t0) * 1000)
            search_times.append((t2 - t1) * 1000)
            total_times.append((t2 - t0) * 1000)

        report["text"][str(k)] = {
            "n_queries": len(queries),
            "encode_ms": {"p50": percentile(enc_times, 50), "p95": percentile(enc_times, 95), "p99": percentile(enc_times, 99)},
            "search_ms": {"p50": percentile(search_times, 50), "p95": percentile(search_times, 95), "p99": percentile(search_times, 99)},
            "total_ms": {"p50": percentile(total_times, 50), "p95": percentile(total_times, 95), "p99": percentile(total_times, 99)},
            "filters": filters,
        }

    if args.image_dir:
        img_dir = Path(args.image_dir)
        images = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")) + list(img_dir.glob("*.tif"))
        for k in ks:
            totals = []
            for im in images[:50]:
                t0 = time.perf_counter()
                search_image(image_path=str(im), k=k, filters=filters)
                totals.append((time.perf_counter() - t0) * 1000)
            report["image"][str(k)] = {
                "n_queries": len(totals),
                "total_ms": {"p50": percentile(totals, 50), "p95": percentile(totals, 95), "p99": percentile(totals, 99)},
            }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
