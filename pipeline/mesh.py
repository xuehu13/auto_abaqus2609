"""Mesh side: case config, frozen-vendor case file, mesh contract and PBC.

Three jobs, all before anything Abaqus is involved:

1. Parse ``config/cases/<case_id>.json`` and rebuild the flat legacy JSON the
   FROZEN vendor stages read (the vendor tree itself is never edited).
2. Check the mesh stage 05 accepted: NPZ <-> report <-> periodic pairs CSV.
3. Compute the lateral PBC equations and write the FE ingredients
   (``shell_mesh.inc``, ``lateral_pbc.inc``, ``pbc_map.json``).

Only the Python standard library and NumPy are used; no Abaqus keyword is
emitted for material/step/contact here (that is pipeline/build.py).
"""
from __future__ import annotations

from collections import defaultdict, deque
import csv
from pathlib import Path
import shutil
import subprocess

import numpy as np

from .common import (PipelineError, atomic_text, file_hash, finite, positive_int,
                     read_json, require_keys, safe_id, write_json)

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "periodic_surface_mesher_v1.0"

_CASE_REQUIRED = ("case_id", "surface_expression", "iso_level", "unit_cell_size_mm", "mesh")
_MESH_REQUIRED = ("topology_sampling_intervals", "boundary_target_spacing_mm",
                  "cgal", "tolerances", "meshcheck")
_CGAL_KEYS = ("edge_size_mm", "facet_angle_deg", "facet_size_mm", "facet_distance_mm",
              "cell_radius_edge_ratio", "cell_size_mm", "random_seed")
_TOLERANCE_KEYS = ("snap_mm", "topology_pair_mm", "boundary_mm", "feature_plane_mm",
                   "feature_periodic_mm", "dedup_mm", "final_pair_mm", "area_mm2")
#: Placeholder material the frozen stage 06 writes into the mesh-check INP. It is
#: a mesher fixture, NOT a production material: production material lives in
#: config/simulation.json.
_MESHCHECK_KEYS = ("material_E", "material_nu", "thickness_mm")


def load_case(path, document=None):
    """Load and validate a case (surface + mesh) config.

    ``document`` takes an already-built case dict (batch: defaults merged with one
    JSONL record); ``path`` is then only used for error messages.
    """
    case = require_keys(document if document is not None else read_json(path), path,
                        _CASE_REQUIRED, (), "case config")
    if not isinstance(case["case_id"], str) or not case["case_id"].strip():
        raise PipelineError("CONFIG_INVALID", "case.case_id must be a non-empty string.")
    if not isinstance(case["surface_expression"], str) or not case["surface_expression"].strip():
        raise PipelineError("CONFIG_INVALID", "case.surface_expression must be a non-empty string.")
    finite(case["iso_level"], "case.iso_level")
    finite(case["unit_cell_size_mm"], "case.unit_cell_size_mm", positive=True)
    mesh = require_keys(case["mesh"], path, _MESH_REQUIRED, (), "case.mesh")
    positive_int(mesh["topology_sampling_intervals"], "case.mesh.topology_sampling_intervals")
    finite(mesh["boundary_target_spacing_mm"], "case.mesh.boundary_target_spacing_mm", positive=True)
    cgal = require_keys(mesh["cgal"], path, _CGAL_KEYS, (), "case.mesh.cgal")
    for key in _CGAL_KEYS:
        finite(cgal[key], "case.mesh.cgal." + key, positive=True)
    if isinstance(cgal["random_seed"], bool) or not isinstance(cgal["random_seed"], int):
        raise PipelineError("CONFIG_INVALID", "case.mesh.cgal.random_seed must be an integer.")
    tolerances = require_keys(mesh["tolerances"], path, _TOLERANCE_KEYS, (), "case.mesh.tolerances")
    for key in _TOLERANCE_KEYS:
        finite(tolerances[key], "case.mesh.tolerances." + key, positive=True)
    meshcheck = require_keys(mesh["meshcheck"], path, _MESHCHECK_KEYS, (), "case.mesh.meshcheck")
    finite(meshcheck["material_E"], "case.mesh.meshcheck.material_E", positive=True)
    finite(meshcheck["material_nu"], "case.mesh.meshcheck.material_nu")
    finite(meshcheck["thickness_mm"], "case.mesh.meshcheck.thickness_mm", positive=True)
    return case


def vendor_case(case):
    """Rebuild the flat legacy case JSON the frozen vendor stages read.

    The vendor's key names are fixed by its own ``meshlib/config.py``; this is the
    only place in this repository that knows about them.
    """
    mesh = case["mesh"]
    meshcheck = mesh["meshcheck"]
    return {
        "case_id": case["case_id"],
        "cell_size_mm": case["unit_cell_size_mm"],
        "iso_level": case["iso_level"],
        "surface_expression": case["surface_expression"],
        "topology_sampling_intervals": mesh["topology_sampling_intervals"],
        "boundary_target_spacing_mm": mesh["boundary_target_spacing_mm"],
        "cgal": dict(mesh["cgal"]),
        "tolerances": dict(mesh["tolerances"]),
        "abaqus": {"meshcheck_material_E": meshcheck["material_E"],
                   "meshcheck_material_nu": meshcheck["material_nu"],
                   "meshcheck_thickness_mm": meshcheck["thickness_mm"]},
    }


def load_bundle(npz_path, report_path, pair_csv):
    """Validate the frozen stage-05 mesh and return its arrays plus metadata.

    Rejects a non-PASS report, broken connectivity, a wrong node count and any
    periodicity that does not match the NPZ and the pairs CSV exactly. This is the
    boundary between the frozen mesher and everything downstream.
    """
    report = read_json(report_path)
    if report.get("pass") is not True:
        raise PipelineError("MESH_QA_FAILED", "Step 05 report did not PASS.")
    with np.load(npz_path, allow_pickle=False) as data:
        arrays = {k: data[k].copy() for k in ("nodes", "triangles", "x_pairs", "y_pairs", "z_pairs")}
    nodes, triangles = arrays["nodes"], arrays["triangles"]
    if nodes.ndim != 2 or nodes.shape[1] != 3 or not len(nodes) or not np.isfinite(nodes).all():
        raise PipelineError("MESH_CONTRACT_INVALID", "Invalid coordinates.")
    if (triangles.ndim != 2 or triangles.shape[1] != 3 or not len(triangles)
            or triangles.dtype.kind not in "iu" or triangles.min() < 0
            or triangles.max() >= len(nodes)):
        raise PipelineError("MESH_CONTRACT_INVALID",
                            "Connectivity must be integer, zero based and in range.")
    if report["nodes"] != len(nodes) or report["triangles"] != len(triangles):
        raise PipelineError("MESH_REPORT_MISMATCH", "Counts differ from the Step 05 report.")
    L = finite(report["cell_size_mm"], "mesh report cell_size_mm", positive=True)
    if nodes.min() < -1e-8 or nodes.max() > L + 1e-8:
        raise PipelineError("MESH_CONTRACT_INVALID", "Invalid cell bounds.")
    points = nodes[triangles]
    areas = np.linalg.norm(np.cross(points[:, 1] - points[:, 0],
                                    points[:, 2] - points[:, 0]), axis=1) / 2
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
    with open(pair_csv, encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    actual = {(r["axis"].strip().upper(), int(r["low_node"]), int(r["high_node"]))
              for r in csv_rows}
    if actual != csv_expected or len(actual) != len(csv_rows):
        raise PipelineError("CSV_NPZ_MISMATCH",
                            "CSV uses one-based labels and must match the NPZ exactly.")
    for row in csv_rows:
        low, high = int(row["low_node"]) - 1, int(row["high_node"]) - 1
        vector = np.array([float(row[k]) for k in ("dx", "dy", "dz")])
        if not np.isfinite(vector).all() or np.linalg.norm(vector - (nodes[high] - nodes[low])) > 1e-8:
            raise PipelineError("CSV_NPZ_MISMATCH", "CSV displacement vector differs from mesh.")
    arrays.update({"report": report, "area_mm2": area, "L_mm": L})
    return arrays


def pbc_relations(x_pairs, y_pairs, rotations=True):
    """Lateral diagonal macro-strain PBC using one representative per class.

    Internal node indices are zero based; coefficients are signed integer cell
    jumps. Every dependent DOF appears only in its own equation and no eliminated
    DOF is ever reused as a representative.
    """
    graph = defaultdict(list)
    edges = []
    for axis, pairs in enumerate((x_pairs, y_pairs)):
        step = (1, 0) if axis == 0 else (0, 1)
        for low, high in pairs:
            low, high = int(low), int(high)
            if low == high:
                raise PipelineError("PBC_INVALID", "Pair references the same node.")
            edges.append((low, high, step))
            graph[low].append((high, step))
            graph[high].append((low, tuple(-n for n in step)))
    potentials, rows = {}, []
    components = 0
    for root in sorted(graph):
        if root in potentials:
            continue
        components += 1
        potentials[root] = (0, 0)
        queue = deque([root])
        members = []
        while queue:
            parent = queue.popleft()
            members.append(parent)
            for child, delta in sorted(graph[parent]):
                candidate = tuple(a + b for a, b in zip(potentials[parent], delta))
                if child in potentials:
                    if potentials[child] != candidate:
                        raise PipelineError("PBC_CYCLE_INCONSISTENT",
                                            "Periodic jumps do not close around a cycle.")
                else:
                    potentials[child] = candidate
                    queue.append(child)
        for node in sorted(members):
            if node != root:
                rows.append({"node": node, "root": root, "shift": list(potentials[node])})
    for low, high, delta in edges:
        if tuple(b - a for a, b in zip(potentials[low], potentials[high])) != delta:
            raise PipelineError("PBC_INVALID", "An original pair is not represented.")
    dependent = {row["node"] for row in rows}
    if dependent & {row["root"] for row in rows}:
        raise PipelineError("PBC_ELIMINATION_CONFLICT", "Dependent node reused as representative.")
    return {"mode": "lateral_xy_diagonal", "index_base": 0, "rotations": bool(rotations),
            "raw_pairs": len(edges), "boundary_nodes": len(graph), "classes": components,
            "independent_relations": len(rows), "removed_relations": len(edges) - len(rows),
            "equation_count": len(rows) * (6 if rotations else 3), "relations": rows}


def render_pbc_include(mapping, rp_x, rp_y):
    """Render the *Equation block for a PBC mapping."""
    node_ids = {r[k] + 1 for r in mapping["relations"] for k in ("node", "root")}
    if rp_x == rp_y or rp_x in node_ids or rp_y in node_ids:
        raise PipelineError("PBC_LABEL_COLLISION", "Macro control labels overlap shell nodes.")
    lines = ["** Lateral PBC. Flat-model global labels; include AFTER node definitions.",
             "** RP_X uses DOF 1 only; RP_Y uses DOF 2 only; do not constrain these free macro DOFs."]
    for row in mapping["relations"]:
        for dof in range(1, 7 if mapping["rotations"] else 4):
            terms = [(row["node"] + 1, dof, 1), (row["root"] + 1, dof, -1)]
            if dof in (1, 2) and row["shift"][dof - 1]:
                terms.append((rp_x if dof == 1 else rp_y, dof, -row["shift"][dof - 1]))
            lines.extend(["*Equation", str(len(terms)),
                          ", ".join(str(v) for term in terms for v in term)])
    return "\n".join(lines) + "\n"


def prepare_ingredients(npz, report, pairs, simulation, output):
    """Write the FE ingredients for one verified mesh into ``output``.

    Returns the facts the builder needs (labels, thickness, target displacement,
    counts). ``simulation`` is the parsed config/simulation.json.
    """
    mesh = load_bundle(npz, report, pairs)
    material, shell = simulation["material"], simulation["shell"]
    relative_density = shell["target_relative_density"]
    strain = simulation["loading"]["target_compression_strain"]
    if not -1 < material["poisson_ratio"] < 0.5:
        raise PipelineError("CONFIG_INVALID", "material.poisson_ratio must be in (-1, 0.5).")
    if not 0 < relative_density < 1:
        raise PipelineError("CONFIG_INVALID", "shell.target_relative_density must be in (0, 1).")
    if not 0 < strain < 1:
        raise PipelineError("CONFIG_INVALID",
                            "loading.target_compression_strain must be in (0, 1).")
    table = np.asarray(material["plastic_table"], dtype=float)
    if (table.ndim != 2 or table.shape[1] != 2 or not len(table) or not np.isfinite(table).all()
            or np.any(table[:, 0] <= 0) or table[0, 1] != 0
            or np.any(np.diff(table[:, 1]) <= 0)):
        raise PipelineError("CONFIG_INVALID",
                            "plastic_table needs positive true stress and increasing equivalent "
                            "plastic strain starting at zero.")
    L, area = mesh["L_mm"], mesh["area_mm2"]
    # Shell thickness source (validated in build.load_simulation):
    # "relative_density" keeps the historical t = rho* * L^3 / surface area,
    # "fixed" takes shell.thickness_mm as the physical shell thickness.
    thickness_mode = shell.get("thickness_mode", "relative_density")
    thickness = (float(shell["thickness_mm"]) if thickness_mode == "fixed"
                 else relative_density * L**3 / area)
    target_displacement = -strain * L
    mapping = pbc_relations(mesh["x_pairs"], mesh["y_pairs"],
                            simulation["pbc"]["include_rotational_dofs"])
    count = len(mesh["nodes"])
    labels = {"rp_x": count + 1, "rp_y": count + 2, "rp_bottom": count + 3, "rp_top": count + 4,
              "first_plate_node": count + 5,
              "first_plate_element": len(mesh["triangles"]) + 1}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lines = ["** Shell mesh only; not a complete Abaqus physical model.", "*Node"]
    lines.extend("%d, %.17g, %.17g, %.17g" % (i, *p) for i, p in enumerate(mesh["nodes"], 1))
    lines.append("*Element, type=%s, elset=SHELL_ALL" % shell["element_type"])
    lines.extend("%d, %d, %d, %d" % (i, *(p + 1)) for i, p in enumerate(mesh["triangles"], 1))
    atomic_text(output / "shell_mesh.inc", "\n".join(lines) + "\n")
    atomic_text(output / "lateral_pbc.inc",
                render_pbc_include(mapping, labels["rp_x"], labels["rp_y"]))
    write_json(output / "pbc_map.json", mapping)
    return {"case_id": mesh["report"].get("case_id"), "L_mm": L, "A0_mm2": L**2,
            "surface_area_mm2": area, "thickness_mm": thickness,
            "thickness_mode": thickness_mode,
            "target_displacement_mm": target_displacement, "labels": labels,
            "shell_nodes": count, "shell_elements": len(mesh["triangles"]),
            "equation_count": mapping["equation_count"]}


# ---------------------------------------------------------------------------
# Running the frozen vendor stages.
#
# The vendor code is executed, never edited, and always through the Pixi
# environment it was validated in ('geo' for the Python stages, 'cgal' for the
# compiled mesher). Stages 00-06 turn a case config into a shell mesh; the Abaqus
# mesh data check and the vendor validator 07 belong to the next stage and are
# driven by pipeline/abaqus.py.
# ---------------------------------------------------------------------------

_STAGES = ("00_check_python_environment.py", "01_build_periodic_topology.py",
           "02_extract_master_boundaries.py", "03_standardize_master_boundaries.py",
           "04_export_cgal_input.py", "05_validate_shell.py",
           "06_export_abaqus_meshcheck.py")
#: Stage 07 validates the Abaqus mesh data check logs; it runs in the next stage.
_VALIDATOR = "07_validate_abaqus_datacheck.py"


def pixi_argv(environment):
    """argv prefix that runs a command inside another Pixi environment."""
    executable = shutil.which("pixi.exe") or shutil.which("pixi")
    if not executable:
        raise PipelineError("PIXI_MISSING", "pixi is required; no system Python fallback.")
    return [executable, "run", "--locked", "--manifest-path", str(ROOT / "pixi.toml"),
            "--environment", environment, "--executable"]


def vendor_hashes():
    """Verify the frozen vendor tree against its own manifest."""
    expected = {}
    for line in (VENDOR / "MANIFEST_SHA256.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        name = name.strip()
        if file_hash(VENDOR / name) != digest:
            raise PipelineError("VENDOR_MODIFIED", "Frozen vendor differs from manifest: " + name)
        expected[name] = digest
    return expected


def find_cgal_executable(configured=None):
    """Locate the compiled CGAL mesher: config first, then the newest local build."""
    if configured:
        path = Path(configured)
        if not path.is_file():
            raise PipelineError("EXTERNAL_TOOL_MISSING",
                                "cgal.executable does not exist: " + str(path))
        return path
    candidates = sorted((ROOT / "work").glob("*/build/periodic_surface_mesher.exe"),
                        key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise PipelineError("EXTERNAL_TOOL_MISSING",
                            "No CGAL mesher found. Run 'pixi run build-cgal --out work/<attempt>' "
                            "and set cgal.executable in config/runtime.json.")
    return candidates[-1]


def run_command(argv, cwd, log, label, timeout_s=3600):
    """Run one vendor-stage command; a non-zero exit is fatal and prints the tail."""
    log("  " + label + " ...")
    completed = subprocess.run([str(part) for part in argv], cwd=str(cwd),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout_s)
    if completed.returncode:
        raise PipelineError("MESH_STAGE_FAILED",
                            label + " failed with return code %d:\n%s\n%s"
                            % (completed.returncode, (completed.stdout or "")[-2000:],
                               (completed.stderr or "")[-2000:]))
    return completed


def run_mesh(case_path, mesh_dir, log, cgal_executable=None, case_document=None):
    """Run the frozen mesh pipeline for one case into ``mesh_dir``/engine.

    Returns the mesh result: paths and SHA256 of the NPZ, the stage-05 report, the
    periodic pairs CSV and the mesh-check INP the Abaqus data check reads. Nothing
    is copied afterwards: the Abaqus stages run in the same case directory, so a
    case owns exactly one deck and there is no staging step.
    """
    case = load_case(case_path, document=case_document)
    case_id = safe_id(case["case_id"])
    expected = vendor_hashes()
    # Subprocess arguments must be absolute: the child runs with cwd=engine.
    mesh_dir = Path(mesh_dir).resolve()
    engine = mesh_dir / "engine"
    if engine.exists():
        raise PipelineError("OUTPUT_EXISTS",
                            "Mesh directory already exists; use --force or a new --work-root: "
                            + str(engine))
    engine.mkdir(parents=True)
    for name in _STAGES + (_VALIDATOR,):
        shutil.copy2(VENDOR / name, engine / name)
    shutil.copytree(VENDOR / "meshlib", engine / "meshlib",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (engine / "config").mkdir()
    write_json(engine / "config/case.json", vendor_case(case))
    case_dir = engine / "cases" / case_id
    for name in ("cgal_input", "cgal_output", "shell", "abaqus_meshcheck"):
        (case_dir / name).mkdir(parents=True)
    geo = pixi_argv("geo")
    for name in _STAGES[:5]:
        run_command(geo + ["python", "-B", str(engine / name)], engine, log, name)
    mesher = find_cgal_executable(cgal_executable)
    log("  CGAL mesher: " + str(mesher))
    run_command(pixi_argv("cgal") + [str(mesher),
                                     str(case_dir / "cgal_input/cgal_case.txt"),
                                     str(case_dir / "cgal_input/periodic3_master_features.txt"),
                                     str(case_dir / ("cgal_output/" + case_id + "_mesh"))],
                engine, log, mesher.name)
    for name in _STAGES[5:]:
        run_command(geo + ["python", "-B", str(engine / name)], engine, log, name)
    vendor_hashes()
    npz = case_dir / "shell" / (case_id + "_shell.npz")
    report = case_dir / "shell" / (case_id + "_shell_report.json")
    pairs = case_dir / "abaqus_meshcheck" / (case_id + "_periodic_pairs.csv")
    meshcheck_inp = case_dir / "abaqus_meshcheck" / (case_id + "_meshcheck.inp")
    missing = [str(path) for path in (npz, report, pairs, meshcheck_inp)
               if not path.is_file()]
    if missing:
        raise PipelineError("MESH_OUTPUT_MISSING",
                            "The frozen mesh stages did not produce: " + ", ".join(missing))
    result = {"case_id": case_id, "engine": str(engine), "case_dir": str(case_dir),
              "npz": str(npz), "report": str(report), "pairs_csv": str(pairs),
              "meshcheck_inp": str(meshcheck_inp),
              "meshcheck_dir": str(meshcheck_inp.parent),
              "meshcheck_job": case_id + "_meshcheck",
              "cgal_executable": str(mesher), "vendor": expected,
              "artifacts": {str(path.relative_to(engine)): file_hash(path)
                            for path in (npz, report, pairs, meshcheck_inp)}}
    write_json(mesh_dir / "mesh_result.json", dict(result, status="MESH_COMPLETED"))
    log("  mesh written: " + str(npz))
    return result


def validate_meshcheck(mesh_result, log):
    """Run vendor stage 07 over the Abaqus mesh data check logs (no Abaqus here)."""
    engine = Path(mesh_result["engine"])
    run_command(pixi_argv("geo") + ["python", "-B", str(engine / _VALIDATOR)], engine, log,
                _VALIDATOR)
    return read_json(Path(mesh_result["case_dir"]) / "abaqus_meshcheck" /
                     (mesh_result["case_id"] + "_meshcheck_datacheck_report.json"))
