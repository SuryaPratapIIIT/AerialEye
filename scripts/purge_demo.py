#!/usr/bin/env python3
"""
Purge DEMO scenes and their vectors.

  python scripts/purge_demo.py --dry-run
  python scripts/purge_demo.py

NOTE: This is the ONE operation that rebuilds the FAISS index from surviving
tile_embeddings / vector store, because FAISS Flat/HNSW cannot cheaply remove IDs.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("purge_demo")


def rebuild_index_from_store(model_name: str, surviving_ids: set) -> None:
    """One-time rebuild after DEMO purge."""
    import faiss
    import numpy as np
    from backend.services.embedding_service import (
        INDEX_DIR,
        _create_base_index,
        _wrap_idmap,
        get_model,
        index_path_for,
        load_or_create_index,
        vectors_ids_path_for,
        vectors_path_for,
        save_index_atomic,
        _vector_store,
        _load_vector_store,
    )
    import backend.services.embedding_service as es

    model = get_model(model_name)
    _load_vector_store(model_name)
    keep_ids = sorted(i for i in es._vector_store.keys() if int(i) in surviving_ids)
    if not keep_ids:
        # Empty index
        base, _ = _create_base_index(model.embedding_dim, 0)
        es._faiss_index = _wrap_idmap(base)
        es._vector_store = {}
        save_index_atomic(model_name)
        logger.info("Wrote empty index for %s after purge", model_name)
        return

    vecs = np.stack([es._vector_store[i] for i in keep_ids], axis=0).astype(np.float32)
    ids = np.asarray(keep_ids, dtype=np.int64)
    base, itype = _create_base_index(model.embedding_dim, len(ids))
    index = _wrap_idmap(base)
    index.add_with_ids(vecs, ids)
    es._faiss_index = index
    es._index_type = itype
    es._vector_store = {int(i): es._vector_store[int(i)] for i in keep_ids}
    save_index_atomic(model_name)
    logger.info(
        "Rebuilt index type=%s ntotal=%d for model=%s (ONE-TIME purge rebuild)",
        itype,
        index.ntotal,
        model_name,
    )


def main():
    parser = argparse.ArgumentParser(description="Purge DEMO records and rebuild FAISS once")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=None, help="Model whose index to rebuild")
    args = parser.parse_args()

    from backend.repository import GeoRepository
    from backend.services.embedding_service import get_embedding_config

    repo = GeoRepository()
    emb = get_embedding_config()
    model_name = args.model or emb["model"]

    scenes = list(repo.db["geo_scenes"].rows_where("source_type = ?", ["DEMO"]))
    tile_ids = []
    for s in scenes:
        tiles = repo.get_tiles_for_scene(s["scene_id"], include_superseded=True)
        tile_ids.extend(int(t["tile_id"]) for t in tiles)

    print(f"DEMO scenes: {len(scenes)}")
    print(f"DEMO tiles:  {len(tile_ids)}")
    if args.dry_run:
        print("Dry-run: no changes made.")
        return

    removed_tiles, removed_scenes = repo.delete_demo_scenes()
    print(f"Deleted scenes={len(removed_scenes)} tiles={len(removed_tiles)}")

    # Surviving tile ids that still have embeddings
    surviving = set(repo.get_embedded_tile_ids(model_name))
    print(
        f"ONE-TIME INDEX REBUILD required after DEMO purge "
        f"(FAISS Flat/HNSW cannot remove IDs cheaply). Surviving embeddings: {len(surviving)}"
    )
    rebuild_index_from_store(model_name, surviving)
    print("Done.")


if __name__ == "__main__":
    main()
