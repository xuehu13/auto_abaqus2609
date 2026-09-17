"""Shared test helpers: locate the real Fig.1 mesh, or build a synthetic one.

Nothing here calls Abaqus or the frozen mesher. The synthetic bundle is a tiny
complete periodic surface used to exercise the mesh contract and the PBC solver
without depending on the git-ignored work/ tree.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/fig1_20pct_regression"
FINGERPRINTS = json.loads((FIXTURE / "deck_sha256.json").read_text(encoding="utf-8"))
SIMULATION = ROOT / "config/simulation.json"
CASE = ROOT / "config/cases/fig1.json"

#: Two square faces opposite each other in z, i.e. a closed periodic cell with
#: boundary nodes on all six sides. Node indices are zero based.
_CUBE_NODES = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]])
_CUBE_TRIANGLES = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6]], dtype=np.int32)
_CUBE_X_PAIRS = np.array([[0, 1], [3, 2], [4, 5], [7, 6]], dtype=np.int32)
_CUBE_Y_PAIRS = np.array([[0, 3], [1, 2], [4, 7], [5, 6]], dtype=np.int32)
_CUBE_Z_PAIRS = np.array([[0, 4], [1, 5], [2, 6], [3, 7]], dtype=np.int32)


def fig1_bundle():
    """Locate the local Fig.1 mesh bundle (validated by SHA); None when unavailable."""
    from pipeline.common import file_hash
    from pipeline.mesh import load_bundle

    expected = FINGERPRINTS["mesh_source_hashes"]
    work = ROOT / "work"
    if not work.is_dir():
        return None
    for npz in sorted(work.glob("**/fig1_shell.npz")):
        if file_hash(npz) != expected["npz"]:
            continue
        report = npz.with_name("fig1_shell_report.json")
        pairs = npz.parents[1] / "abaqus_meshcheck/fig1_periodic_pairs.csv"
        if not report.is_file() or not pairs.is_file():
            continue
        if file_hash(pairs) != expected["pairs_csv"]:
            continue
        try:
            load_bundle(npz, report, pairs)
        except Exception:                      # noqa: BLE001 - any contract failure means "not it"
            continue
        return npz, report, pairs
    return None


def synthetic_bundle(folder):
    """Write a tiny valid mesh bundle (npz + report + pairs CSV) and return its paths."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    npz = folder / "mini_shell.npz"
    report = folder / "mini_shell_report.json"
    pairs = folder / "mini_periodic_pairs.csv"
    write_bundle(npz, report, pairs)
    return npz, report, pairs


def write_bundle(npz, report, pairs, *, nodes=None, triangles=None, x_pairs=None, y_pairs=None,
                 z_pairs=None, report_overrides=None, csv_rows=None):
    """Write a bundle, allowing any of its parts to be replaced by a broken variant."""
    nodes = _CUBE_NODES if nodes is None else nodes
    triangles = _CUBE_TRIANGLES if triangles is None else triangles
    x_pairs = _CUBE_X_PAIRS if x_pairs is None else x_pairs
    y_pairs = _CUBE_Y_PAIRS if y_pairs is None else y_pairs
    z_pairs = _CUBE_Z_PAIRS if z_pairs is None else z_pairs
    np.savez(npz, nodes=nodes, triangles=triangles, x_pairs=x_pairs, y_pairs=y_pairs,
             z_pairs=z_pairs)
    document = {"pass": True, "case_id": "mini", "cell_size_mm": 1.0, "nodes": len(nodes),
                "triangles": len(triangles), "surface_area_mm2": 2.0}
    document.update(report_overrides or {})
    Path(report).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if csv_rows is None:
        csv_rows = []
        for axis, axis_pairs in zip("XYZ", (x_pairs, y_pairs, z_pairs)):
            for low, high in axis_pairs:
                delta = nodes[int(high)] - nodes[int(low)]
                csv_rows.append([axis, int(low) + 1, int(high) + 1,
                                 delta[0], delta[1], delta[2]])
    with open(pairs, "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["axis", "low_node", "high_node", "dx", "dy", "dz"])
        writer.writerows(csv_rows)
    return npz, report, pairs


def simulation(*, mutate=None):
    """Load config/simulation.json, optionally with a mutation applied in memory."""
    document = json.loads(SIMULATION.read_text(encoding="utf-8"))
    if mutate is not None:
        mutate(document)
    return document


def write_simulation(folder, *, mutate=None, name="simulation.json"):
    """Write a (possibly mutated) simulation config into a temporary folder."""
    document = simulation(mutate=mutate)
    path = Path(folder) / name
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def write_synthetic_simulation(folder, *, mutate=None, name="simulation.json"):
    """Simulation config adapted to the 1 mm synthetic cell.

    The platen width (``width_factor * cell_size``) must be an exact integer number
    of platen elements, so for the synthetic cell the platen mesh size is 0.9 mm
    instead of 1.0 mm. Everything else stays the Fig.1 config.
    """
    def adapt(document):
        document["platen"]["mesh_size_mm"] = 0.9
        if mutate is not None:
            mutate(document)

    return write_simulation(folder, mutate=adapt, name=name)
