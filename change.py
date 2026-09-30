#!/usr/bin/env python3
"""
AerialEye change-detection CLI.

  python change.py --aoi aoi.geojson --from 2023-01-01 --to 2026-09-01
  python change.py --aoi aoi.geojson --from 2023-01-01 --to 2024-01-01 --pair SCENE_A SCENE_B
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("change.cli")


def main():
    parser = argparse.ArgumentParser(description="AerialEye staged change detection")
    parser.add_argument("--aoi", required=True, help="AOI GeoJSON path")
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--pair", nargs=2, metavar=("BEFORE", "AFTER"), default=None)
    parser.add_argument("--sensor", default=None)
    parser.add_argument("--out", default="runs")
    parser.add_argument("--include-low", action="store_true")
    parser.add_argument("--mode", choices=["pair", "series"], default="pair")
    args = parser.parse_args()

    aoi = json.loads(Path(args.aoi).read_text(encoding="utf-8"))
    from backend.services.change.repository import ChangeRepository
    from backend.services.change.pipeline import execute_change_run
    from backend.services.change.config import load_change_config

    cfg = load_change_config()
    repo = ChangeRepository()
    run_id = repo.create_run({
        "aoi": aoi,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "mode": "pair" if args.pair else args.mode,
        "params": {"sensor": args.sensor, "include_low": args.include_low},
        "pipeline_version": cfg.get("pipeline_version"),
    })

    def band_loader(scene_id: str):
        # Minimal loader: mosaic tile chips if present; else raise
        from backend.repository import GeoRepository
        import numpy as np
        geo = GeoRepository()
        tiles = geo.get_tiles_for_scene(scene_id)
        if not tiles:
            raise FileNotFoundError(f"No tiles for {scene_id}")
        # Use first tile chip as stand-in AOI crop for CLI demo
        t = tiles[0]
        chip = np.load(t["chip_path"])
        if chip.ndim == 3 and chip.shape[0] <= 12:
            # CHW
            bands = {}
            names = ["B02", "B03", "B04", "B08", "B11"]
            for i, n in enumerate(names):
                if i < chip.shape[0]:
                    bands[n] = chip[i].astype(np.float32)
                    if bands[n].max() > 1.5:
                        bands[n] = bands[n] / 10000.0
            if "B08" not in bands and "B03" in bands:
                bands["B08"] = bands["B03"]
            if "B11" not in bands and "B04" in bands:
                bands["B11"] = bands["B04"] * 0.9
            return bands
        # HWC RGB
        arr = chip
        if arr.ndim == 3 and arr.shape[-1] >= 3:
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            if r.max() > 1.5:
                r, g, b = r / 255.0, g / 255.0, b / 255.0
            return {"B04": r.astype(np.float32), "B03": g.astype(np.float32), "B02": b.astype(np.float32),
                    "B08": g.astype(np.float32), "B11": r.astype(np.float32) * 0.8}
        raise ValueError("Unsupported chip layout")

    t0 = time.time()
    result = execute_change_run(
        run_id,
        aoi=aoi,
        date_from=args.date_from,
        date_to=args.date_to,
        mode="pair" if args.pair else args.mode,
        before_scene_id=args.pair[0] if args.pair else None,
        after_scene_id=args.pair[1] if args.pair else None,
        sensor=args.sensor,
        include_low_confidence=args.include_low,
        band_loader=band_loader,
        cfg=cfg,
    )
    elapsed = time.time() - t0

    out = Path(args.out) / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    print("\n--- CHANGE SUMMARY ---")
    print(f"run_id:        {run_id}")
    print(f"success:       {result.get('success')}")
    print(f"candidates:    {result.get('n_candidates')}")
    print(f"suppressed:    {result.get('n_suppressed')}")
    unusable = result.get("unusable_scenes") or []
    print(f"unusable:      {len(unusable)}")
    for u in unusable[:10]:
        print(f"  - {u}")
    if result.get("error"):
        print(f"error:         {result['error']}")
    print(f"time_s:        {elapsed:.2f}")
    print(f"out:           {out}")
    print("----------------------\n")


if __name__ == "__main__":
    main()
