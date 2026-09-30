#!/usr/bin/env python3
"""
AerialEye incremental embedding CLI.

  python embed.py [--model remoteclip] [--batch-size 64] [--device cpu|cuda] [--limit N]
  python embed.py --watch

New tiles are appended to FAISS IndexIDMap2 without rebuilding.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

# Offline before any model imports
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aerialeye.embed")


def main():
    parser = argparse.ArgumentParser(description="AerialEye incremental tile embedding")
    parser.add_argument("--model", default=None, help="Override embedding.model from config.yaml")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--device", choices=["cpu", "cuda"], default=None)
    parser.add_argument("--limit", type=int, default=None, help="Max tiles to embed this run")
    parser.add_argument("--watch", action="store_true", help="Poll for new tiles every 30s")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--interval", type=int, default=30, help="Watch poll interval seconds")
    args = parser.parse_args()

    # Ensure project root on path
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from backend.services.embedding_service import (
        get_embedding_config,
        load_app_config,
        run_incremental_embed,
    )

    load_app_config(args.config)
    emb = get_embedding_config()
    model = args.model or emb["model"]
    batch_size = args.batch_size or int(emb.get("batch_size", 64))
    device = args.device or emb.get("device", "cpu")

    def run_once():
        logger.info(
            "Embedding pending tiles model=%s batch_size=%s device=%s limit=%s",
            model,
            batch_size,
            device,
            args.limit,
        )
        start = time.time()
        try:
            from tqdm import tqdm  # noqa: F401 — progress used inside if we wrap; stats printed below
        except Exception:
            pass
        stats = run_incremental_embed(
            model_name=model,
            batch_size=batch_size,
            device=device,
            limit=args.limit,
        )
        elapsed = time.time() - start
        print("\n--- EMBED SUMMARY ---")
        for k, v in stats.items():
            print(f"{k}: {v}")
        print(f"elapsed_s: {elapsed:.2f}")
        print("---------------------\n")
        return stats

    if args.watch:
        logger.info("Watch mode: polling every %ss (Ctrl+C to stop)", args.interval)
        while True:
            run_once()
            time.sleep(args.interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
