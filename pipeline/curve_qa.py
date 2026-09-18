"""Checks aligned raw histories. Outputs are NOT complete FE acceptance decisions."""
import csv
from pathlib import Path

import numpy as np

from .common import PipelineError, finite, read_json, require_keys, write_json

#: Thresholds the curve check needs. Values are visible draft engineering choices,
#: never admission criteria for a production dataset. ``strain_targets`` are the
#: target strain samples (RB-011): a scientific variable in the policy, not a
#: hardcoded paper constant.
_POLICY_KEYS = ("ke_ie_limit", "ae_ie_limit", "energy_floor_Nmm", "startup_ke_max_Nmm",
                "target_strain_tolerance", "strain_monotonic_tolerance",
                "stress_sign_tolerance_MPa", "duplicate_stress_tolerance_MPa",
                "strain_targets")
_POLICY_OPTIONAL = ("schema_version", "policy_id", "calibrated_for_production", "note")


def _strain_targets(value, path):
    """Validate the configured target strain samples (finite, >= 2, increasing)."""
    if not isinstance(value, list) or len(value) < 2:
        raise PipelineError("CONFIG_INVALID",
                            "QA policy strain_targets (" + str(path)
                            + ") must be a list of at least 2 numbers.")
    targets = []
    for index, entry in enumerate(value):
        finite(entry, "strain_targets[%d] (%s)" % (index, path), minimum=0.0)
        targets.append(float(entry))
    if any(later <= earlier for earlier, later in zip(targets, targets[1:])):
        raise PipelineError("CONFIG_INVALID",
                            "QA policy strain_targets (" + str(path)
                            + ") must be strictly increasing.")
    return targets


def validate_policy(policy, path="<policy>"):
    """Every threshold must be a finite number; a NaN would silently disable a gate."""
    policy = require_keys(policy, path, _POLICY_KEYS, _POLICY_OPTIONAL, "QA policy")
    for key in _POLICY_KEYS:
        if key != "strain_targets":
            finite(policy[key], key + " (" + str(path) + ")", minimum=0.0)
    policy["strain_targets"] = _strain_targets(policy["strain_targets"], path)
    return policy


def load_policy(path):
    path = Path(path)
    if not path.is_file():
        raise PipelineError("CONFIG_INVALID", "QA policy file not found: " + str(path))
    return validate_policy(read_json(path), str(path))


def assess(columns, height_mm, area_mm2, compression_reaction_sign, policy):
    # Policy is validated before any comparison: a NaN threshold would make every
    # comparison False and silently disable the gate, and an unknown key means the
    # policy the operator wrote is not the policy being applied.
    validate_policy(policy)
    targets = policy["strain_targets"]
    failures = []
    required = ("time_s", "u3_mm", "rf3_N", "ALLKE", "ALLIE", "ALLAE")
    if any(k not in columns for k in required):
        return {"status": "CURVE_QA_FAILED", "failures": ["HISTORY_MISSING"], "dataset_eligible": False}
    data = {k: np.asarray(columns[k], dtype=float) for k in required}
    if (len({a.shape for a in data.values()}) != 1 or data["time_s"].ndim != 1
            or len(data["time_s"]) < 2 or not all(np.isfinite(v).all() for v in data.values())):
        return {"status": "CURVE_QA_FAILED", "failures": ["HISTORY_INVALID"], "dataset_eligible": False}
    if (not np.isfinite([height_mm, area_mm2]).all() or min(height_mm, area_mm2) <= 0
            or compression_reaction_sign not in (-1, 1)):
        raise ValueError("Invalid normalization or reaction sign.")
    time = data["time_s"]
    strain = -data["u3_mm"] / height_mm
    # Keep the chosen convention; abs(RF3) would hide sign errors.
    stress = compression_reaction_sign * data["rf3_N"] / area_mm2
    if np.any(np.diff(time) <= 0):
        failures.append("TIME_NOT_STRICTLY_INCREASING")
    if np.any(np.diff(strain) < -policy["strain_monotonic_tolerance"]):
        failures.append("STRAIN_REVERSAL")
    if strain[0] > targets[0] or strain[-1] < targets[-1] - policy["target_strain_tolerance"]:
        failures.append("TARGET_RANGE_NOT_REACHED")
    if strain[-1] > targets[-1] + policy["target_strain_tolerance"]:
        failures.append("TARGET_OVERSHOOT")
    if float(stress.min()) < -policy["stress_sign_tolerance_MPa"]:
        failures.append("REACTION_SIGN_ERROR")
    floor = policy["energy_floor_Nmm"]
    ie, ke, ae = data["ALLIE"], data["ALLKE"], data["ALLAE"]
    if np.any(ie < -floor) or np.any(ke < -floor):
        failures.append("NEGATIVE_ENERGY")
    active = ie > floor
    low_energy = ~active
    # Do not ignore the early-time region: use an absolute KE requirement there.
    if np.any(ke[low_energy] > policy["startup_ke_max_Nmm"]):
        failures.append("STARTUP_INERTIA")
    if not active.any():
        failures.append("NO_MEANINGFUL_INTERNAL_ENERGY")
    max_ke_ie = float(np.max(ke[active] / ie[active])) if active.any() else None
    max_ae_ie = float(np.max(np.abs(ae[active]) / ie[active])) if active.any() else None
    if max_ke_ie is not None and max_ke_ie >= policy["ke_ie_limit"]:
        failures.append("QUASISTATIC_FAIL")
    if max_ae_ie is not None and max_ae_ie > policy["ae_ie_limit"]:
        failures.append("ARTIFICIAL_ENERGY_REVIEW")
    keep = [0]
    for i in range(1, len(strain)):
        if strain[i] > strain[keep[-1]] + policy["strain_monotonic_tolerance"]:
            keep.append(i)
        elif abs(stress[i] - stress[keep[-1]]) > policy["duplicate_stress_tolerance_MPa"]:
            failures.append("MULTIVALUED_STRESS_AT_SAME_STRAIN")
    output = {"status": "CURVE_QA_FAILED" if failures else "CURVE_QA_PASS",
              "failures": sorted(set(failures)), "final_strain": float(strain[-1]),
              "max_ke_ie": max_ke_ie, "max_ae_ie": max_ae_ie,
              "energy_floor_Nmm": floor, "low_energy_points": int(low_energy.sum()),
              "stress_at_targets_MPa": None, "strain_targets": list(targets),
              "dataset_eligible": False,
              "note": "Curve-only QA; complete solver, contact, PBC and material-domain gates are still required."}
    if not failures:
        target_array = np.asarray(targets)
        # Endpoint snapping is allowed ONLY inside the documented roundoff tolerance.
        x = strain[keep].copy()
        if abs(x[-1] - target_array[-1]) <= policy["target_strain_tolerance"]:
            x[-1] = target_array[-1]
        if x[0] <= target_array[0] and x[-1] >= target_array[-1]:
            output["stress_at_targets_MPa"] = np.interp(target_array, x, stress[keep]).tolist()
        else:
            output["status"] = "CURVE_QA_FAILED"
            output["failures"].append("INTERPOLATION_RANGE_INVALID")
    return output


def read_history_csv(path):
    """Read a history CSV (the extract.py column schema) into assess()' columns dict."""
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = {name: [] for name in (reader.fieldnames or [])}
        for row in reader:
            for name in columns:
                columns[name].append(float(row[name]))
    return columns


def record_curve_qa(results_dir, *, policy_path, height_mm, area_mm2, log=print):
    """assess() one extracted history.csv and write curve_qa.json beside it.

    This is the run_case wiring point: extraction writes the canonical columns
    (time_s, u3_mm, rf3_N, the energy variables), the configured policy turns
    them into a recorded verdict. The verdict is diagnostics only: dataset_eligible
    stays false and a failed QA never invalidates the extraction itself.
    """
    policy = load_policy(policy_path)
    columns = read_history_csv(Path(results_dir) / "history.csv")
    # reaction sign -1 matches extract.py: stress = -RF3/A0, compression positive.
    assessment = assess(columns, height_mm, area_mm2, -1, policy)
    write_json(Path(results_dir) / "curve_qa.json", assessment)
    log("curve qa " + assessment["status"] + " (" + str(policy_path) + ")")
    return assessment
