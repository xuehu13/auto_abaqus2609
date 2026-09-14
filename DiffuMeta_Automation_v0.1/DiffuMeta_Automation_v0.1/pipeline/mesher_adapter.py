"""Prepare isolated v1.0 workspaces. This module never edits the frozen vendor tree."""
from __future__ import annotations

from pathlib import Path
import math
import shutil

from .common import PipelineError, atomic_json, read_json, safe_id, tree_hash, digest, reserve_directory, file_hash

WORKSPACE = Path(__file__).resolve().parents[3]


def external_environment(path):
    env = read_json(path)
    allowed = {"schema_version", "abaqus_launcher", "abaqus_release_required"}
    if env.get("schema_version") != 2 or set(env) != allowed:
        raise PipelineError("ENVIRONMENT_SCHEMA", "Use schema 2 with only schema_version, abaqus_launcher and abaqus_release_required.")
    launcher = env["abaqus_launcher"]
    if launcher is not None and (not isinstance(launcher, str) or not Path(launcher).is_absolute()
                                 or not Path(launcher).is_file()):
        raise PipelineError("EXTERNAL_TOOL_MISSING", "abaqus_launcher must be null or an existing absolute file path.")
    if not isinstance(env["abaqus_release_required"], str) or not env["abaqus_release_required"]:
        raise PipelineError("ENVIRONMENT_SCHEMA", "abaqus_release_required must be a nonempty string.")
    return env


def pixi_prefix(environment):
    executable = shutil.which("pixi.exe")
    if not executable:
        raise PipelineError("PIXI_MISSING", "pixi.exe is required; no system Python fallback.")
    return [executable, "run", "--locked", "--manifest-path", str(WORKSPACE / "pixi.toml"),
            "--environment", environment, "--executable"]


def cgal_artifact(build_directory):
    if build_directory is None:
        return None
    directory = Path(build_directory).resolve()
    result = read_json(directory / "build_result.json")
    # Derive the current artifact location, so a relocated workspace still works.
    exe = directory / "build" / "periodic_surface_mesher.exe"
    inputs = read_json(directory / "inputs.json")
    if (result.get("status") != "BUILT_NOT_MESH_VALIDATED" or not exe.is_file()
            or file_hash(exe) != result.get("sha256")
            or inputs.get("pixi_lock_sha256") != file_hash(WORKSPACE / "pixi.lock")):
        raise PipelineError("CGAL_BUILD_MISMATCH", "CGAL artifact/hash/lock mismatch; use a build from the current Pixi lock.")
    return {"executable": str(exe), "sha256": result["sha256"], "build_directory": str(directory)}


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


def prepare(vendor, case_path, environment_path, output, cgal_build=None):
    vendor = Path(vendor).resolve()
    case = read_json(case_path)
    env = external_environment(environment_path)
    geo = pixi_prefix("geo") + ["python", "-B"]
    cgal = cgal_artifact(cgal_build)
    lock_sha256 = file_hash(WORKSPACE / "pixi.lock")
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
        add(name[:2], geo + [str(engine / name)], engine,
            "exit=0 AND expected fresh output/report; environment 00 has no mesh report")
    add("CGAL", (pixi_prefix("cgal") + [cgal["executable"], str(case_dir / "cgal_input/cgal_case.txt"),
                 str(case_dir / "cgal_input/periodic3_master_features.txt"),
                 str(case_dir / ("cgal_output/" + case_id + "_mesh"))]) if cgal else None, engine,
        "exit=0 AND canonical CSV fresh/nonempty AND clipping=0")
    for name in ["05_validate_shell.py", "06_export_abaqus_meshcheck.py"]:
        add(name[:2], geo + [str(engine / name)], engine, "exit=0 AND report.pass=true")
    job = case_id + "_meshcheck"
    add("MESH_DATACHECK", [env["abaqus_launcher"], "job=" + job,
        "input=" + job + ".inp", "datacheck", "interactive"] if env["abaqus_launcher"] else None, case_dir / "abaqus_meshcheck",
        "completed process AND matching job completion AND fresh nonempty dat/msg AND no fatal diagnostic")
    add("07", geo + [str(engine / "07_validate_abaqus_datacheck.py")], engine,
        "exit=0 AND report.pass=true; this alone is insufficient to prove job completion")
    geometry_case = {k: v for k, v in case.items() if k not in {"case_id", "description", "abaqus"}}
    manifest = {
        "schema_version": 2, "status": "PREPARED_ONLY", "case_id": case_id,
        "mesh_request_key": digest({"geometry": geometry_case, "vendor": source_hash,
                                    "pixi_lock_sha256": lock_sha256,
                                    "cgal_sha256": cgal["sha256"] if cgal else "UNBUILT"}),
        "vendor_sha256": source_hash, "engine": str(engine), "case_dir": str(case_dir),
        "commands": commands, "environment": env,
        "runtime": {"manager": "pixi", "lock_sha256": lock_sha256, "cgal_build": cgal},
        "unconfigured_stages": [c["stage"] for c in commands if c["argv"] is None],
        "execution_note": "Preparation only, not an executor. Null argv means missing external configuration or build artifact; do not execute it. Pixi argv lists use shell=False. Abaqus is an EXTERNAL runtime; its batch launcher must not inherit Pixi Python/DLL activation.",
        "dataset_eligible": False,
    }
    if tree_hash(vendor) != source_hash:
        raise PipelineError("SOURCE_CHANGED", "Vendor source changed during preparation.")
    atomic_json(folder / "mesh_plan.json", manifest)
    return manifest
