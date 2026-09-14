"""Central project configuration.

Every Python stage imports settings from this module.  For a new surface/case,
edit only ``config/case.json``; do not edit paths/constants inside stage files.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "case.json"


@dataclass(frozen=True)
class CaseConfig:
    raw: dict
    config_path: Path

    @property
    def case_id(self) -> str:
        return str(self.raw["case_id"])

    @property
    def L(self) -> float:
        return float(self.raw["cell_size_mm"])

    @property
    def level(self) -> float:
        return float(self.raw.get("iso_level", 0.0))

    @property
    def expression(self) -> str:
        return str(self.raw["surface_expression"])

    @property
    def n_intervals(self) -> int:
        return int(self.raw["topology_sampling_intervals"])

    @property
    def boundary_spacing(self) -> float:
        return float(self.raw["boundary_target_spacing_mm"])

    @property
    def cgal(self) -> dict:
        return self.raw["cgal"]

    @property
    def tol(self) -> dict:
        return self.raw["tolerances"]

    @property
    def abaqus(self) -> dict:
        return self.raw["abaqus"]

    @property
    def case_dir(self) -> Path:
        return PROJECT_ROOT / "cases" / self.case_id

    @property
    def cgal_input_dir(self) -> Path:
        return self.case_dir / "cgal_input"

    @property
    def cgal_output_dir(self) -> Path:
        return self.case_dir / "cgal_output"

    @property
    def shell_dir(self) -> Path:
        return self.case_dir / "shell"

    @property
    def abaqus_dir(self) -> Path:
        return self.case_dir / "abaqus_meshcheck"

    @property
    def mesh_prefix(self) -> str:
        return f"{self.case_id}_mesh"

    @property
    def meshcheck_job(self) -> str:
        return f"{self.case_id}_meshcheck"

    def ensure_dirs(self) -> None:
        for p in (self.case_dir, self.cgal_input_dir, self.cgal_output_dir,
                  self.shell_dir, self.abaqus_dir):
            p.mkdir(parents=True, exist_ok=True)


def load_config(path: Path | str = DEFAULT_CONFIG) -> CaseConfig:
    path = Path(path).resolve()
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    cfg = CaseConfig(raw=raw, config_path=path)
    cfg.ensure_dirs()
    return cfg


CFG = load_config()
