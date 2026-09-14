"""Checks aligned raw histories. Outputs are NOT complete FE acceptance decisions."""
import numpy as np

TARGETS = [0.016, 0.031, 0.055, 0.094, 0.149, 0.165, 0.204, 0.227, 0.267, 0.282, 0.300]


def assess(columns, height_mm, area_mm2, compression_reaction_sign, policy):
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
    if strain[0] > TARGETS[0] or strain[-1] < TARGETS[-1] - policy["target_strain_tolerance"]:
        failures.append("TARGET_RANGE_NOT_REACHED")
    if strain[-1] > TARGETS[-1] + policy["target_strain_tolerance"]:
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
              "stress_11_MPa": None, "strain_11": TARGETS,
              "dataset_eligible": False,
              "note": "Curve-only QA; complete solver, contact, PBC and material-domain gates are still required."}
    if not failures:
        targets = np.asarray(TARGETS)
        # Endpoint snapping is allowed ONLY inside the documented roundoff tolerance.
        x = strain[keep].copy()
        if abs(x[-1] - TARGETS[-1]) <= policy["target_strain_tolerance"]:
            x[-1] = TARGETS[-1]
        if x[0] <= targets[0] and x[-1] >= targets[-1]:
            output["stress_11_MPa"] = np.interp(targets, x, stress[keep]).tolist()
        else:
            output["status"] = "CURVE_QA_FAILED"
            output["failures"].append("INTERPOLATION_RANGE_INVALID")
    return output
