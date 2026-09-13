"""Prepare isolated v1.0 workspaces. This module never edits the frozen vendor tree."""
from __future__ import annotations

from pathlib import Path
import math
import shutil

from .common import PipelineError, atomic_json, read_json, safe_id, tree_hash, digest, reserve_directory


STAGES = [
    ("PREFLIGHT", "Check environment, versions, disk and configuration"),
    ("MESH", "Run frozen 00-04, CGAL, 05-06 in an isolated directory"),
    ("MESH_DATACHECK", "Abaqus mesh datacheck + frozen 07 + outer evidence check"),
    ("BUILD", "Validated mesh -> complete physical INP and model manifest"),
    ("PHYSICAL_DATACHECK", "Fresh physical datacheck + contact initialization QA"),
    ("SOLVE", "Dynamic implicit solve with resource limits and watchdog"),
    ("EXTRACT", "Abaqus Python -> raw histories, fields and diagnostics"),
    ("QA", "Coverage, energies, PBC, contact, mesh and material validity"),
    ("PUBLISH", "Atomic result acceptance and idempotent dataset export"),
]


def prepare(vendor, case_path, environment_path, output):
    vendor = Path(vendor).resolve()
    case = read_json(case_path)
    env = read_json(environment_path)
    case_id = safe_id(case["case_id"])
    if case.get("iso_level", 0.0) != 0.0:
        raise PipelineError("CONFIG_UNSUPPORTED", "Frozen v1.0 requires iso_level=0.")
    if not math.isfinite(float(case["cell_size_mm"])) or not 0 < float(case["cell_size_mm"]):
        raise PipelineError("CONFIG_INVALID", "Cell size must be positive.")
    source_hash = tree_hash(vendor)
    folder = reserve_directory(output).resolve()
    engine = folder / "engine"
    engine.mkdir()
    for source in sorted(vendor.glob("[0-9][0-9]_*.py")):
        shutil.copy2(source, engine / source.name)
    shutil.copytree(vendor / "meshlib", engine / "meshlib",
                    ignore=shutil.ignore_patterns("__pycache__"))
    # The only replaced configuration is in this private copy.
    atomic_json(engine / "config" / "case.json", case)
    case_dir = engine / "cases" / case_id
    for name in ["cgal_input", "cgal_output", "shell", "abaqus_meshcheck"]:
        (case_dir / name).mkdir(parents=True)
    commands = []

    def add(stage, argv, cwd, gate):
        commands.append({"stage": stage, "argv": argv, "cwd": str(cwd), "gate": gate})

    for name in ["00_check_python_environment.py", "01_build_periodic_topology.py",
                 "02_extract_master_boundaries.py", "03_standardize_master_boundaries.py",
                 "04_export_cgal_input.py"]:
        add(name[:2], [env["geo_python"], str(engine / name)], engine,
            "exit=0 AND expected fresh output/report; environment 00 has no mesh report")
    add("CGAL", [env["cgal_exe"], str(case_dir / "cgal_input/cgal_case.txt"),
                 str(case_dir / "cgal_input/periodic3_master_features.txt"),
                 str(case_dir / ("cgal_output/" + case_id + "_mesh"))], engine,
        "exit=0 AND canonical CSV fresh/nonempty AND clipping=0")
    for name in ["05_validate_shell.py", "06_export_abaqus_meshcheck.py"]:
        add(name[:2], [env["geo_python"], str(engine / name)], engine, "exit=0 AND report.pass=true")
    job = case_id + "_meshcheck"
    add("MESH_DATACHECK", [env["abaqus_launcher"], "job=" + job,
        "input=" + job + ".inp", "datacheck", "interactive"], case_dir / "abaqus_meshcheck",
        "completed process AND matching job completion AND fresh nonempty dat/msg AND no fatal diagnostic")
    add("07", [env["geo_python"], str(engine / "07_validate_abaqus_datacheck.py")], engine,
        "exit=0 AND report.pass=true; this alone is insufficient to prove job completion")
    geometry_case = {k: v for k, v in case.items() if k not in {"case_id", "description", "abaqus"}}
    manifest = {
        "schema_version": 1, "status": "PREPARED_ONLY", "case_id": case_id,
        "mesh_request_key": digest({"geometry": geometry_case, "vendor": source_hash,
                                    "environment": env.get("mesher_environment_id", "UNVERIFIED")}),
        "vendor_sha256": source_hash, "engine": str(engine), "case_dir": str(case_dir),
        "commands": commands, "environment": env,
        "execution_note": "Commands are a plan; no CGAL/Abaqus process has been launched. Windows .bat/.cmd launchers need the documented launcher adapter.",
        "dataset_eligible": False,
    }
    if tree_hash(vendor) != source_hash:
        raise PipelineError("SOURCE_CHANGED", "Vendor source changed during preparation.")
    atomic_json(folder / "mesh_plan.json", manifest)
    return manifest
