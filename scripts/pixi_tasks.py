"""Pixi-only wrappers for existing functions; no Abaqus launcher or solver.

All paths supplied by users are resolved against the workspace root. Mesh tasks
always copy inputs into a new attempt. Frozen code is never imported in place.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "DiffuMeta_Automation_v0.1" / "DiffuMeta_Automation_v0.1"
VENDOR = CODE / "vendor" / "periodic_surface_mesher_v1.0"
# Validated baseline assertions, NOT a second dependency truth: pixi.toml +
# pixi.lock are the only dependency configuration. These pins re-check what is
# actually installed so a silently broken or partially upgraded Pixi env fails
# loudly instead of producing subtly different mesh results.
GEO = {"numpy": "2.2.6", "scipy": "1.15.3", "skimage": "0.25.2", "sympy": "1.14.0"}
# Same rule for the CGAL build/runtime packages below.
CGAL = {"cgal-cpp": "6.0.1", "cmake": "4.4.3", "ninja": "1.13.2",
        "eigen": "5.0.1", "libboost": "1.88.0", "libboost-devel": "1.88.0",
        "libboost-headers": "1.88.0", "gmp": "6.3.0", "mpfr": "4.2.2"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    # Never replace a previous stage's evidence, including a failed attempt.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def resolve(path):
    p = Path(path)
    return (p if p.is_absolute() else ROOT / p).resolve()


def require_role(role):
    prefix = os.environ.get("CONDA_PREFIX")  # Pixi's package-prefix variable, not conda.exe.
    if os.environ.get("PIXI_ENVIRONMENT_NAME") != role or not prefix:
        raise RuntimeError("Use the matching 'pixi run <task>' environment: " + role)
    if Path(prefix).resolve() != Path(sys.prefix).resolve():
        raise RuntimeError("Pixi prefix and running Python disagree")


def vendor_hashes():
    expected = {}
    for line in (VENDOR / "MANIFEST_SHA256.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        if sha(VENDOR / name.strip()) != digest:
            raise RuntimeError("Frozen vendor differs from manifest: " + name)
        expected[name.strip()] = digest
    return expected


def new_attempt(path):
    out = resolve(path)
    # Direct children only: never create a subdirectory inside historical work.
    if out.parent not in {(ROOT / "work").resolve(), (CODE / "work").resolve()}:
        raise ValueError("--out must be a NEW direct child of workspace work/ or code work/")
    out.parent.mkdir(exist_ok=True)
    out.mkdir(exist_ok=False)
    return out


def run_logged(argv, cwd, out, label, env=None):
    write_json(out / (label + ".command.json"), {"argv": argv, "cwd": str(cwd)})
    with (out / (label + ".log")).open("xb") as stream:
        result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    write_json(out / (label + ".result.json"), {"returncode": result.returncode})
    if result.returncode:
        raise RuntimeError(f"{label} failed ({result.returncode}); see {out / (label + '.log')}")


def toolchain():
    """Discover installed VS, activate ONLY a child process, never install it."""
    finder = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if not finder.is_file():
        return {"status": "PARTIAL", "missing": ["vswhere / Visual Studio Build Tools"]}, None
    found = subprocess.run([str(finder), "-latest", "-products", "*", "-requires",
                            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                           capture_output=True, text=True, check=True).stdout.strip()
    devcmd = Path(found) / "Common7/Tools/VsDevCmd.bat"
    if not found or not devcmd.is_file():
        return {"status": "PARTIAL", "missing": ["VS C++ x64 toolchain"]}, None
    # The only shell input is the discovered installation path, not task arguments.
    if any(c in str(devcmd) for c in '\r\n"%&|<>^'):
        raise RuntimeError("Unsupported characters in Visual Studio installation path")
    base = os.environ.copy()
    base["VSCMD_SKIP_SENDTELEMETRY"] = "1"
    base["PIXI_VSDEVCMD"] = str(devcmd)
    # A fixed batch wrapper owns cmd quoting; subprocess always receives argv.
    comspec = os.environ.get("COMSPEC", "C:/Windows/System32/cmd.exe")
    result = subprocess.run([comspec, "/d", "/c", str(Path(__file__).with_name("vs_environment.cmd"))],
                            env=base, capture_output=True, text=True, errors="replace")
    if result.returncode:
        return {"status": "PARTIAL", "missing": ["VS developer environment"],
                "detail": result.stderr.strip()}, None
    child = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line and not line.startswith("="))
    # Keep Pixi CMake, Ninja and library DLLs first, after VS contributes INCLUDE/LIB.
    path_key = next((key for key in child if key.upper() == "PATH"), "PATH")
    child[path_key] = str(Path(sys.prefix) / "Library/bin") + os.pathsep + child.get(path_key, "")
    cl = shutil.which("cl.exe", path=child[path_key])
    sdk = child.get("WindowsSdkDir", "")
    version = child.get("WindowsSDKVersion", "").rstrip("\\/")
    sdk_header = Path(sdk) / "Include" / version / "um/Windows.h"
    missing = ([] if cl else ["cl.exe"]) + ([] if sdk and sdk_header.is_file() else ["Windows SDK headers"])
    info = {"status": "PARTIAL" if missing else "PASS", "missing": missing,
            "cl": cl, "vc_tools_version": child.get("VCToolsVersion", "UNKNOWN"),
            "windows_sdk_version": version or "UNKNOWN", "vs_devcmd": str(devcmd)}
    return info, child


def check(role):
    require_role(role)
    vendor_hashes()
    info = {"role": role, "python": platform.python_version(), "executable": sys.executable,
            "status": "PASS", "scope": "environment only; no mesh regression or Abaqus validation"}
    if role in ("default", "geo"):
        expected = GEO if role == "geo" else {"numpy": "2.2.6"}
        info["packages"] = {name: importlib.import_module(name).__version__ for name in expected}
        if info["packages"] != expected:
            raise RuntimeError("Scientific package versions differ from pinned environment")
        if role == "geo" and platform.python_version() != "3.10.21":
            raise RuntimeError("geo Python differs from validated reference")
        if role == "default" and sys.version_info[:2] != (3, 11):
            raise RuntimeError("default requires Python 3.11")
        with sqlite3.connect(":memory:") as db:
            info["sqlite"] = db.execute("select sqlite_version()").fetchone()[0]
    else:
        records = [json.loads(p.read_text(encoding="utf-8")) for p in (Path(sys.prefix) / "conda-meta").glob("*.json")]
        info["packages"] = {d["name"]: d["version"] for d in records if d["name"] in CGAL}
        if info["packages"] != CGAL:
            raise RuntimeError("CGAL package versions differ from pinned environment")
        for executable in ("cmake", "ninja"):
            path = shutil.which(executable)
            if not path or not Path(path).resolve().is_relative_to(Path(sys.prefix).resolve()):
                raise RuntimeError("Tool did not resolve inside Pixi: " + executable)
            info[executable] = subprocess.run([path, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
        dll_dir = Path(sys.prefix) / "Library/bin"
        with os.add_dll_directory(str(dll_dir)):
            info["loaded_dlls"] = []
            for name in ("gmp", "mpfr"):
                dlls = list(dll_dir.glob("*" + name + "*.dll"))
                if not dlls:
                    raise RuntimeError("Missing DLL: " + name)
                for dll in dlls:
                    ctypes.WinDLL(str(dll))
                    info["loaded_dlls"].append(dll.name)
        info["external_toolchain"], _ = toolchain()
        info["status"] = info["external_toolchain"]["status"]
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0 if info["status"] == "PASS" else 2


def mesh(args):
    require_role("geo")
    expected = vendor_hashes()
    stage_files = sorted(VENDOR.glob("[0-9][0-9]_*.py"))
    source = None
    if args.stage in ("post", "check"):
        if not args.from_attempt:
            raise ValueError("This stage requires --from-attempt with existing input artifacts")
        source = resolve(args.from_attempt) / "engine"
        if not source.is_dir():
            raise ValueError("Source attempt must contain engine/")
    case_path = source / "config/case.json" if source else resolve(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8-sig"))
    sys.path.insert(0, str(CODE))
    from pipeline.common import safe_id
    case_id = safe_id(case["case_id"])
    # Source must contain unchanged Python algorithms, never arbitrary supplied code.
    names = [p.name for p in stage_files] + [str(p.relative_to(VENDOR)).replace("\\", "/") for p in (VENDOR / "meshlib").glob("*.py")]
    if source:
        for name in names:
            if sha(source / name) != sha(VENDOR / name):
                raise ValueError("Source engine algorithm mismatch: " + name)
        target_dir = source / "cases" / case_id
        if args.stage == "post":
            if not (target_dir / "cgal_output" / (case_id + "_mesh_canonical_triangles.csv")).is_file():
                raise ValueError("Missing CGAL canonical CSV; no CGAL run is performed by mesh-post")
            if any((target_dir / "shell").glob("*")) or any((target_dir / "abaqus_meshcheck").glob("*")):
                raise ValueError("Postprocess outputs already exist; select a pre-postprocess input attempt")
        else:
            logs = target_dir / "abaqus_meshcheck"
            if not all((logs / (case_id + "_meshcheck" + suffix)).is_file() for suffix in (".dat", ".msg")):
                raise ValueError("mesh-check needs existing .dat/.msg; it never submits Abaqus")
            if (logs / (case_id + "_meshcheck_datacheck_report.json")).exists():
                raise ValueError("Step07 report already exists; do not overwrite historical evidence")
    out = new_attempt(args.out)
    engine = out / "engine"
    if source:
        shutil.copytree(source, engine, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        engine.mkdir()
        for p in stage_files:
            shutil.copy2(p, engine / p.name)
        shutil.copytree(VENDOR / "meshlib", engine / "meshlib", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (engine / "config").mkdir()
        write_json(engine / "config/case.json", case)
    write_json(out / "inputs.json", {"case_sha256": sha(case_path), "vendor": expected,
               "pixi_lock_sha256": sha(ROOT / "pixi.lock"), "python": sys.executable,
               "source_engine": str(source) if source else None,
               "input_files": {str(p.relative_to(source)): sha(p) for p in source.rglob("*") if p.is_file()} if source else {}})
    indexes = {"env": [0], "pre": [0, 1, 2, 3, 4], "post": [5, 6], "check": [7]}[args.stage]
    for index in indexes:
        script = next(p for p in stage_files if p.name.startswith(f"{index:02d}_"))
        run_logged([sys.executable, "-B", str(engine / script.name)], engine, out, script.stem)
    vendor_hashes()
    write_json(out / "stage_result.json", {"status": "COMMANDS_COMPLETED", "stage": args.stage,
               "dataset_eligible": False, "note": "Inspect stage reports; not a new validated baseline or solver acceptance"})
    print(out)
    return 0


def build(args):
    require_role("cgal")
    vendor_hashes()
    info, child = toolchain()
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if info["status"] != "PASS":
        return 2
    if args.check_only:
        return 0
    if not args.out:
        raise ValueError("Actual compilation requires a NEW --out work/<attempt>")
    out = new_attempt(args.out)
    write_json(out / "inputs.json", {"toolchain": info, "pixi_lock_sha256": sha(ROOT / "pixi.lock"),
               "source": {p.name: sha(p) for p in (VENDOR / "cgal_mesher").iterdir() if p.is_file()}})
    cmake = str(Path(sys.prefix) / "Library/bin/cmake.exe")
    run_logged([cmake, "-S", str(VENDOR / "cgal_mesher"), "-B", str(out / "build"),
                "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(Path(sys.prefix) / "Library")], ROOT, out, "configure", child)
    run_logged([cmake, "--build", str(out / "build")], ROOT, out, "build", child)
    exe = out / "build/periodic_surface_mesher.exe"
    write_json(out / "build_result.json", {"status": "BUILT_NOT_MESH_VALIDATED", "executable": str(exe), "sha256": sha(exe)})
    vendor_hashes()
    return 0


def tests():
    require_role("default")
    # Existing suite creates TemporaryDirectory/SQLite. Keep these project-local.
    parent = ROOT / "work"
    parent.mkdir(exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix="pixi_tests_", dir=parent))
    child = os.environ.copy()
    child.update(TEMP=str(attempt), TMP=str(attempt), PYTHONDONTWRITEBYTECODE="1")
    run_logged([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"], CODE, attempt, "unittest", child)
    # Pixi migration boundary tests (old-schema rejection, lock/artifact binding,
    # attempt protection) must run with the standard entry, not stay orphaned.
    run_logged([sys.executable, "-B", str(Path(__file__).with_name("test_pixi_tasks.py"))], ROOT, attempt, "pixi_boundary_tests", child)
    print((attempt / "unittest.log").read_text(encoding="utf-8", errors="replace"))
    print((attempt / "pixi_boundary_tests.log").read_text(encoding="utf-8", errors="replace"))
    print("Test evidence:", attempt)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.add_argument("role", choices=("default", "geo", "cgal"))
    sub.add_parser("test")
    p = sub.add_parser("mesh", description="Existing frozen stages in a NEW copied attempt; paths are workspace-relative")
    p.add_argument("stage", choices=("env", "pre", "post", "check"))
    p.add_argument("--out", required=True)
    p.add_argument("--case", default=str(CODE / "config/cases/fig1.json"))
    p.add_argument("--from-attempt")
    p = sub.add_parser("build-cgal")
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--out")
    args = parser.parse_args()
    if args.command == "check":
        return check(args.role)
    if args.command == "mesh":
        return mesh(args)
    if args.command == "build-cgal":
        return build(args)
    return tests()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
