import sys
import re

with open('backend/services/change/stages.py', 'r') as f:
    content = f.read()

# 1. Replace _scl_invalid and stage_quality_mask logic
new_quality = '''def stage_quality_mask(
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
        )'''
content = re.sub(r'def _scl_invalid.*?def stage_quality_mask.*?return QualityMaskResult.*?\n        \)', new_quality, content, flags=re.DOTALL)

# 2. Replace compute_index
new_compute = '''def compute_index(bands: Dict[str, np.ndarray], name: str, cfg: Dict[str, Any], prof) -> np.ndarray:
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
'''
content = re.sub(r'def compute_index.*?raise ValueError\(f"Unknown index \{name\}"\)\n\n', new_compute + '\n', content, flags=re.DOTALL)

# Modify stage_indices to pass prof and cfg to compute_index
new_stage_indices_start = '''def stage_indices(
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
        after_idx = {n: compute_index(ba, n, cfg, prof_after) for n in names}'''

content = re.sub(r'def stage_indices\(.*?after_idx = \{n: compute_index\(ba, n\) for n in names\}', new_stage_indices_start, content, flags=re.DOTALL)


# 3. Refactor stage_type_candidates to use rule engine
new_type_cands = '''def stage_type_candidates(
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
        return candidates'''

content = re.sub(r'def stage_type_candidates\(.*?return candidates', new_type_cands, content, flags=re.DOTALL)


with open('backend/services/change/stages.py', 'w') as f:
    f.write(content)
