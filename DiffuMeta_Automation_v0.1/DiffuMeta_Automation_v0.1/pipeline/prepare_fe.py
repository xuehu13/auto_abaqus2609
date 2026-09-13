"""Generate verified inputs and PBC includes, not a complete executable physical INP."""
from __future__ import annotations

import numpy as np

from .common import PipelineError, read_json, atomic_json, atomic_text, digest, reserve_directory
from .mesh_contract import load_bundle
from .pbc import relations, render_include


def prepare(npz, report, pairs, physics_path, material_path, output):
    mesh = load_bundle(npz, report, pairs)
    physics, material = read_json(physics_path), read_json(material_path)
    if physics["boundary_mode"] != "lateral_xy_platens" or physics["repeats"] != [1, 1, 1]:
        raise PipelineError("NOT_IMPLEMENTED", "v0.1 prepares only one cell with lateral XY PBC.")
    if material["type"] != "elastic_plastic_table":
        raise PipelineError("NOT_IMPLEMENTED", "Other material contracts are described in the design document.")
    values = [material["density_tonne_mm3"], material["E_MPa"], material["nu"],
              physics["relative_density"], physics["target_compression_strain"], physics["time_period_s"]]
    if not np.isfinite(values).all() or min(values[0], values[1], values[5]) <= 0:
        raise PipelineError("CONFIG_INVALID", "Invalid material/loading constants.")
    if not -1 < values[2] < 0.5 or not 0 < values[3] < 1 or not 0 < values[4] < 1:
        raise PipelineError("CONFIG_INVALID", "Invalid Poisson ratio, relative density or strain.")
    table = np.asarray(material["plastic_table_MPa_strain"], dtype=float)
    if (table.ndim != 2 or table.shape[1] != 2 or not len(table) or not np.isfinite(table).all()
            or np.any(table[:, 0] <= 0) or table[0, 1] != 0 or np.any(np.diff(table[:, 1]) <= 0)):
        raise PipelineError("CONFIG_INVALID", "Plastic table needs positive true stress and increasing equivalent plastic strain starting at zero.")
    L, area = mesh["L_mm"], mesh["area_mm2"]
    thickness = physics["relative_density"] * L**3 / area
    mapping = relations(mesh["x_pairs"], mesh["y_pairs"], physics["rotational_pbc"])
    count = len(mesh["nodes"])
    labels = {"rp_x": count + 1, "rp_y": count + 2, "rp_bottom": count + 3, "rp_top": count + 4,
              "first_plate_node": count + 5, "first_plate_element": len(mesh["triangles"]) + 1}
    folder = reserve_directory(output)
    lines = ["** Shell mesh only; not a complete Abaqus physical model.", "*Node"]
    lines.extend("%d, %.17g, %.17g, %.17g" % (i, *p) for i, p in enumerate(mesh["nodes"], 1))
    lines.append("*Element, type=S3R, elset=SHELL_ALL")
    lines.extend("%d, %d, %d, %d" % (i, *(p + 1)) for i, p in enumerate(mesh["triangles"], 1))
    atomic_text(folder / "shell_mesh.inc", "\n".join(lines) + "\n")
    atomic_text(folder / "lateral_pbc.inc", render_include(mapping, labels["rp_x"], labels["rp_y"]))
    atomic_json(folder / "pbc_map.json", mapping)
    identity = {"mesh_files": mesh["source_hashes"], "physics": physics,
                "material": material, "pbc_implementation": "representative-v1"}
    manifest = {"schema_version": 1, "status": "FE_INPUTS_PREPARED_ONLY",
                "model_key": digest(identity), **identity,
                "L_mm": L, "A0_mm2": L**2, "height_reference_mm": L,
                "surface_area_mm2": area, "thickness_mm": thickness,
                "target_displacement_mm": -physics["target_compression_strain"] * L,
                "labels": labels, "shell_nodes": count, "shell_elements": len(mesh["triangles"]),
                "equation_count": mapping["equation_count"], "dataset_eligible": False,
                "missing": ["rigid plates, material/section and contact keyword assembly",
                            "step/loading/output keyword assembly", "physical datacheck", "solve", "ODB QA"],
                "warning": "This directory contains ingredients, NOT a runnable physical.inp. No Abaqus validation was performed."}
    atomic_json(folder / "model_inputs.json", manifest)
    return manifest
