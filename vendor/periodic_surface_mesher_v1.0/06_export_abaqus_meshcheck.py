# -*- coding: utf-8 -*-

"""Step 06 — Export a mesh-only Abaqus S3R Data-Check model.

Purpose
-------
Turn the validated shell into an Abaqus .inp using S3R elements and placeholder
elastic properties.  This step deliberately excludes PBC equations, plates,
contact, real material, and loading so Abaqus Data Check tests the mesh itself.

Inputs : shell/<case>_shell.npz and report.json
Outputs: abaqus_meshcheck/<case>_meshcheck.inp, periodic-pair CSV, export report
"""
import csv
import json
import numpy as np


from meshlib.config import CFG

CASE_DIR = CFG.case_dir
INPUT_NPZ = CFG.shell_dir / f"{CFG.case_id}_shell.npz"
INPUT_REPORT = CFG.shell_dir / f"{CFG.case_id}_shell_report.json"
OUTPUT_DIR = CFG.abaqus_dir
OUTPUT_INP = OUTPUT_DIR / f"{CFG.meshcheck_job}.inp"
OUTPUT_PAIRS = OUTPUT_DIR / f"{CFG.case_id}_periodic_pairs.csv"
OUTPUT_REPORT = OUTPUT_DIR / f"{CFG.meshcheck_job}_export_report.json"
L = CFG.L
FACE_TOL = float(CFG.tol["boundary_mm"])


# ============================================================
# Write Abaqus node set
# ============================================================

def write_nset(
    f,
    name,
    node_ids,
    per_line=16
):

    node_ids = list(
        int(x)
        for x in node_ids
    )

    f.write(
        f"*Nset, nset={name}\n"
    )

    for i in range(
        0,
        len(node_ids),
        per_line
    ):

        chunk = node_ids[
            i:i + per_line
        ]

        f.write(
            ", ".join(
                str(x)
                for x in chunk
            )
            +
            "\n"
        )


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "================================================"
    )
    print(
        "STEP 06 - EXPORT ABAQUS S3R MESH CHECK"
    )
    print(
        "================================================"
    )


    if not INPUT_NPZ.exists():

        raise FileNotFoundError(
            INPUT_NPZ
        )


    if not INPUT_REPORT.exists():

        raise FileNotFoundError(
            INPUT_REPORT
        )


    with INPUT_REPORT.open(
        "r",
        encoding="utf-8"
    ) as f:

        previous_report = json.load(f)


    if not previous_report.get(
        "pass",
        False
    ):

        raise RuntimeError(
            "Step 05 shell validation did not PASS."
        )


    data = np.load(
        INPUT_NPZ
    )


    nodes = np.asarray(
        data["nodes"],
        dtype=np.float64
    )

    triangles = np.asarray(
        data["triangles"],
        dtype=np.int64
    )


    x_pairs = np.asarray(
        data["x_pairs"],
        dtype=np.int64
    )

    y_pairs = np.asarray(
        data["y_pairs"],
        dtype=np.int64
    )

    z_pairs = np.asarray(
        data["z_pairs"],
        dtype=np.int64
    )


    if len(nodes) == 0:

        raise RuntimeError(
            "No nodes."
        )


    if len(triangles) == 0:

        raise RuntimeError(
            "No triangles."
        )


    # Abaqus numbering is 1-based.
    abaqus_triangles = (
        triangles
        +
        1
    )


    # ========================================================
    # Boundary node sets
    # ========================================================

    X0 = np.where(
        np.abs(
            nodes[:, 0]
        )
        <=
        FACE_TOL
    )[0] + 1


    XL = np.where(
        np.abs(
            nodes[:, 0] - L
        )
        <=
        FACE_TOL
    )[0] + 1


    Y0 = np.where(
        np.abs(
            nodes[:, 1]
        )
        <=
        FACE_TOL
    )[0] + 1


    YL = np.where(
        np.abs(
            nodes[:, 1] - L
        )
        <=
        FACE_TOL
    )[0] + 1


    Z0 = np.where(
        np.abs(
            nodes[:, 2]
        )
        <=
        FACE_TOL
    )[0] + 1


    ZL = np.where(
        np.abs(
            nodes[:, 2] - L
        )
        <=
        FACE_TOL
    )[0] + 1


    print()
    print(
        "nodes     =",
        len(nodes)
    )

    print(
        "S3R elems =",
        len(triangles)
    )


    print()
    print(
        "Boundary nodes:"
    )

    print(
        "  X0 / XL =",
        len(X0),
        "/",
        len(XL)
    )

    print(
        "  Y0 / YL =",
        len(Y0),
        "/",
        len(YL)
    )

    print(
        "  Z0 / ZL =",
        len(Z0),
        "/",
        len(ZL)
    )


    # ========================================================
    # Periodic pair sanity check
    # ========================================================

    pair_report = {}


    for name, pairs, axis in (
        (
            "X",
            x_pairs,
            0
        ),
        (
            "Y",
            y_pairs,
            1
        ),
        (
            "Z",
            z_pairs,
            2
        ),
    ):

        if len(pairs) == 0:

            raise RuntimeError(
                f"No {name} periodic pairs."
            )


        low = nodes[
            pairs[:, 0]
        ]

        high = nodes[
            pairs[:, 1]
        ]


        delta = (
            high
            -
            low
        )


        expected = np.zeros(
            3,
            dtype=np.float64
        )

        expected[axis] = L


        err = np.linalg.norm(
            delta
            -
            expected,
            axis=1
        )


        max_error = float(
            np.max(err)
        )


        print(
            f"{name} periodic pairs = "
            f"{len(pairs)}, "
            f"max vector error = "
            f"{max_error}"
        )


        if max_error > 1.0e-8:

            raise RuntimeError(
                f"{name} periodic pair error too large."
            )


        pair_report[name] = {

            "count":
                int(
                    len(pairs)
                ),

            "max_vector_error_mm":
                max_error,
        }


    # ========================================================
    # Write INP
    #
    # IMPORTANT:
    #
    # This is intentionally a MESH-ONLY data-check model.
    #
    # Placeholder elastic material and shell thickness are
    # used solely so Abaqus has a complete shell definition.
    #
    # NO:
    #   - PBC equations
    #   - rigid plates
    #   - contact
    #   - real material
    #   - compression loading
    #
    # ========================================================

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    with OUTPUT_INP.open(
        "w",
        encoding="ascii",
        newline="\n"
    ) as f:

        f.write(
            "*Heading\n"
        )

        f.write(
            "** -------------------------------------------------\n"
        )

        f.write(
            "** DiffuMeta periodic shell mesh check\n"
        )

        f.write(
            "** Step 06\n"
        )

        f.write(
            "** Validated periodic CGAL mesh\n"
        )

        f.write(
            "** Mesh size is controlled by config/case.json\n"
        )

        f.write(
            "** -------------------------------------------------\n"
        )


        f.write(
            "*Preprint, echo=NO, model=NO, "
            "history=NO, contact=NO\n"
        )


        # ----------------------------------------------------
        # Nodes
        # ----------------------------------------------------

        f.write(
            "*Node\n"
        )


        for i, p in enumerate(
            nodes,
            start=1
        ):

            f.write(
                f"{i}, "
                f"{p[0]:.17g}, "
                f"{p[1]:.17g}, "
                f"{p[2]:.17g}\n"
            )


        # ----------------------------------------------------
        # S3R triangular shell elements
        # ----------------------------------------------------

        f.write(
            "*Element, type=S3R, elset=EALL\n"
        )


        for eid, tri in enumerate(
            abaqus_triangles,
            start=1
        ):

            f.write(
                f"{eid}, "
                f"{tri[0]}, "
                f"{tri[1]}, "
                f"{tri[2]}\n"
            )


        # ----------------------------------------------------
        # Boundary sets
        # ----------------------------------------------------

        write_nset(
            f,
            "X0",
            X0
        )

        write_nset(
            f,
            "XL",
            XL
        )

        write_nset(
            f,
            "Y0",
            Y0
        )

        write_nset(
            f,
            "YL",
            YL
        )

        write_nset(
            f,
            "Z0",
            Z0
        )

        write_nset(
            f,
            "ZL",
            ZL
        )


        # ----------------------------------------------------
        # Placeholder material / section
        #
        # These values are NOT the physical model.
        # They exist only for mesh Data Check.
        # ----------------------------------------------------

        f.write(
            "*Material, name=MESH_CHECK_MAT\n"
        )

        f.write(
            "*Elastic\n"
        )

        f.write(
            f"{float(CFG.abaqus['meshcheck_material_E'])}, "
            f"{float(CFG.abaqus['meshcheck_material_nu'])}\n"
        )


        f.write(
            "*Shell Section, "
            "elset=EALL, "
            "material=MESH_CHECK_MAT\n"
        )

        f.write(
            f"{float(CFG.abaqus['meshcheck_thickness_mm'])}\n"
        )


        # ----------------------------------------------------
        # Dummy analysis step.
        #
        # We will run ABAQUS DATACHECK ONLY,
        # not the actual analysis.
        # ----------------------------------------------------

        f.write(
            "*Step, name=MESH_CHECK, nlgeom=YES\n"
        )

        f.write(
            "*Static\n"
        )

        f.write(
            "0.1, 1.0\n"
        )

        f.write(
            "*End Step\n"
        )


    # ========================================================
    # Export periodic node-pair CSV for the final datacheck validator
    # ========================================================

    with OUTPUT_PAIRS.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "axis",
                "low_node",
                "high_node",
                "dx",
                "dy",
                "dz",
            ]
        )


        for name, pairs in (
            (
                "X",
                x_pairs
            ),
            (
                "Y",
                y_pairs
            ),
            (
                "Z",
                z_pairs
            ),
        ):

            for low_id, high_id in pairs:

                delta = (
                    nodes[high_id]
                    -
                    nodes[low_id]
                )


                writer.writerow(
                    [
                        name,

                        int(
                            low_id
                            +
                            1
                        ),

                        int(
                            high_id
                            +
                            1
                        ),

                        float(
                            delta[0]
                        ),

                        float(
                            delta[1]
                        ),

                        float(
                            delta[2]
                        ),
                    ]
                )


    report = {

        "source_npz":
            str(
                INPUT_NPZ
            ),

        "nodes":
            int(
                len(nodes)
            ),

        "elements":
            int(
                len(triangles)
            ),

        "element_type":
            "S3R",

        "face_sets": {

            "X0":
                int(
                    len(X0)
                ),

            "XL":
                int(
                    len(XL)
                ),

            "Y0":
                int(
                    len(Y0)
                ),

            "YL":
                int(
                    len(YL)
                ),

            "Z0":
                int(
                    len(Z0)
                ),

            "ZL":
                int(
                    len(ZL)
                ),
        },

        "periodic_pairs":
            pair_report,

        "inp":
            str(
                OUTPUT_INP
            ),

        "periodic_pair_csv":
            str(
                OUTPUT_PAIRS
            ),

        "export_pass":
            True,
    }


    with OUTPUT_REPORT.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )


    print()
    print(
        "Saved:"
    )

    print(
        " ",
        OUTPUT_INP
    )

    print(
        " ",
        OUTPUT_PAIRS
    )

    print(
        " ",
        OUTPUT_REPORT
    )


    print()
    print(
        "================================================"
    )

    print(
        "STEP 06 EXPORT STATUS: PASS"
    )

    print(
        "================================================"
    )


if __name__ == "__main__":

    main()
