"""
AerialEye Embedding Service (Prompt 2)

Offline, incremental tile embedding with FAISS IndexIDMap2.
FAISS IDs == tiles.tile_id. Index is append-only under normal operation.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Offline before model imports
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np
import yaml

logger = logging.getLogger("aerialeye.embedding")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_DIR = PROJECT_ROOT / "indexes"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Module state (per-process)
_active_model = None
_active_model_name: Optional[str] = None
_faiss_index = None
_index_type: str = "IndexFlatIP"
_vector_store: Dict[int, np.ndarray] = {}
_config_cache: Optional[dict] = None


def load_app_config(path: Optional[str] = None) -> dict:
    global _config_cache
    cfg_path = Path(path) if path else CONFIG_PATH
    if _config_cache is not None and path is None:
        return _config_cache
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    if path is None:
        _config_cache = data
    return data


def get_embedding_config(cfg: Optional[dict] = None) -> dict:
    cfg = cfg or load_app_config()
    emb = dict(cfg.get("embedding", {}) or {})
    emb.setdefault("model", "clip-vit-base-patch32")
    emb.setdefault("device", "cpu")
    emb.setdefault("exclude_cloudy_from_index_above", 0.8)
    emb.setdefault("min_valid_fraction", 0.5)
    emb.setdefault("use_hnsw", False)
    emb.setdefault("hnsw_threshold", 100000)
    emb.setdefault("hnsw_M", 32)
    emb.setdefault("hnsw_ef_construction", 200)
    emb.setdefault("hnsw_ef_search", 64)
    emb.setdefault("input_size", 224)
    emb.setdefault("reflectance_scale", 10000.0)
    emb.setdefault("reflectance_clip", 0.3)
    emb.setdefault("gamma", 0.8)
    emb.setdefault("batch_size", 64)
    return emb


def index_path_for(model_name: str) -> Path:
    safe = model_name.replace("/", "_")
    return INDEX_DIR / f"{safe}.faiss"


def vectors_path_for(model_name: str) -> Path:
    safe = model_name.replace("/", "_")
    return INDEX_DIR / f"{safe}_vectors.npy"


def vectors_ids_path_for(model_name: str) -> Path:
    safe = model_name.replace("/", "_")
    return INDEX_DIR / f"{safe}_vector_ids.npy"


def get_model(model_name: Optional[str] = None, device: Optional[str] = None):
    """Load (or return cached) EmbeddingModel. Raises ModelWeightsMissingError if absent."""
    global _active_model, _active_model_name
    emb = get_embedding_config()
    name = model_name or emb["model"]
    dev = device or emb.get("device", "cpu")
    if _active_model is not None and _active_model_name == name:
        return _active_model
    from backend.services.embedding_models import get_embedding_model, write_model_card

    model = get_embedding_model(name, device=dev)
    try:
        write_model_card(model)
    except Exception as exc:
        logger.debug("MODEL_CARD write skipped: %s", exc)
    _active_model = model
    _active_model_name = name
    return model


def _create_base_index(dim: int, ntotal_hint: int = 0):
    import faiss

    emb = get_embedding_config()
    use_hnsw = bool(emb.get("use_hnsw"))
    threshold = int(emb.get("hnsw_threshold", 100000))
    # HNSW when explicitly enabled AND tile count already above threshold
    if use_hnsw and ntotal_hint >= threshold:
        M = int(emb.get("hnsw_M", 32))
        index = faiss.IndexHNSWFlat(dim, M, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = int(emb.get("hnsw_ef_construction", 200))
        index.hnsw.efSearch = int(emb.get("hnsw_ef_search", 64))
        itype = "IndexHNSWFlat"
        logger.warning(
            "Using HNSW (M=%d). Tradeoff: approximate search, faster at scale, "
            "does NOT support removal — superseded tiles must be filtered at query time.",
            M,
        )
    else:
        index = faiss.IndexFlatIP(dim)
        itype = "IndexFlatIP"
    return index, itype


def _wrap_idmap(base):
    import faiss

    return faiss.IndexIDMap2(base)


def load_or_create_index(model_name: Optional[str] = None, dim: Optional[int] = None):
    """Load FAISS IndexIDMap2 for the model, or create empty."""
    global _faiss_index, _index_type, _vector_store
    import faiss

    emb = get_embedding_config()
    name = model_name or emb["model"]
    if dim is None:
        # Prefer model dim; fall back to 512
        try:
            dim = get_model(name).embedding_dim
        except Exception:
            dim = 512

    path = index_path_for(name)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    if path.exists():
        index = faiss.read_index(str(path))
        # Detect type
        if hasattr(index, "index"):
            inner = index.index
            if "HNSW" in type(inner).__name__:
                _index_type = "IndexHNSWFlat"
            else:
                _index_type = "IndexFlatIP"
        else:
            # Upgrade bare index to IDMap2 (should not happen in Prompt 2)
            base, _index_type = _create_base_index(index.d, index.ntotal)
            wrapped = _wrap_idmap(base)
            if index.ntotal > 0:
                logger.warning("Re-wrapping legacy index without IDs is unsupported; starting empty IDMap2.")
            index = wrapped
        _faiss_index = index
        logger.info(
            "Loaded FAISS index type=%s ntotal=%d dim=%d path=%s",
            _index_type,
            index.ntotal,
            index.d,
            path,
        )
    else:
        base, _index_type = _create_base_index(dim, 0)
        _faiss_index = _wrap_idmap(base)
        logger.info(
            "Created FAISS index type=%s ntotal=0 dim=%d path=%s",
            _index_type,
            dim,
            path,
        )

    _load_vector_store(name)
    return _faiss_index


def _load_vector_store(model_name: str) -> None:
    global _vector_store
    vp = vectors_path_for(model_name)
    ip = vectors_ids_path_for(model_name)
    _vector_store = {}
    if vp.exists() and ip.exists():
        try:
            vecs = np.load(str(vp))
            ids = np.load(str(ip))
            for i, tid in enumerate(ids):
                _vector_store[int(tid)] = vecs[i].astype(np.float32)
            logger.info("Loaded %d raw vectors for clustering reuse", len(_vector_store))
        except Exception as exc:
            logger.warning("Failed to load vector store: %s", exc)
            _vector_store = {}


def get_index(model_name: Optional[str] = None):
    global _faiss_index
    if _faiss_index is None:
        return load_or_create_index(model_name)
    return _faiss_index


def get_index_ids(index=None) -> set:
    """Return set of FAISS IDs currently in the index (via id_map)."""
    import faiss

    index = index if index is not None else get_index()
    if index is None or index.ntotal == 0:
        return set()
    try:
        # IndexIDMap2 exposes id_map
        id_map = faiss.vector_to_array(index.id_map)
        return set(int(x) for x in id_map.tolist())
    except Exception:
        # Fallback: reconstruct attempts
        ids = set()
        try:
            for i in range(index.ntotal):
                ids.add(int(index.id_map.at(i)))
        except Exception as exc:
            logger.warning("Could not read FAISS id_map: %s", exc)
        return ids


def save_index_atomic(model_name: Optional[str] = None) -> Path:
    """Persist index to temp file then rename (atomic on same filesystem)."""
    import faiss

    emb = get_embedding_config()
    name = model_name or emb["model"]
    index = get_index(name)
    path = index_path_for(name)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".faiss.tmp")
    faiss.write_index(index, str(tmp))
    # Windows-safe replace
    if path.exists():
        path.unlink()
    tmp.rename(path)
    _save_vector_store(name)
    return path


def _save_vector_store(model_name: str) -> None:
    import tempfile
    import shutil

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    vp = vectors_path_for(model_name)
    ip = vectors_ids_path_for(model_name)
    if not _vector_store:
        ids = np.array([], dtype=np.int64)
        vecs = np.zeros((0, 1), dtype=np.float32)
    else:
        ids = np.array(sorted(_vector_store.keys()), dtype=np.int64)
        vecs = np.stack([_vector_store[int(i)] for i in ids], axis=0).astype(np.float32)

    with tempfile.TemporaryDirectory(dir=str(INDEX_DIR)) as td:
        tmp_v = Path(td) / "vectors.npy"
        tmp_i = Path(td) / "ids.npy"
        np.save(str(tmp_v), vecs)
        np.save(str(tmp_i), ids)
        shutil.copy2(str(tmp_v), str(vp) + ".part")
        shutil.copy2(str(tmp_i), str(ip) + ".part")
    # Atomic-ish replace
    part_v = Path(str(vp) + ".part")
    part_i = Path(str(ip) + ".part")
    if vp.exists():
        vp.unlink()
    if ip.exists():
        ip.unlink()
    part_v.rename(vp)
    part_i.rename(ip)


def add_vectors_with_ids(
    vectors: np.ndarray,
    tile_ids: Sequence[int],
    model_name: Optional[str] = None,
    skip_existing: bool = True,
) -> Tuple[int, int]:
    """
    Add vectors to FAISS with tile_id IDs. Returns (added, skipped).
    Never duplicates IDs already present in the index (safe re-run).
    """
    import faiss

    emb = get_embedding_config()
    name = model_name or emb["model"]
    index = get_index(name)
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    ids = np.asarray(list(tile_ids), dtype=np.int64)
    assert len(ids) == len(vectors)

    existing = get_index_ids(index) if skip_existing else set()
    mask = np.array([int(i) not in existing for i in ids], dtype=bool)
    added = int(mask.sum())
    skipped = int((~mask).sum())
    if added == 0:
        return 0, skipped

    vectors_new = np.ascontiguousarray(vectors[mask])
    ids_new = np.ascontiguousarray(ids[mask])
    index.add_with_ids(vectors_new, ids_new)
    for tid, vec in zip(ids_new.tolist(), vectors_new):
        _vector_store[int(tid)] = vec.astype(np.float32)
    return added, skipped


def embed_tiles_batch(
    tiles: List[Dict[str, Any]],
    model=None,
    model_name: Optional[str] = None,
) -> Tuple[np.ndarray, List[int], List[Dict[str, Any]]]:
    """
    Encode a list of tile rows. Returns (vectors, tile_ids, skipped_info).
    """
    from backend.services.tile_image import load_tile_rgb

    emb = get_embedding_config()
    name = model_name or emb["model"]
    model = model or get_model(name)

    images = []
    ids = []
    skipped = []
    for t in tiles:
        rgb = load_tile_rgb(
            t,
            input_size=int(emb.get("input_size", 224)),
            reflectance_scale=float(emb.get("reflectance_scale", 10000.0)),
            reflectance_clip=float(emb.get("reflectance_clip", 0.3)),
            gamma=float(emb.get("gamma", 0.8)),
        )
        if rgb is None:
            skipped.append({"tile_id": t.get("tile_id"), "reason": "load_failed"})
            continue
        images.append(rgb)
        ids.append(int(t["tile_id"]))

    if not images:
        return np.zeros((0, model.embedding_dim), dtype=np.float32), [], skipped

    vectors = model.encode_images(images)
    return vectors, ids, skipped


def run_incremental_embed(
    model_name: Optional[str] = None,
    batch_size: int = 64,
    device: Optional[str] = None,
    limit: Optional[int] = None,
    repo=None,
    fail_after_index_write: bool = False,
) -> Dict[str, Any]:
    """
    Embed pending tiles for the active model.
    Order: encode -> add_with_ids (skip existing IDs) -> atomic save -> DB commit.
    If process dies between index write and DB commit, re-run skips FAISS IDs already present.
    """
    from backend.repository import GeoRepository

    emb = get_embedding_config()
    name = model_name or emb["model"]
    if device:
        emb = dict(emb)
        # force reload on device change
        global _active_model, _active_model_name
        _active_model = None
        _active_model_name = None

    repo = repo or GeoRepository()
    model = get_model(name, device=device or emb.get("device", "cpu"))
    load_or_create_index(name, dim=model.embedding_dim)

    min_vf = float(emb.get("min_valid_fraction", 0.5))
    cloudy = float(emb.get("exclude_cloudy_from_index_above", 0.8))

    stats = {
        "model": name,
        "model_version": model.version,
        "encoded": 0,
        "added": 0,
        "skipped_existing": 0,
        "skipped_quality": 0,
        "batches": 0,
        "pending_before": repo.count_tiles_pending_embed(name, min_vf, cloudy),
    }

    remaining = limit
    while True:
        fetch = batch_size if remaining is None else min(batch_size, remaining)
        if fetch <= 0:
            break
        tiles = repo.select_pending_tiles(name, limit=fetch, min_valid_fraction=min_vf, exclude_cloudy_above=cloudy)
        # select_pending_tiles already logs quality skips; count difference
        if not tiles:
            break

        vectors, ids, skipped = embed_tiles_batch(tiles, model=model, model_name=name)
        stats["skipped_quality"] += len(skipped)
        for s in skipped:
            if s.get("tile_id") is not None:
                repo.log_embed_skip(int(s["tile_id"]), name, s.get("reason", "load_failed"))

        if len(ids) == 0:
            if remaining is not None:
                remaining -= len(tiles)
            stats["batches"] += 1
            # Avoid infinite loop if all tiles keep failing load — mark? skip by inserting nothing
            break

        added, skipped_ex = add_vectors_with_ids(vectors, ids, model_name=name, skip_existing=True)
        save_index_atomic(name)

        if fail_after_index_write:
            raise RuntimeError("Simulated crash after index write (before DB commit)")

        now = time.time()
        rows = [
            {
                "tile_id": int(tid),
                "model_name": name,
                "model_version": model.version,
                "embedded_at": now,
            }
            for tid in ids
        ]
        # Also commit rows for IDs that were already in the index (healing after crash)
        existing_ids = get_index_ids()
        heal = [int(t["tile_id"]) for t in tiles if int(t["tile_id"]) in existing_ids]
        heal_rows = [
            {
                "tile_id": tid,
                "model_name": name,
                "model_version": model.version,
                "embedded_at": now,
            }
            for tid in heal
            if not repo.has_tile_embedding(tid, name)
        ]
        repo.insert_tile_embeddings(rows + heal_rows)
        repo.mark_tiles_embedded(list({*ids, *heal}))

        stats["encoded"] += len(ids)
        stats["added"] += added
        stats["skipped_existing"] += skipped_ex
        stats["batches"] += 1

        if remaining is not None:
            remaining -= len(tiles)
            if remaining <= 0:
                break
        if len(tiles) < fetch:
            break

    stats["pending_after"] = repo.count_tiles_pending_embed(name, min_vf, cloudy)
    stats["indexed_total"] = repo.count_tiles_indexed(name)
    stats["index_type"] = _index_type
    stats["index_ntotal"] = get_index(name).ntotal if get_index(name) else 0
    return stats


def search_faiss(
    query_vec: np.ndarray,
    k: int,
    allowed_ids: Optional[Sequence[int]] = None,
    model_name: Optional[str] = None,
) -> List[Tuple[float, int]]:
    """
    Search FAISS. If allowed_ids provided:
      - if len(allowed) < max_candidates_for_exact: exact IP over stored vectors
      - else: IDSelectorBatch restricted search
    Returns list of (score, tile_id) sorted desc.
    """
    import faiss

    cfg = load_app_config()
    search_cfg = cfg.get("search", {}) or {}
    exact_thresh = int(search_cfg.get("max_candidates_for_exact", 5000))

    emb = get_embedding_config()
    name = model_name or emb["model"]
    index = get_index(name)
    if index is None or index.ntotal == 0:
        return []

    q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
    # L2-normalize query
    n = np.linalg.norm(q, axis=1, keepdims=True)
    q = q / np.maximum(n, 1e-12)

    if allowed_ids is not None:
        allowed = [int(x) for x in allowed_ids]
        if len(allowed) == 0:
            return []

        if len(allowed) < exact_thresh:
            return _exact_search_subset(q[0], allowed, k)

        # Restricted FAISS search with IDSelectorBatch
        id_array = np.asarray(allowed, dtype=np.int64)
        selector = faiss.IDSelectorBatch(id_array.size, faiss.swig_ptr(id_array))
        params = faiss.SearchParameters()
        # IndexIDMap2 / FlatIP support params with sel
        try:
            params.sel = selector
            scores, idxs = index.search(q, min(k, len(allowed)), params=params)
        except Exception:
            # Older faiss: search then filter (over-fetch)
            over = min(index.ntotal, max(k * 50, len(allowed)))
            scores, idxs = index.search(q, over)
            allowed_set = set(allowed)
            out = []
            for sc, idx in zip(scores[0], idxs[0]):
                if idx < 0:
                    continue
                if int(idx) in allowed_set:
                    out.append((float(sc), int(idx)))
                if len(out) >= k:
                    break
            return out

        out = []
        for sc, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            out.append((float(sc), int(idx)))
        return out

    k_eff = min(k, index.ntotal)
    scores, idxs = index.search(q, k_eff)
    return [(float(sc), int(idx)) for sc, idx in zip(scores[0], idxs[0]) if idx >= 0]


def _exact_search_subset(query: np.ndarray, allowed_ids: Sequence[int], k: int) -> List[Tuple[float, int]]:
    """Exact cosine (IP on normalised vectors) over candidate IDs using vector store or reconstruct."""
    global _vector_store
    q = query.astype(np.float32)
    scored = []
    missing = []
    for tid in allowed_ids:
        vec = _vector_store.get(int(tid))
        if vec is None:
            missing.append(int(tid))
            continue
        scored.append((float(np.dot(q, vec)), int(tid)))

    if missing:
        # Try reconstruct from FAISS
        index = get_index()
        for tid in missing:
            try:
                vec = np.zeros(index.d, dtype=np.float32)
                index.reconstruct(int(tid), vec)
                scored.append((float(np.dot(q, vec)), int(tid)))
                _vector_store[int(tid)] = vec
            except Exception:
                continue

    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def get_vector_for_tile(tile_id: int, model_name: Optional[str] = None) -> Optional[np.ndarray]:
    if int(tile_id) in _vector_store:
        return _vector_store[int(tile_id)]
    index = get_index(model_name)
    if index is None:
        return None
    try:
        vec = np.zeros(index.d, dtype=np.float32)
        index.reconstruct(int(tile_id), vec)
        _vector_store[int(tile_id)] = vec
        return vec
    except Exception:
        return None


def get_index_status(model_name: Optional[str] = None, repo=None) -> Dict[str, Any]:
    from backend.repository import GeoRepository

    emb = get_embedding_config()
    name = model_name or emb["model"]
    repo = repo or GeoRepository()
    path = index_path_for(name)
    try:
        index = load_or_create_index(name)
        ntotal = index.ntotal
        dim = index.d
    except Exception as exc:
        ntotal = 0
        dim = 0
        logger.warning("Index status load failed: %s", exc)

    size = path.stat().st_size if path.exists() else 0
    min_vf = float(emb.get("min_valid_fraction", 0.5))
    cloudy = float(emb.get("exclude_cloudy_from_index_above", 0.8))
    return {
        "model": name,
        "index_type": _index_type,
        "embedding_dim": dim,
        "tiles_indexed": repo.count_tiles_indexed(name),
        "tiles_pending": repo.count_tiles_pending_embed(name, min_vf, cloudy),
        "faiss_ntotal": ntotal,
        "index_path": str(path),
        "index_file_size_bytes": size,
        "vectors_path": str(vectors_path_for(name)),
        "last_update": repo.last_embed_time(name),
    }


# ---------------------------------------------------------------------------
# Backward-compatible thin wrappers used by legacy scene search / Data page
# ---------------------------------------------------------------------------

def embed_image(image_path: str):
    """Legacy: embed a file path. Returns (vec, label)."""
    from backend.services.tile_image import load_image_file_rgb

    try:
        model = get_model()
        rgb = load_image_file_rgb(image_path)
        if rgb is None:
            return None, "UNAVAILABLE"
        vec = model.encode_images([rgb])[0]
        return vec, "REAL"
    except Exception as exc:
        logger.warning("embed_image failed: %s", exc)
        return None, "UNAVAILABLE"


def embed_text(query: str):
    try:
        model = get_model()
        vec = model.encode_text([query])[0]
        return vec, "REAL"
    except Exception as exc:
        logger.warning("embed_text failed: %s", exc)
        return None, "UNAVAILABLE"


def search_index(query_vec: np.ndarray, top_k: int = 20):
    """Legacy adapter returning (score, meta_dict with tile_id)."""
    hits = search_faiss(query_vec, k=top_k)
    return [(sc, {"tile_id": tid, "asset_id": str(tid)}) for sc, tid in hits]


def add_to_index(vector: np.ndarray, meta: Dict[str, Any]) -> int:
    """Legacy: add one vector. Prefer add_vectors_with_ids."""
    tid = meta.get("tile_id")
    if tid is None:
        tid = abs(hash(str(meta))) % (2**62)
    add_vectors_with_ids(vector.reshape(1, -1), [int(tid)])
    save_index_atomic()
    return int(tid)


def get_models_status() -> Dict[str, Any]:
    try:
        model = get_model()
        ok = True
        err = None
        name = model.name
        dim = model.embedding_dim
    except Exception as exc:
        ok = False
        err = str(exc)
        name = get_embedding_config()["model"]
        dim = 512
    try:
        st = get_index_status(name if ok else None)
    except Exception:
        st = {"faiss_ntotal": 0}
    return {
        "clip_available": ok,
        "text_model_available": ok,
        "faiss_available": True,
        "faiss_vector_count": st.get("faiss_ntotal", 0),
        "faiss_index_path": st.get("index_path"),
        "embedding_dim": dim,
        "model": name,
        "error": err,
        "label": "REAL" if ok else "UNAVAILABLE",
    }
