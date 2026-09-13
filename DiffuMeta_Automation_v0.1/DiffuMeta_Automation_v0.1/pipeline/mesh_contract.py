from __future__ import annotations

import csv
import numpy as np

from .common import PipelineError, read_json, file_hash


def load_bundle(npz_path, report_path, pair_csv=None):
    report = read_json(report_path)
    if report.get("pass") is not True:
        raise PipelineError("MESH_QA_FAILED", "Step 05 report did not PASS.")
    with np.load(npz_path, allow_pickle=False) as data:
        arrays = {k: data[k].copy() for k in ("nodes", "triangles", "x_pairs", "y_pairs", "z_pairs")}
    nodes, triangles = arrays["nodes"], arrays["triangles"]
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not len(nodes) or not np.isfinite(nodes).all():
        raise PipelineError("MESH_CONTRACT_INVALID", "Invalid coordinates.")
    if (triangles.ndim != 2 or triangles.shape[1] != 3 or not len(triangles)
            or triangles.dtype.kind not in "iu" or triangles.min() < 0 or triangles.max() >= len(nodes)):
        raise PipelineError("MESH_CONTRACT_INVALID", "Connectivity must be integer, zero based and in range.")
    if report["nodes"] != len(nodes) or report["triangles"] != len(triangles):
        raise PipelineError("MESH_REPORT_MISMATCH", "Counts differ from the Step 05 report.")
    L = float(report["cell_size_mm"])
    if not np.isfinite(L) or L <= 0 or nodes.min() < -1e-8 or nodes.max() > L + 1e-8:
        raise PipelineError("MESH_CONTRACT_INVALID", "Invalid cell bounds.")
    points = nodes[triangles]
    areas = np.linalg.norm(np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0]), axis=1) / 2
    if not np.isfinite(areas).all() or np.any(areas <= 1e-14):
        raise PipelineError("MESH_CONTRACT_INVALID", "Invalid triangle area.")
    area = float(areas.sum())
    if not np.isclose(area, report["surface_area_mm2"], rtol=1e-9, atol=1e-10):
        raise PipelineError("MESH_REPORT_MISMATCH", "Area differs from the Step 05 report.")
    csv_expected = set()
    for axis, key in enumerate(("x_pairs", "y_pairs", "z_pairs")):
        pairs = arrays[key]
        if (pairs.ndim != 2 or pairs.shape[1] != 2 or not len(pairs)
                or pairs.dtype.kind not in "iu" or pairs.min() < 0 or pairs.max() >= len(nodes)):
            raise PipelineError("MESH_CONTRACT_INVALID", "Invalid periodic pair array: " + key)
        target = np.eye(3)[axis] * L
        if np.linalg.norm(nodes[pairs[:, 1]] - nodes[pairs[:, 0]] - target, axis=1).max() > 1e-8:
            raise PipelineError("PBC_GEOMETRY_MISMATCH", key)
        for side, value in enumerate((0.0, L)):
            boundary = set(np.flatnonzero(np.abs(nodes[:, axis] - value) <= 1e-8))
            if len(np.unique(pairs[:, side])) != len(pairs) or set(pairs[:, side]) != boundary:
                raise PipelineError("PBC_COVERAGE_MISMATCH", key)
        csv_expected.update(("XYZ"[axis], int(a) + 1, int(b) + 1) for a, b in pairs)
    if pair_csv:
        with open(pair_csv, encoding="utf-8-sig", newline="") as stream:
            csv_rows = list(csv.DictReader(stream))
        actual = {(r["axis"].strip().upper(), int(r["low_node"]), int(r["high_node"])) for r in csv_rows}
        if actual != csv_expected or len(actual) != len(csv_rows):
            raise PipelineError("CSV_NPZ_MISMATCH", "CSV uses one-based labels and must match NPZ exactly.")
        for row in csv_rows:
            low, high = int(row["low_node"]) - 1, int(row["high_node"]) - 1
            vector = np.array([float(row[k]) for k in ("dx", "dy", "dz")])
            if not np.isfinite(vector).all() or np.linalg.norm(vector - (nodes[high] - nodes[low])) > 1e-8:
                raise PipelineError("CSV_NPZ_MISMATCH", "CSV displacement vector differs from mesh.")
    arrays.update({"report": report, "area_mm2": area, "L_mm": L,
                   "source_hashes": {"npz": file_hash(npz_path), "report": file_hash(report_path),
                                     "pairs_csv": file_hash(pair_csv) if pair_csv else None}})
    return arrays
