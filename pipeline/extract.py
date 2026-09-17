"""Result extraction: solve ODB -> history.csv, stress_strain.csv, summary.json.

The ODB is read by ``abaqus python abaqus_worker/export_history.py`` (the Pixi
environment never imports odbAccess). This module decides what the raw history
means and writes the solver-agnostic result files, so a Standard run and an
Explicit run of the same case produce the same three files.

Sign convention (matches the earlier Fig.1 paper-reproduction script):
compression strain > 0 and compression stress > 0, i.e. ``strain = -U3/H0`` and
``stress = -RF3/A0`` with H0 the unit cell size and A0 its square cross-section.
Nothing here decides whether a result is scientifically valid: it only reports the
curve, the energy ratios and the missing variables.
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import numpy as np

from .abaqus import abaqus_env, load_runtime, resolve_launcher
from .common import PipelineError, file_hash, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "abaqus_worker" / "export_history.py"
#: History variables exported when present in the ODB (no fabrication, no rename).
ENERGY_VARIABLES = ("ALLIE", "ALLKE", "ALLAE", "ALLPD", "ALLWK", "ETOTAL", "ALLVD")
NODE_VARIABLES = ("U3", "RF3")


def _solve_report(deck_dir):
    report = read_json(Path(deck_dir) / "solve_report.json")
    if report.get("status") not in ("SOLVE_COMPLETED", "SOLVE_COMPLETED_WITH_WARNINGS"):
        raise PipelineError("EXTRACT_INVALID_SOURCE",
                            "Solve status is " + repr(report.get("status"))
                            + "; extraction needs a completed solve.")
    odb = (report.get("abaqus_output") or {}).get("odb") or {}
    odb_path = Path(deck_dir) / odb.get("path", "")
    if not odb_path.is_file():
        raise PipelineError("EXTRACT_ODB_MISSING", "ODB not found: " + str(odb_path))
    return report, odb_path


def export_raw(odb_path, raw_path, *, step, node_labels, node_variables, energy_variables,
               runtime_path=None, abaqus_command=None, timeout_s=3600):
    """Run the Abaqus Python worker and return the raw history document."""
    runtime = load_runtime(runtime_path)
    launcher = resolve_launcher(runtime, abaqus_command)
    argv = [launcher["path"], "python", str(WORKER), "--odb", str(odb_path),
            "--out", str(raw_path), "--step", step,
            "--node-variables", ",".join(node_variables),
            "--energy", ",".join(energy_variables)]
    for name, label in sorted(node_labels.items()):
        argv.extend(["--node", name + "=" + str(label)])
    completed = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout_s,
                               env=abaqus_env())
    if completed.returncode:
        raise PipelineError("EXTRACT_FAILED",
                            "ODB export failed (return code %d):\n%s\n%s"
                            % (completed.returncode, (completed.stdout or "")[-2000:],
                               (completed.stderr or "")[-2000:]))
    return read_json(raw_path)


def _align(series, axis):
    """Put a series on the reference time axis; interpolate only when needed."""
    times = np.asarray([point[0] for point in series], dtype=float)
    values = np.asarray([point[1] for point in series], dtype=float)
    if len(times) == len(axis) and np.allclose(times, axis, rtol=0.0, atol=1e-12):
        return values, False
    return np.interp(axis, times, values), True


def build_results(raw, *, case_id, solver, height_mm, area_mm2, target_strain,
                  wall_time_s=None, mass_scaling=None):
    """Turn raw ODB history into the contents of the three result files."""
    series = (raw["nodes"].get("RP_TOP") or {}).get("series") or {}
    if "U3" not in series:
        raise PipelineError("EXTRACT_INCOMPLETE",
                            "The ODB has no RP_TOP U3 history, so no stress-strain curve can be "
                            "built. Missing: " + repr(raw.get("missing")))
    if "RF3" not in series:
        raise PipelineError("EXTRACT_INCOMPLETE", "The ODB has no RP_TOP RF3 history.")
    axis = np.asarray([point[0] for point in series["U3"]], dtype=float)
    displacement = np.asarray([point[1] for point in series["U3"]], dtype=float)
    columns = {"time_s": axis, "U3_mm": displacement}
    interpolated = False
    reaction, flag = _align(series["RF3"], axis)
    columns["RF3_N"] = reaction
    interpolated = interpolated or flag
    for variable in ENERGY_VARIABLES:
        if variable in raw["energy"]:
            columns[variable], flag = _align(raw["energy"][variable], axis)
            interpolated = interpolated or flag
    strain = -displacement / height_mm
    stress = -np.asarray(columns["RF3_N"], dtype=float) / area_mm2
    ke_ie = None
    if "ALLIE" in columns and "ALLKE" in columns:
        # Diagnostics only: a high ratio is reported, never repaired automatically.
        energy = np.asarray(columns["ALLIE"], dtype=float)
        active = energy > 0
        if active.any():
            ratio = np.asarray(columns["ALLKE"], dtype=float) / energy
            ke_ie = float(np.max(ratio[active]))
    summary = {
        "case_id": case_id, "solver": solver, "success": True,
        "sign_convention": "compression positive: strain = -U3/H0, stress = -RF3/A0",
        "height_mm": height_mm, "reference_area_mm2": area_mm2,
        "target_compression_strain": target_strain,
        "final_strain": float(strain[-1]), "final_stress_MPa": float(stress[-1]),
        "max_stress_MPa": float(np.max(stress)), "points": int(len(strain)),
        "wall_time_s": wall_time_s, "mass_scaling": mass_scaling,
        "max_ke_ie_ratio": ke_ie,
        "energy_variables": [name for name in ENERGY_VARIABLES if name in columns],
        "energy_interpolated": bool(interpolated),
        "missing": raw.get("missing", {}),
        "note": "Curve and energy diagnostics only. No contact/PBC/material-domain QA and no "
                "quasi-static acceptance: a high KE/IE ratio is reported, never repaired.",
    }
    return columns, strain, stress, summary


def _number(value):
    """Deterministic CSV number text (no negative zero)."""
    return "%.10e" % (value if value != 0 else 0.0)


def write_results(results_dir, columns, strain, stress, summary):
    """Write history.csv, stress_strain.csv and summary.json into ``results_dir``."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    names = [name for name in columns if name != "time_s"]
    series = {name: np.asarray(columns[name], dtype=float) for name in names}
    with (results_dir / "history.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["time_s"] + names)
        for index in range(len(columns["time_s"])):
            writer.writerow([_number(columns["time_s"][index])]
                            + [_number(series[name][index]) for name in names])
    with (results_dir / "stress_strain.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["engineering_strain", "engineering_stress_MPa"])
        for strain_value, stress_value in zip(strain, stress):
            writer.writerow([_number(strain_value), _number(stress_value)])
    write_json(results_dir / "summary.json", summary)
    return {"history_csv": file_hash(results_dir / "history.csv"),
            "stress_strain_csv": file_hash(results_dir / "stress_strain.csv"),
            "summary": summary}


def extract(deck_dir, results_dir, *, case_id=None, step="Compression", runtime_path=None,
            abaqus_command=None, timeout_s=3600, log=print, odb_path=None):
    """Extract one solved case: ODB -> results dir (history/stress-strain/summary).

    ``odb_path`` is a debugging override: read that ODB instead of the one named by
    solve_report.json (used to re-extract an older, already validated ODB). The
    deck's build_report.json is still required, because the node labels, H0 and the
    reference area come from the model that was actually built.
    """
    deck_dir = Path(deck_dir)
    if odb_path:
        odb_path = Path(odb_path)
        if not odb_path.is_file():
            raise PipelineError("EXTRACT_ODB_MISSING", "ODB not found: " + str(odb_path))
        solve_report = {}
    else:
        solve_report, odb_path = _solve_report(deck_dir)
    build_report = read_json(deck_dir / "build_report.json")
    model = build_report["model"]
    case_id = case_id or build_report.get("case_id")
    labels = dict(model["labels"])
    node_labels = {"RP_TOP": labels["rp_top"], "RP_X_CTRL": labels["rp_x"],
                   "RP_Y_CTRL": labels["rp_y"]}
    raw_path = Path(results_dir) / "raw_history.json"
    # The Abaqus Python worker writes raw_history.json with a plain open(), so the
    # results directory has to exist before it runs. Re-running extraction inside
    # the same case directory overwrites this intermediate file on purpose.
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    log("  reading ODB with abaqus python ...")
    raw = export_raw(odb_path, raw_path, step=step, node_labels=node_labels,
                     node_variables=NODE_VARIABLES, energy_variables=ENERGY_VARIABLES,
                     runtime_path=runtime_path, abaqus_command=abaqus_command,
                     timeout_s=timeout_s)
    simulation = build_report["simulation"]
    solver = simulation["solver"]["type"]
    columns, strain, stress, summary = build_results(
        raw, case_id=case_id, solver=solver, height_mm=model["height_mm"],
        area_mm2=model["reference_area_mm2"],
        target_strain=simulation["loading"]["target_compression_strain"],
        wall_time_s=solve_report.get("wall_time_s"),
        mass_scaling=(simulation["solver"][solver].get("mass_scaling")
                      if solver == "explicit_dynamic" else None))
    written = write_results(results_dir, columns, strain, stress, summary)
    log("  results written to " + str(results_dir))
    return dict(summary, results=written, odb=str(odb_path), raw_history=str(raw_path))
