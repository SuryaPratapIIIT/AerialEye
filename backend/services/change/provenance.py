"""
Change-detection Provenance: every stage appends name, params, versions, runtime.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def _lib_versions() -> Dict[str, str]:
    vers: Dict[str, str] = {}
    for name, mod in (
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("cv2", "cv2"),
        ("skimage", "skimage"),
        ("shapely", "shapely"),
        ("sklearn", "sklearn"),
        ("rasterio", "rasterio"),
    ):
        try:
            m = __import__(mod)
            vers[name] = getattr(m, "__version__", "unknown")
        except Exception:
            vers[name] = "unavailable"
    return vers


@dataclass
class Provenance:
    stages: List[Dict[str, Any]] = field(default_factory=list)
    library_versions: Dict[str, str] = field(default_factory=_lib_versions)
    warnings: List[str] = field(default_factory=list)
    method_label: str = "REAL"
    pipeline_version: str = "change-v1"

    def record(
        self,
        stage: str,
        params: Optional[Dict[str, Any]] = None,
        runtime_s: float = 0.0,
        extras: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "stage": stage,
            "params": params or {},
            "runtime_s": round(float(runtime_s), 6),
            "library_versions": dict(self.library_versions),
        }
        if extras:
            entry["extras"] = extras
        self.stages.append(entry)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StageTimer:
    """Context manager that records stage runtime into Provenance."""

    def __init__(self, prov: Provenance, stage: str, params: Optional[Dict[str, Any]] = None):
        self.prov = prov
        self.stage = stage
        self.params = params or {}
        self.extras: Dict[str, Any] = {}
        self._t0 = 0.0

    def __enter__(self) -> "StageTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        dt = time.perf_counter() - self._t0
        self.prov.record(self.stage, self.params, dt, self.extras or None)
