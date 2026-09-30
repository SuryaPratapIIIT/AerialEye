"""
Pure, unit-testable change-detection stages (1–10).

Masked / invalid pixels are UNKNOWN: excluded from numerator AND denominator.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from scipy import ndimage
from skimage.measure import label, regionprops
from skimage.morphology import binary_closing, binary_opening, disk
from skimage.registration import phase_cross_correlation

from backend.services.change.provenance import Provenance, StageTimer
from backend.services.change.types import (
    ChangeCandidate,
    CommonGrid,
    IndexStack,
    QualityMaskResult,
    RadiometryResult,
    RegistrationResult,
    SceneObservation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros_like(a, dtype=np.float32)
    mask = np.abs(b) > 1e-6
    out[mask] = (a[mask] / b[mask]).astype(np.float32)
    return out


def _mad_sigma(values: np.ndarray) -> float:
    """Robust sigma ≈ 1.4826 * MAD. Returns 1e-6 if empty."""
    if values.size == 0:
        return 1e-6
    med = np.median(values)
    mad = np.median(np.abs(values - med))
    return float(max(1.4826 * mad, 1e-6))


def _valid_stats(arr: np.ndarray, valid: np.ndarray) -> Tuple[float, int]:
    """Mean over valid pixels only. Invalid never counted as change or no-change."""
    m = valid.astype(bool) & np.isfinite(arr)
    n = int(m.sum())
    if n == 0:
        return float("nan"), 0
    return float(arr[m].mean()), n


def day_of_year(iso: str) -> int:
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s[:19])
        return int(dt.timetuple().tm_yday)
    except Exception:
        return 0


def parse_date(iso: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")[:19])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stage 1: Common grid (in-memory / pre-aligned path for tests + tile chips)
# ---------------------------------------------------------------------------

def stage_common_grid(
    before: SceneObservation,
    after: SceneObservation,
    aoi_mask: Optional[np.ndarray],
    cfg: Dict[str, Any],
    prov: Provenance,
) -> CommonGrid:
    """
    Align band dicts to a shared shape. For REAL georeferenced data the caller
    should resample into matching arrays first; this stage validates overlap
    and builds the CommonGrid.
    """
    with StageTimer(prov, "common_grid", {"min_overlap": cfg.get("min_overlap")}) as t:
        keys = sorted(set(before.bands) & set(after.bands) - {"SCL"})
        if not keys:
            keys = sorted(set(before.bands) & set(after.bands))
        if not keys:
            raise ValueError("No shared bands between before and after")

        ref = before.bands[keys[0]]
        h, w = ref.shape[:2]
        for k in keys:
            if before.bands[k].shape[:2] != (h, w) or after.bands[k].shape[:2] != (h, w):
                # nearest/bilinear resize to before shape
                bh = before.bands[k]
                ah = after.bands[k]
                if bh.shape[:2] != (h, w):
                    interp = cv2.INTER_NEAREST if k == "SCL" else cv2.INTER_LINEAR
                    before.bands[k] = cv2.resize(bh.astype(np.float32), (w, h), interpolation=interp)
                if ah.shape[:2] != (h, w):
                    interp = cv2.INTER_NEAREST if k == "SCL" else cv2.INTER_LINEAR
                    after.bands[k] = cv2.resize(ah.astype(np.float32), (w, h), interpolation=interp)

        if aoi_mask is None:
            aoi = np.ones((h, w), dtype=bool)
        else:
            aoi = aoi_mask.astype(bool)
            if aoi.shape != (h, w):
                aoi = cv2.resize(aoi.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)

        # Overlap: fraction of AOI where both scenes have finite reflectance in a ref band
        b0 = before.bands[keys[0]].astype(np.float32)
        a0 = after.bands[keys[0]].astype(np.float32)
        both = aoi & np.isfinite(b0) & np.isfinite(a0)
        denom = max(int(aoi.sum()), 1)
        overlap = float(both.sum()) / float(denom)
        t.extras["overlap_fraction"] = overlap
        t.extras["shape"] = [h, w]

        if overlap < float(cfg.get("min_overlap", 0.5)):
            raise ValueError(
                f"Pair overlap {overlap:.3f} below change.min_overlap={cfg.get('min_overlap')}"
            )

        return CommonGrid(
            bands_before={k: before.bands[k].astype(np.float32) for k in before.bands},
            bands_after={k: after.bands[k].astype(np.float32) for k in after.bands},
            transform=before.transform,
            crs=before.crs,
            resolution_m=float(before.resolution_m or cfg.get("target_resolution_m", 10.0)),
            overlap_fraction=overlap,
            height=h,
            width=w,
            aoi_mask=aoi,
        )


# ---------------------------------------------------------------------------
# Stage 2: Registration refinement (phase correlation; no ORB)
# ---------------------------------------------------------------------------

def stage_registration(
    grid: CommonGrid,
    invalid_seed: Optional[np.ndarray],
    cfg: Dict[str, Any],
    prov: Provenance,
) -> Tuple[CommonGrid, RegistrationResult]:
    with StageTimer(
        prov,
        "registration",
        {
            "max_shift_px": cfg.get("max_shift_px"),
            "min_registration_correlation": cfg.get("min_registration_correlation"),
        },
    ) as t:
        # Prefer NIR (B08) else B04; use Sobel edges over valid pixels
        band_key = "B08" if "B08" in grid.bands_before else ("B04" if "B04" in grid.bands_before else next(iter(grid.bands_before)))
        ref = grid.bands_before[band_key].astype(np.float32)
        mov = grid.bands_after[band_key].astype(np.float32)
        valid = grid.aoi_mask.copy()
        if invalid_seed is not None:
            valid &= ~invalid_seed.astype(bool)

        # Gradient-rich image
        ref_e = cv2.Sobel(ref, cv2.CV_32F, 1, 1, ksize=3)
        mov_e = cv2.Sobel(mov, cv2.CV_32F, 1, 1, ksize=3)
        ref_e = np.where(valid, ref_e, 0.0)
        mov_e = np.where(valid, mov_e, 0.0)

        try:
            shift, error, _ = phase_cross_correlation(
                ref_e, mov_e, upsample_factor=10, normalization=None
            )
            # skimage returns (row, col) shift to apply to moving → reference
            sy, sx = float(shift[0]), float(shift[1])
            corr = float(1.0 - min(max(error, 0.0), 1.0)) if error is not None else 0.5
        except Exception as exc:
            prov.warn(f"phase_cross_correlation failed: {exc}")
            sy, sx, corr = 0.0, 0.0, 0.0

        mag = float(np.hypot(sx, sy))
        max_shift = float(cfg.get("max_shift_px", 5.0))
        min_shift = float(cfg.get("min_shift_px", 0.1))
        min_corr = float(cfg.get("min_registration_correlation", 0.3))

        quality = "good"
        applied = False
        if mag > max_shift or corr < min_corr:
            quality = "poor"
        elif mag >= min_shift:
            # Apply shift to all after bands
            for k, arr in list(grid.bands_after.items()):
                interp = cv2.INTER_NEAREST if k == "SCL" else cv2.INTER_LINEAR
                M = np.array([[1, 0, sx], [0, 1, sy]], dtype=np.float32)
                grid.bands_after[k] = cv2.warpAffine(
                    arr.astype(np.float32), M, (grid.width, grid.height),
                    flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=np.nan,
                )
            applied = True

        result = RegistrationResult(
            shift_y=sy, shift_x=sx, correlation=corr, quality=quality, applied=applied
        )
        t.extras = {
            "shift_y": sy, "shift_x": sx, "correlation": corr,
            "quality": quality, "applied": applied,
        }
        if quality == "poor" and cfg.get("reject_poor_registration"):
            raise ValueError("registration_quality=poor and reject_poor_registration=true")
        return grid, result


# ---------------------------------------------------------------------------
# Stage 3: Quality masking
# ---------------------------------------------------------------------------

def stage_quality_mask(
    grid: CommonGrid,
    quality_source_before: str,
    quality_source_after: str,
    cfg: Dict[str, Any],
    prov: Provenance,
    sensor_before: str = 'Sentinel-2',
    sensor_after: str = 'Sentinel-2'
) -> QualityMaskResult:
    from backend.services.sensor_profile import SensorProfile
    prof_before = SensorProfile.load(sensor_before)
    prof_after = SensorProfile.load(sensor_after)

    with StageTimer(prov, "quality_mask", {"mask_dilation_px": cfg.get("mask_dilation_px")}) as t:
        h, w = grid.height, grid.width
        before_inv = np.zeros((h, w), dtype=bool)
        after_inv = np.zeros((h, w), dtype=bool)
        before_cloud = np.zeros((h, w), dtype=bool)
        after_cloud = np.zeros((h, w), dtype=bool)
        no_product = True

        for side, inv_ref, cloud_ref, qs, prof in (
            ("before", before_inv, before_cloud, quality_source_before, prof_before),
            ("after", after_inv, after_cloud, quality_source_after, prof_after),
        ):
            bands = grid.bands_before if side == "before" else grid.bands_after
            mask_band = prof.cloud_mask.get("band")
            if mask_band and mask_band in bands and qs and qs != "none":
                no_product = False
                scl = bands[mask_band].astype(np.int32)
                bad = set(prof.cloud_classes + prof.shadow_classes + prof.snow_classes + prof.nodata_classes)
                inv = np.isin(scl, list(bad))
                cloud_ref[:] = np.isin(scl, prof.cloud_classes)
                inv_ref[:] = inv
            # nodata / nan
            for k, arr in bands.items():
                if k == mask_band:
                    continue
                inv_ref |= ~np.isfinite(arr)

        # Spectral haze safeguard (high blue)
        thr = float(cfg.get("blue_haze_threshold", 0.25))
        for side, inv_ref, prof in (("before", before_inv, prof_before), ("after", after_inv, prof_after)):
            bands = grid.bands_before if side == "before" else grid.bands_after
            blue_k = prof.band_mapping.get("B02", "B02")
            if blue_k in bands:
                blue = bands[blue_k]
                inv_ref |= np.isfinite(blue) & (blue > thr)

        # Brightness outliers on valid AOI pixels
        sigma_b = float(cfg.get("brightness_outlier_sigma", 3.0))
        for side, inv_ref, prof in (("before", before_inv, prof_before), ("after", after_inv, prof_after)):
            bands = grid.bands_before if side == "before" else grid.bands_after
            keys = [prof.band_mapping.get(k, k) for k in ("B02", "B03", "B04") if prof.band_mapping.get(k, k) in bands]
            if not keys:
                continue
            bright = np.mean([bands[k] for k in keys], axis=0)
            valid = grid.aoi_mask & ~inv_ref & np.isfinite(bright)
            if valid.sum() > 50:
                vals = bright[valid]
                sig = _mad_sigma(vals)
                med = float(np.median(vals))
                inv_ref |= valid & (np.abs(bright - med) > sigma_b * sig)

        invalid = before_inv | after_inv | ~grid.aoi_mask

        # Dilate invalid
        dil = int(cfg.get("mask_dilation_px", 3))
        if dil > 0:
            invalid = ndimage.binary_dilation(invalid, iterations=dil)
            before_cloud = ndimage.binary_dilation(before_cloud, iterations=dil)
            after_cloud = ndimage.binary_dilation(after_cloud, iterations=dil)

        usable = float((~invalid & grid.aoi_mask).sum()) / float(max(grid.aoi_mask.sum(), 1))
        t.extras = {"usable_fraction": usable, "no_product_mask": no_product}
        return QualityMaskResult(
            invalid=invalid,
            usable_fraction=usable,
            no_product_mask=no_product or (quality_source_before == "none" and quality_source_after == "none"),
            before_cloud=before_cloud,
            after_cloud=after_cloud,
        )


# ---------------------------------------------------------------------------
# Stage 4: Radiometric normalisation
# ---------------------------------------------------------------------------

def stage_radiometry(
    grid: CommonGrid,
    invalid: np.ndarray,
    cfg: Dict[str, Any],
    prov: Provenance,
) -> RadiometryResult:
    with StageTimer(prov, "radiometry", {"irmad_iterations": cfg.get("irmad_iterations")}) as t:
        valid = (~invalid) & grid.aoi_mask
        spectral_keys = [k for k in grid.bands_before if k != "SCL" and k in grid.bands_after]
        gains: Dict[str, float] = {}
        offsets: Dict[str, float] = {}
        after_norm: Dict[str, np.ndarray] = dict(grid.bands_after)

        # Build initial stable mask via iterative exclusion of large diffs (IR-MAD-ish)
        if not spectral_keys:
            return RadiometryResult(after_norm, gains, offsets, 0, "none")

        # composite abs diff
        diffs = []
        for k in spectral_keys:
            diffs.append(np.abs(grid.bands_after[k] - grid.bands_before[k]))
        diff = np.mean(diffs, axis=0)
        stable = valid.copy()
        iters = int(cfg.get("irmad_iterations", 4))
        excl = float(cfg.get("irmad_exclude_pct", 0.2))
        for _ in range(iters):
            vals = diff[stable]
            if vals.size < 10:
                break
            cutoff = np.quantile(vals, 1.0 - excl)
            stable = stable & (diff <= cutoff)

        n_stable = int(stable.sum())
        method = "irmad"
        min_stable = int(cfg.get("min_stable_pixels", 500))

        if n_stable >= min_stable:
            for k in spectral_keys:
                x = grid.bands_after[k][stable].astype(np.float64)
                y = grid.bands_before[k][stable].astype(np.float64)
                # y ≈ a*x + b
                A = np.vstack([x, np.ones_like(x)]).T
                try:
                    a, b = np.linalg.lstsq(A, y, rcond=None)[0]
                except Exception:
                    a, b = 1.0, 0.0
                gains[k] = float(a)
                offsets[k] = float(b)
                after_norm[k] = (a * grid.bands_after[k].astype(np.float32) + b).astype(np.float32)
        else:
            method = "histogram"
            for k in spectral_keys:
                src = grid.bands_after[k]
                ref = grid.bands_before[k]
                out = src.copy()
                sv = valid & np.isfinite(src) & np.isfinite(ref)
                if sv.sum() > 10:
                    # quantile matching
                    qs = np.linspace(0.01, 0.99, 50)
                    src_q = np.quantile(src[sv], qs)
                    ref_q = np.quantile(ref[sv], qs)
                    flat = src.ravel()
                    mapped = np.interp(flat, src_q, ref_q)
                    out = mapped.reshape(src.shape).astype(np.float32)
                after_norm[k] = out
                gains[k] = 1.0
                offsets[k] = 0.0

        if "SCL" in grid.bands_after:
            after_norm["SCL"] = grid.bands_after["SCL"]

        t.extras = {"stable_pixel_count": n_stable, "method": method, "gains": gains, "offsets": offsets}
        return RadiometryResult(after_norm, gains, offsets, n_stable, method)


# ---------------------------------------------------------------------------
# Stage 5: Indices + differences
# ---------------------------------------------------------------------------

def compute_index(bands: Dict[str, np.ndarray], name: str, cfg: Dict[str, Any], prof) -> np.ndarray:
    formula = cfg.get("index_formulas", {}).get(name)
    if not formula:
        raise ValueError(f"Unknown index {name}")
    
    with np.errstate(divide='ignore', invalid='ignore'):
        # Map logical names (B08) to sensor actual names based on profile
        local_env = {}
        for logical, actual in prof.band_mapping.items():
            if actual in bands:
                local_env[logical] = bands[actual].astype(np.float32)
            elif logical in bands:
                local_env[logical] = bands[logical].astype(np.float32)

        try:
            res = eval(formula, {"__builtins__": None}, local_env)
            res = np.where(np.isfinite(res), res, 0.0).astype(np.float32)
            return res
        except Exception as e:
            raise ValueError(f"Error evaluating index {name} with formula {formula}: {e}")


def stage_indices(
    bands_before: Dict[str, np.ndarray],
    bands_after_norm: Dict[str, np.ndarray],
    invalid: np.ndarray,
    cfg: Dict[str, Any],
    prov: Provenance,
    sensor_before: str = 'Sentinel-2',
    sensor_after: str = 'Sentinel-2'
) -> IndexStack:
    from backend.services.sensor_profile import SensorProfile
    prof_before = SensorProfile.load(sensor_before)
    prof_after = SensorProfile.load(sensor_after)

    with StageTimer(prov, "indices", {"sigma_k": cfg.get("sigma_k")}) as t:
        names = ["NDVI", "NDBI", "MNDWI", "BSI"]
        # Ensure required bands exist; synthesize missing from available
        def ensure(bands: Dict[str, np.ndarray], prof) -> Dict[str, np.ndarray]:
            out = dict(bands)
            bm = prof.band_mapping
            b11, b04, b08, b03, b02 = bm.get("B11","B11"), bm.get("B04","B04"), bm.get("B08","B08"), bm.get("B03","B03"), bm.get("B02","B02")
            if b11 not in out and b04 in out:
                out[b11] = out[b04] * 0.8
            if b08 not in out and b03 in out:
                out[b08] = out[b03] * 1.1
            if b02 not in out and b03 in out:
                out[b02] = out[b03]
            if b03 not in out and b02 in out:
                out[b03] = out[b02]
            if b04 not in out and b03 in out:
                out[b04] = out[b03]
            return out

        bb = ensure(bands_before, prof_before)
        ba = ensure(bands_after_norm, prof_after)
        before_idx = {n: compute_index(bb, n, cfg, prof_before) for n in names}
        after_idx = {n: compute_index(ba, n, cfg, prof_after) for n in names}
        delta = {n: after_idx[n] - before_idx[n] for n in names}

        valid = ~invalid
        sigma: Dict[str, float] = {}
        for n in names:
            # MAD over "stable-ish" pixels: those with small |delta| mid-quantile
            vals = delta[n][valid]
            if vals.size == 0:
                sigma[n] = 1e-6
            else:
                # use central 60% as proxy for stable noise
                lo, hi = np.quantile(vals, [0.2, 0.8])
                core = vals[(vals >= lo) & (vals <= hi)]
                sigma[n] = _mad_sigma(core)

        # Structural: gradient magnitude difference on NIR
        nir_b = bb.get("B08", bb.get("B04"))
        nir_a = ba.get("B08", ba.get("B04"))
        gb = cv2.Sobel(nir_b, cv2.CV_32F, 1, 1, ksize=3)
        ga = cv2.Sobel(nir_a, cv2.CV_32F, 1, 1, ksize=3)
        structural = np.abs(ga - gb).astype(np.float32)
        t.extras = {"sigma": sigma}
        return IndexStack(before_idx, after_idx, delta, sigma, structural)


# ---------------------------------------------------------------------------
# Stage 6: Candidate extraction
# ---------------------------------------------------------------------------

def stage_extract_candidates(
    indices: IndexStack,
    invalid: np.ndarray,
    grid: CommonGrid,
    cfg: Dict[str, Any],
    prov: Provenance,
    before_scene_id: str,
    after_scene_id: str,
) -> List[ChangeCandidate]:
    with StageTimer(prov, "extract_candidates", {"min_area_m2": cfg.get("min_area_m2")}) as t:
        valid = ~invalid
        k = float(cfg.get("sigma_k", 3.0))
        wts = cfg.get("score_weights") or {}

        def sig_map(name: str, abs_min_key: str) -> np.ndarray:
            d = indices.delta[name]
            sig = indices.sigma.get(name, 1e-6)
            abs_min = float(cfg.get(abs_min_key, 0.08))
            return (np.abs(d) > max(k * sig, abs_min)).astype(np.float32)

        score = (
            float(wts.get("ndvi", 0.25)) * sig_map("NDVI", "abs_min_ndvi")
            + float(wts.get("ndbi", 0.30)) * sig_map("NDBI", "abs_min_ndbi")
            + float(wts.get("mndwi", 0.20)) * sig_map("MNDWI", "abs_min_mndwi")
            + float(wts.get("bsi", 0.15)) * sig_map("BSI", "abs_min_bsi")
        )
        # structural contribution (normalized)
        st = indices.structural_diff.copy()
        st_valid = st[valid]
        if st_valid.size:
            st_thr = max(float(np.median(st_valid) + k * _mad_sigma(st_valid)), 1e-3)
            score = score + float(wts.get("structural", 0.10)) * (st > st_thr).astype(np.float32)

        score = np.where(valid, score, 0.0)

        # Adaptive threshold: Otsu on valid scores > 0, else k-based
        vals = score[valid]
        if vals.size and vals.max() > 0:
            # Otsu on scaled uint8
            u8 = np.clip(vals / max(vals.max(), 1e-6) * 255, 0, 255).astype(np.uint8)
            thr_u8, _ = cv2.threshold(u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            thr = float(thr_u8) / 255.0 * float(vals.max())
            thr = max(thr, 0.25)
        else:
            thr = 0.5

        binary = (score >= thr) & valid
        open_r = int(cfg.get("morph_open_px", 1))
        close_r = int(cfg.get("morph_close_px", 2))
        if open_r > 0:
            binary = binary_opening(binary, disk(open_r))
        if close_r > 0:
            binary = binary_closing(binary, disk(close_r))

        labeled = label(binary)
        res_m = float(grid.resolution_m or 10.0)
        px_area = res_m * res_m
        min_area = float(cfg.get("min_area_m2", 400.0))
        edge_thr = float(cfg.get("edge_alignment_threshold", 0.55))

        # Edge map for edge-alignment score
        edge = cv2.Canny(
            np.clip(indices.before["NDVI"] * 127 + 128, 0, 255).astype(np.uint8), 50, 150
        ) > 0

        candidates: List[ChangeCandidate] = []
        for prop in regionprops(labeled):
            area_m2 = float(prop.area) * px_area
            if area_m2 < min_area:
                continue
            coords = prop.coords  # (row, col)
            rr, cc = coords[:, 0], coords[:, 1]
            region = np.zeros_like(binary)
            region[rr, cc] = True

            # Compactness: 4πA / P²
            perim = float(prop.perimeter) if prop.perimeter else 1.0
            compactness = float(4 * np.pi * prop.area / (perim * perim + 1e-6))
            # Edge alignment: fraction of region pixels that are edges
            edge_align = float((region & edge).sum()) / float(max(prop.area, 1))

            minr, minc, maxr, maxc = prop.bbox
            # Geometry as GeoJSON in pixel space → approximate lon/lat if no transform
            geom = _region_to_geojson(region, grid)

            # Mean deltas over VALID pixels only inside region
            region_valid = region & valid
            evidence = {"score_mean": float(score[region_valid].mean()) if region_valid.any() else 0.0}
            for n in indices.delta:
                m, nvalid = _valid_stats(indices.delta[n], region_valid)
                evidence[f"delta_{n}"] = m
                evidence[f"n_{n}"] = nvalid
                evidence[f"sigma_{n}"] = indices.sigma[n]

            usable = float(region_valid.sum()) / float(max(region.sum(), 1))
            cand = ChangeCandidate(
                candidate_id=str(uuid.uuid4()),
                geometry_geojson=geom,
                area_m2=area_m2,
                change_type="unclassified",
                direction="appearance",
                confidence=0.0,
                confidence_label="low",
                confidence_breakdown={},
                evidence=evidence,
                before_scene_id=before_scene_id,
                after_scene_id=after_scene_id,
                usable_fraction=usable,
                method_label=prov.method_label,
                mask_label=region,
                bbox_px=(minr, maxr, minc, maxc),
            )
            if edge_align >= edge_thr and compactness < float(cfg.get("compactness_min", 0.15)):
                cand.suppression_reasons.append("edge_only_misregistration")
                cand.evidence["edge_alignment"] = edge_align
                cand.evidence["compactness"] = compactness
            else:
                cand.evidence["edge_alignment"] = edge_align
                cand.evidence["compactness"] = compactness
            candidates.append(cand)

        t.extras = {"n_candidates": len(candidates), "threshold": thr}
        return candidates


def _region_to_geojson(region: np.ndarray, grid: CommonGrid) -> Dict[str, Any]:
    """Polygonize region; use affine transform when available else pixel coords as lon/lat stubs."""
    try:
        from rasterio import features as rio_features
        from shapely.geometry import shape, mapping
        from shapely.ops import transform as shapely_transform
        import pyproj

        shapes = list(rio_features.shapes(region.astype(np.uint8), mask=region, transform=grid.transform))
        if shapes and grid.transform is not None:
            geom = shape(shapes[0][0])
            if grid.crs is not None:
                try:
                    crs_str = grid.crs.to_string() if hasattr(grid.crs, "to_string") else str(grid.crs)
                    if "4326" not in crs_str:
                        transformer = pyproj.Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
                        geom = shapely_transform(transformer.transform, geom)
                except Exception:
                    pass
            geom = geom.simplify(0.00001)
            return mapping(geom)
    except Exception:
        pass

    # Fallback: bbox polygon in pixel indices (tests)
    ys, xs = np.where(region)
    if len(xs) == 0:
        return {"type": "Polygon", "coordinates": [[]]}
    minx, maxx = float(xs.min()), float(xs.max())
    miny, maxy = float(ys.min()), float(ys.max())
    return {
        "type": "Polygon",
        "coordinates": [[
            [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny],
        ]],
    }


# ---------------------------------------------------------------------------
# Stage 7: Change typing
# ---------------------------------------------------------------------------

def stage_type_candidates(
    candidates: List[ChangeCandidate],
    indices: IndexStack,
    invalid: np.ndarray,
    cfg: Dict[str, Any],
    prov: Provenance,
) -> List[ChangeCandidate]:
    with StageTimer(prov, "typing", {}) as t:
        valid = ~invalid
        rules = cfg.get("change_rules", [])

        for cand in candidates:
            if cand.mask_label is None:
                continue
            region = cand.mask_label & valid
            if not region.any():
                cand.change_type = "unclassified"
                continue

            def mean_idx(stack: Dict[str, np.ndarray], name: str) -> float:
                m, _ = _valid_stats(stack[name], region)
                return m

            # Provide context for rule evaluation
            env = dict(cfg)  # include config values directly
            env.update({
                "ndvi_before": mean_idx(indices.before, "NDVI"),
                "ndvi_after": mean_idx(indices.after, "NDVI"),
                "ndbi_before": mean_idx(indices.before, "NDBI"),
                "ndbi_after": mean_idx(indices.after, "NDBI"),
                "mndwi_before": mean_idx(indices.before, "MNDWI"),
                "mndwi_after": mean_idx(indices.after, "MNDWI"),
                "bsi_before": mean_idx(indices.before, "BSI"),
                "bsi_after": mean_idx(indices.after, "BSI"),
                "compactness": cand.evidence.get("compactness", 1.0),
            })
            
            # deltas
            env["d_ndvi"] = env["ndvi_after"] - env["ndvi_before"]
            env["d_ndbi"] = env["ndbi_after"] - env["ndbi_before"]
            env["d_mndwi"] = env["mndwi_after"] - env["mndwi_before"]
            env["d_bsi"] = env["bsi_after"] - env["bsi_before"]

            # Aspect ratio
            env["aspect"] = 1.0
            if cand.bbox_px:
                r0, r1, c0, c1 = cand.bbox_px
                h, w = max(r1 - r0, 1), max(c1 - c0, 1)
                env["aspect"] = max(h, w) / float(min(h, w))

            # Record evidence
            cand.evidence.update({
                "ndvi_before": env["ndvi_before"], "ndvi_after": env["ndvi_after"],
                "ndbi_before": env["ndbi_before"], "ndbi_after": env["ndbi_after"],
                "mndwi_before": env["mndwi_before"], "mndwi_after": env["mndwi_after"],
                "bsi_before": env["bsi_before"], "bsi_after": env["bsi_after"],
                "aspect_ratio": env["aspect"]
            })

            ctype = "unclassified"
            direction = "appearance"
            rule_fired = None

            # Rule engine evaluation
            for rule in rules:
                try:
                    passed = all(eval(cond, {"__builtins__": None, "abs": abs}, env) for cond in rule["conditions"])
                    if passed:
                        ctype = rule["output_type"]
                        direction = rule["direction"]
                        rule_fired = rule["name"]
                        break
                except Exception as exc:
                    prov.warn(f"Rule evaluation failed for {rule['name']}: {exc}")
            
            # Post-rule override for phenology setting
            if ctype == "vegetation_growth" and cfg.get("phenology_ndvi_only_as_seasonal", True):
                ctype = "seasonal_or_uncertain"
                rule_fired = "vegetation_growth_as_seasonal"

            cand.change_type = ctype
            cand.direction = direction
            cand.evidence["rule_fired"] = rule_fired

        t.extras = {"types": {c.change_type: 0 for c in candidates}}
        for c in candidates:
            t.extras["types"][c.change_type] = t.extras["types"].get(c.change_type, 0) + 1
        return candidates


# ---------------------------------------------------------------------------
# Stage 8: False-alarm suppression
# ---------------------------------------------------------------------------

def stage_suppress(
    candidates: List[ChangeCandidate],
    indices: IndexStack,
    quality: QualityMaskResult,
    registration: RegistrationResult,
    cfg: Dict[str, Any],
    prov: Provenance,
    *,
    doy_diff: int = 0,
    same_sensor: bool = True,
    persistence_counts: Optional[Dict[str, int]] = None,
) -> Tuple[List[ChangeCandidate], List[ChangeCandidate]]:
    """Returns (kept, suppressed)."""
    with StageTimer(prov, "suppression", {}) as t:
        kept: List[ChangeCandidate] = []
        suppressed: List[ChangeCandidate] = []
        persistence_counts = persistence_counts or {}
        opp_doy = int(cfg.get("opposite_season_doy_diff", 90))
        cloud_r = int(cfg.get("cloud_proximity_radius_px", 15))
        cloud_frac = float(cfg.get("cloud_neighbourhood_mask_frac", 0.35))

        for cand in candidates:
            reasons: List[str] = list(cand.suppression_reasons)

            # Season
            if doy_diff >= opp_doy:
                reasons.append("opposite_season")
                prov.warn("Pair spans opposite seasons (DOY gap)")

            # Seasonal / phenology
            if cand.change_type == "seasonal_or_uncertain" and not cfg.get("report_seasonal", False):
                reasons.append("seasonal_or_uncertain")
                cand.rejected = True
                cand.rejection_reason = "seasonal_or_uncertain"
                cand.suppression_reasons = reasons
                suppressed.append(cand)
                continue

            # Phenology: veg→veg NDVI-only
            if (cfg.get("phenology_ndvi_only_as_seasonal", True)
                    and cand.evidence.get("rule_fired") in (
                        "ndvi_only_veg_veg", "vegetation_growth_as_seasonal", "vegetation_loss_as_seasonal"
                    )):
                if "seasonal_phenology" not in reasons:
                    reasons.append("seasonal_phenology")
                cand.rejected = True
                cand.rejection_reason = "seasonal_phenology"
                cand.suppression_reasons = reasons
                suppressed.append(cand)
                continue

            # Cross-sensor
            if not same_sensor and not cfg.get("allow_cross_sensor", False):
                reasons.append("cross_sensor")
                cand.rejected = True
                cand.rejection_reason = "cross_sensor"
                cand.suppression_reasons = reasons
                suppressed.append(cand)
                continue

            # Registration edge-only
            if registration.quality == "poor" and "edge_only_misregistration" in reasons:
                cand.rejected = True
                cand.rejection_reason = "poor_registration_edge_only"
                cand.suppression_reasons = reasons
                suppressed.append(cand)
                continue

            # Cloud proximity / shadow next to cloud
            if cand.mask_label is not None:
                dil_cloud = ndimage.binary_dilation(
                    quality.after_cloud | quality.before_cloud, iterations=max(cloud_r, 1)
                )
                neigh = ndimage.binary_dilation(cand.mask_label, iterations=3)
                mask_frac = float((neigh & quality.invalid).sum()) / float(max(neigh.sum(), 1))
                if mask_frac >= cloud_frac:
                    reasons.append("cloud_proximity")
                # Shadow heuristic: dark after + near cloud
                if cand.mask_label is not None and "B04" in indices.after:
                    # use brightness proxy from after NDVI/BSI region
                    bright = indices.after.get("BSI")
                    if bright is None:
                        bright = indices.after["NDVI"]
                    m, _ = _valid_stats(bright, cand.mask_label & ~quality.invalid)
                    near_cloud = float((cand.mask_label & dil_cloud).sum()) / float(max(cand.mask_label.sum(), 1))
                    if near_cloud > 0.3 and np.isfinite(m) and m < -0.05 and cand.change_type in (
                        "clearance", "unclassified", "construction"
                    ):
                        reasons.append("cloud_shadow_suspect")
                        cand.rejected = True
                        cand.rejection_reason = "cloud_shadow_suspect"
                        cand.suppression_reasons = reasons
                        suppressed.append(cand)
                        continue

            # Illumination: if evidence looks like global bias only — handled at pair level;
            # per-candidate: very low structural + uniform small deltas across types → skip
            if abs(cand.evidence.get("delta_NDVI", 0) or 0) < float(cfg.get("abs_min_ndvi", 0.08)) * 0.5 \
                    and abs(cand.evidence.get("delta_NDBI", 0) or 0) < float(cfg.get("abs_min_ndbi", 0.08)) * 0.5 \
                    and cand.evidence.get("score_mean", 0) < 0.2:
                reasons.append("weak_signal")
                cand.rejected = True
                cand.rejection_reason = "weak_signal"
                cand.suppression_reasons = reasons
                suppressed.append(cand)
                continue

            # Persistence flag (not necessarily reject)
            pcount = persistence_counts.get(cand.candidate_id, 0)
            cand.persistence_count = pcount
            if pcount < int(cfg.get("min_persistence_obs", 1)):
                reasons.append("single_observation")

            cand.suppression_reasons = reasons
            # Downweight-only reasons keep the candidate
            if cand.rejected:
                suppressed.append(cand)
            else:
                kept.append(cand)

        t.extras = {"kept": len(kept), "suppressed": len(suppressed)}
        return kept, suppressed


# ---------------------------------------------------------------------------
# Stage 9: Confidence
# ---------------------------------------------------------------------------

def stage_confidence(
    candidates: List[ChangeCandidate],
    quality: QualityMaskResult,
    registration: RegistrationResult,
    cfg: Dict[str, Any],
    prov: Provenance,
    *,
    doy_diff: int = 0,
) -> List[ChangeCandidate]:
    with StageTimer(prov, "confidence", {}) as t:
        w = cfg.get("confidence_weights") or {}
        pens = cfg.get("confidence_penalties") or {}
        high = float(cfg.get("high_confidence", 0.75))
        med = float(cfg.get("medium_confidence", 0.5))
        opp = int(cfg.get("opposite_season_doy_diff", 90))

        out = []
        for cand in candidates:
            # Components 0-1
            usable = float(np.clip(cand.usable_fraction, 0, 1))
            # magnitude in sigma units (NDBI or NDVI)
            mag = 0.0
            for key in ("NDBI", "NDVI", "MNDWI", "BSI"):
                d = abs(cand.evidence.get(f"delta_{key}") or 0.0)
                sig = max(cand.evidence.get(f"sigma_{key}") or 1e-6, 1e-6)
                mag = max(mag, min(d / (3 * sig), 1.0))
            persistence = 1.0 if cand.persistence_count >= int(cfg.get("min_persistence_obs", 1)) else 0.35
            reg = 1.0 if registration.quality == "good" else (0.5 if registration.quality == "poor" else 0.7)
            rule_ok = 1.0 if cand.evidence.get("rule_fired") and cand.change_type != "unclassified" else 0.4
            shape = float(np.clip(cand.evidence.get("compactness") or 0.3, 0, 1))
            same_season = 1.0 if doy_diff < opp else 0.3

            breakdown = {
                "usable_fraction": usable,
                "magnitude_sigma": mag,
                "persistence": persistence,
                "registration": reg,
                "rule_consistency": rule_ok,
                "shape": shape,
                "same_season": same_season,
            }
            score = sum(float(w.get(k, 0)) * v for k, v in breakdown.items())

            penalty = 1.0
            applied = []
            if quality.no_product_mask:
                penalty *= float(pens.get("no_mask", 0.7))
                applied.append("no_mask")
            if "single_observation" in cand.suppression_reasons:
                penalty *= float(pens.get("single_observation", 0.75))
                applied.append("single_observation")
            if "cloud_proximity" in cand.suppression_reasons:
                penalty *= float(pens.get("cloud_proximity", 0.8))
                applied.append("cloud_proximity")
            if registration.quality == "poor":
                penalty *= float(pens.get("poor_registration", 0.7))
                applied.append("poor_registration")
            if "opposite_season" in cand.suppression_reasons:
                penalty *= float(pens.get("opposite_season", 0.85))
                applied.append("opposite_season")

            conf = float(np.clip(score * penalty, 0, 1))
            if quality.no_product_mask:
                conf = min(conf, float(cfg.get("no_mask_confidence_cap", 0.5)))
            if not same_sensor_cap_ok(cfg) and False:
                pass

            if cand.change_type == "unclassified" and conf < float(cfg.get("unclassified_confidence_min", 0.75)):
                cand.rejected = True
                cand.rejection_reason = "unclassified_low_confidence"
                cand.suppression_reasons = list(cand.suppression_reasons) + ["unclassified_low_confidence"]

            label = "high" if conf >= high else ("medium" if conf >= med else "low")
            cand.confidence = conf
            cand.confidence_label = label
            cand.confidence_breakdown = {
                **breakdown,
                "weighted_score": score,
                "penalty": penalty,
                "penalties_applied": applied,
                "confidence": conf,
            }
            out.append(cand)

        t.extras = {"n": len(out)}
        return out


def same_sensor_cap_ok(cfg):
    return True


# ---------------------------------------------------------------------------
# Stage 10: Earliest supporting observation
# ---------------------------------------------------------------------------

def find_earliest_supporting_observation(
    candidate: ChangeCandidate,
    series: Sequence[Dict[str, Any]],
    cfg: Dict[str, Any],
    prov: Optional[Provenance] = None,
) -> ChangeCandidate:
    """
    series items: {scene_id, date, usable_fraction, indicator} where indicator is
    the type-specific mean value inside the polygon (higher/lower depending on type).
    """
    t0 = __import__("time").perf_counter()
    min_frac = float(cfg.get("min_polygon_usable_fraction", 0.7))
    usable = [s for s in series if float(s.get("usable_fraction", 0)) >= min_frac]
    skipped = [s["scene_id"] for s in series if float(s.get("usable_fraction", 0)) < min_frac]

    if len(usable) < 3:
        candidate.low_temporal_support = True
        candidate.earliest_scene_id = candidate.after_scene_id
        candidate.earliest_date = next(
            (s["date"] for s in series if s["scene_id"] == candidate.after_scene_id), ""
        )
        candidate.last_clear_before_date = next(
            (s["date"] for s in series if s["scene_id"] == candidate.before_scene_id), ""
        )
        d0 = parse_date(candidate.last_clear_before_date)
        d1 = parse_date(candidate.earliest_date)
        if d0 and d1:
            candidate.detection_window_days = abs((d1 - d0).days)
        candidate.skipped_scenes = skipped
        if prov:
            prov.record("earliest_observation", {"low_temporal_support": True},
                        __import__("time").perf_counter() - t0,
                        {"skipped": skipped})
        return candidate

    # Sort by date
    usable = sorted(usable, key=lambda s: s["date"])
    values = np.array([float(s["indicator"]) for s in usable], dtype=np.float64)

    # Step-fit changepoint: minimise SSE for one step
    best_i, best_sse = 1, float("inf")
    for i in range(1, len(values)):
        left, right = values[:i], values[i:]
        sse = float(((left - left.mean()) ** 2).sum() + ((right - right.mean()) ** 2).sum())
        if sse < best_sse:
            best_sse, best_i = sse, i

    # Require significant step
    left, right = values[:best_i], values[best_i:]
    if abs(right.mean() - left.mean()) < max(0.05, 0.5 * _mad_sigma(values)):
        # weak changepoint — use after scene
        best_i = next(
            (i for i, s in enumerate(usable) if s["scene_id"] == candidate.after_scene_id),
            len(usable) - 1,
        )

    after_obs = usable[best_i]
    before_obs = usable[best_i - 1] if best_i > 0 else usable[0]
    candidate.earliest_scene_id = after_obs["scene_id"]
    candidate.earliest_date = after_obs["date"]
    candidate.last_clear_before_date = before_obs["date"]
    d0 = parse_date(before_obs["date"])
    d1 = parse_date(after_obs["date"])
    candidate.detection_window_days = float(abs((d1 - d0).days)) if d0 and d1 else 0.0
    candidate.skipped_scenes = skipped
    # Cloudy scenes between before_obs and after_obs
    mid_skipped = [
        s["scene_id"] for s in series
        if before_obs["date"] < s["date"] < after_obs["date"]
        and float(s.get("usable_fraction", 0)) < min_frac
    ]
    candidate.skipped_scenes = list(dict.fromkeys(skipped + mid_skipped))

    if prov:
        prov.record(
            "earliest_observation",
            {"changepoint_index": best_i},
            __import__("time").perf_counter() - t0,
            {
                "earliest_scene_id": candidate.earliest_scene_id,
                "last_clear_before": candidate.last_clear_before_date,
                "detection_window_days": candidate.detection_window_days,
                "skipped": candidate.skipped_scenes,
            },
        )
    return candidate
