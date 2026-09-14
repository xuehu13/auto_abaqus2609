# -*- coding: utf-8 -*-

"""Step 04 — Export the protected Periodic_3 features and runtime case file.

Purpose
-------
Validate the standardized curves one final time, write the eight master feature
polylines expected by CGAL, and write cgal_case.txt containing the cell size,
implicit equation, mesh criteria, and random seed used by the C++ mesher.

Input : standard_boundary_curves.npz
Outputs: cgal_input/periodic3_master_features.txt,
         cgal_input/periodic3_master_features_report.json,
         cgal_input/cgal_case.txt
"""
import json
import numpy as np


from meshlib.config import CFG
from meshlib.surface import implicit_points, gradient_magnitude as _gradient_magnitude

CASE_ID = CFG.case_id
L = CFG.L
CASE_DIR = CFG.case_dir
INPUT_FILE = CASE_DIR / "standard_boundary_curves.npz"
OUTPUT_DIR = CFG.cgal_input_dir
OUTPUT_TXT = OUTPUT_DIR / "periodic3_master_features.txt"
OUTPUT_JSON = OUTPUT_DIR / "periodic3_master_features_report.json"
OUTPUT_CGAL_CONFIG = OUTPUT_DIR / "cgal_case.txt"
PLANE_TOL = float(CFG.tol["feature_plane_mm"])
F_TOL = 1.0e-8
PERIODIC_TOL = float(CFG.tol["feature_periodic_mm"])
MIN_SEGMENT = 0.05
MAX_SEGMENT = 0.20
FACE_NAMES = {0: "X0", 1: "Y0", 2: "Z0"}

def implicit_function(points):
    return implicit_points(points)

def gradient_magnitude(points):
    return _gradient_magnitude(points)


# ============================================================
# Periodic canonicalization for endpoint classes
# ============================================================

def canonicalize_periodic_point(p):

    q = np.asarray(
        p,
        dtype=np.float64
    ).copy()

    for axis in range(3):

        if abs(q[axis]) <= PERIODIC_TOL:
            q[axis] = 0.0

        elif abs(q[axis] - L) <= PERIODIC_TOL:
            q[axis] = 0.0

        else:
            q[axis] = (
                q[axis] % L
            )

    return q


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "================================================"
    )
    print(
        "PREPARE PERIODIC_3 MASTER FEATURES"
    )
    print(
        "================================================"
    )

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Not found: {INPUT_FILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    data = np.load(
        INPUT_FILE
    )

    points = data[
        "curve_points"
    ].astype(np.float64)

    offsets = data[
        "curve_offsets"
    ].astype(np.int64)

    face_ids = data[
        "curve_face_id"
    ].astype(np.int8)

    closed_flags = data[
        "curve_closed"
    ].astype(bool)

    start_classes = data[
        "curve_start_class"
    ].astype(np.int64)

    end_classes = data[
        "curve_end_class"
    ].astype(np.int64)


    n_curves = len(offsets) - 1


    print()
    print(
        "master curves =",
        n_curves
    )


    if n_curves == 0:

        raise RuntimeError(
            "No master feature curves."
        )


    curve_records = []

    endpoint_groups = {}

    global_min_segment = np.inf
    global_max_segment = 0.0

    global_max_node_f = 0.0

    global_max_plane_error = 0.0

    global_max_chord_error = 0.0

    finite_ok = True
    bounds_ok = True


    face_local_count = {
        0: 0,
        1: 0,
        2: 0,
    }


    # ========================================================
    # Process every master curve
    # ========================================================

    for i in range(n_curves):

        p0 = int(
            offsets[i]
        )

        p1 = int(
            offsets[i + 1]
        )

        curve = points[
            p0:p1
        ].copy()


        face_id = int(
            face_ids[i]
        )

        if face_id not in FACE_NAMES:

            raise RuntimeError(
                f"Invalid master face id: {face_id}"
            )


        face_name = FACE_NAMES[
            face_id
        ]

        local_id = (
            face_local_count[
                face_id
            ]
        )

        face_local_count[
            face_id
        ] += 1


        curve_name = (
            f"{face_name}_curve_"
            f"{local_id:03d}"
        )


        closed = bool(
            closed_flags[i]
        )

        start_class = int(
            start_classes[i]
        )

        end_class = int(
            end_classes[i]
        )


        if len(curve) < 2:

            raise RuntimeError(
                f"{curve_name}: "
                "fewer than two points."
            )


        # ----------------------------------------------------
        # Basic numerical validity
        # ----------------------------------------------------

        if not np.all(
            np.isfinite(curve)
        ):

            finite_ok = False


        if (
            np.any(
                curve < -PLANE_TOL
            )
            or
            np.any(
                curve > L + PLANE_TOL
            )
        ):

            bounds_ok = False


        # ----------------------------------------------------
        # Every master curve must lie exactly on:
        #
        # face 0 -> X0
        # face 1 -> Y0
        # face 2 -> Z0
        # ----------------------------------------------------

        plane_error = float(
            np.max(
                np.abs(
                    curve[:, face_id]
                )
            )
        )


        global_max_plane_error = max(
            global_max_plane_error,
            plane_error
        )


        # Snap only numerical noise.
        curve[:, face_id] = 0.0


        # ----------------------------------------------------
        # Node residual
        # ----------------------------------------------------

        node_f = np.abs(
            implicit_function(
                curve
            )
        )


        max_node_f = float(
            node_f.max()
        )


        global_max_node_f = max(
            global_max_node_f,
            max_node_f
        )


        # ----------------------------------------------------
        # Feature segments
        # ----------------------------------------------------

        if closed:

            geom_curve = np.vstack(
                [
                    curve,
                    curve[0]
                ]
            )

        else:

            geom_curve = curve


        delta = (
            geom_curve[1:]
            -
            geom_curve[:-1]
        )


        seg = np.linalg.norm(
            delta,
            axis=1
        )


        min_seg = float(
            seg.min()
        )

        max_seg = float(
            seg.max()
        )

        mean_seg = float(
            seg.mean()
        )


        global_min_segment = min(
            global_min_segment,
            min_seg
        )

        global_max_segment = max(
            global_max_segment,
            max_seg
        )


        # ----------------------------------------------------
        # Chord-vs-exact-implicit diagnostic
        #
        # Feature curves are piecewise-linear.
        # Sample 1/4, 1/2 and 3/4 of every segment and
        # estimate normal deviation:
        #
        #     |f| / |grad f|
        #
        # This is diagnostic only for now.
        # ----------------------------------------------------

        samples = []

        for alpha in (
            0.25,
            0.50,
            0.75,
        ):

            q = (
                geom_curve[:-1]
                * (1.0 - alpha)

                +

                geom_curve[1:]
                * alpha
            )

            samples.append(q)


        samples = np.vstack(
            samples
        )


        f_sample = np.abs(
            implicit_function(
                samples
            )
        )


        grad_sample = (
            gradient_magnitude(
                samples
            )
        )


        chord_error = (
            f_sample
            /
            np.maximum(
                grad_sample,
                1.0e-14
            )
        )


        max_chord_error = float(
            chord_error.max()
        )


        global_max_chord_error = max(
            global_max_chord_error,
            max_chord_error
        )


        # ----------------------------------------------------
        # Endpoint periodic classes
        # ----------------------------------------------------

        if not closed:

            for side, cls, p in (
                (
                    "start",
                    start_class,
                    curve[0]
                ),
                (
                    "end",
                    end_class,
                    curve[-1]
                ),
            ):

                if cls < 0:

                    raise RuntimeError(
                        f"{curve_name}: "
                        f"{side} endpoint "
                        "has invalid periodic class."
                    )


                endpoint_groups.setdefault(
                    cls,
                    []
                ).append(
                    {
                        "curve":
                            curve_name,

                        "side":
                            side,

                        "canonical":
                            canonicalize_periodic_point(
                                p
                            ),

                        "physical":
                            p.copy(),
                    }
                )


        # ----------------------------------------------------
        # CGAL cycle representation
        #
        # A geometrically closed curve is explicitly closed by
        # repeating its first point.
        #
        # A periodic winding curve whose start_class equals
        # end_class is NOT closed here: its Euclidean endpoints
        # may differ by one full cell and Periodic_3 must see
        # that winding.
        # ----------------------------------------------------

        if closed:

            output_curve = np.vstack(
                [
                    curve,
                    curve[0]
                ]
            )

        else:

            output_curve = curve.copy()


        curve_records.append(
            {
                "curve_index":
                    i,

                "curve_name":
                    curve_name,

                "face_id":
                    face_id,

                "closed":
                    closed,

                "start_class":
                    start_class,

                "end_class":
                    end_class,

                "points":
                    output_curve,

                "n_input_points":
                    int(len(curve)),

                "n_output_points":
                    int(
                        len(output_curve)
                    ),

                "min_segment_mm":
                    min_seg,

                "mean_segment_mm":
                    mean_seg,

                "max_segment_mm":
                    max_seg,

                "max_node_abs_f":
                    max_node_f,

                "max_chord_normal_error_mm":
                    max_chord_error,

                "plane_error_mm":
                    plane_error,
            }
        )


        print()
        print(
            "---------------------------------------------"
        )

        print(curve_name)

        print(
            "---------------------------------------------"
        )

        print(
            "face             =",
            face_name
        )

        print(
            "closed           =",
            closed
        )

        print(
            "start class      =",
            start_class
        )

        print(
            "end class        =",
            end_class
        )

        print(
            "points           =",
            len(output_curve)
        )

        print(
            "segment min      =",
            min_seg
        )

        print(
            "segment mean     =",
            mean_seg
        )

        print(
            "segment max      =",
            max_seg
        )

        print(
            "max node |f|     =",
            max_node_f
        )

        print(
            "max chord error  =",
            max_chord_error
        )

        print(
            "plane error      =",
            plane_error
        )


    # ========================================================
    # Check periodic endpoint-class consistency
    # ========================================================

    max_endpoint_class_mismatch = 0.0

    endpoint_report = {}


    print()
    print(
        "================================================"
    )
    print(
        "PERIODIC FEATURE ENDPOINT CLASSES"
    )
    print(
        "================================================"
    )


    for cls in sorted(
        endpoint_groups
    ):

        records = (
            endpoint_groups[
                cls
            ]
        )


        canonical = np.asarray(
            [
                r["canonical"]
                for r in records
            ],
            dtype=np.float64
        )


        ref = canonical[0]


        mismatch = np.linalg.norm(
            canonical - ref,
            axis=1
        )


        class_max = float(
            mismatch.max()
        )


        max_endpoint_class_mismatch = max(
            max_endpoint_class_mismatch,
            class_max
        )


        print()
        print(
            "class",
            cls
        )

        print(
            "  occurrences =",
            len(records)
        )

        print(
            "  canonical   =",
            ref
        )

        print(
            "  max mismatch=",
            class_max
        )


        endpoint_report[
            str(cls)
        ] = {

            "occurrences":
                int(
                    len(records)
                ),

            "canonical_point":
                ref.tolist(),

            "max_mismatch":
                class_max,

            "members":
                [
                    {
                        "curve":
                            r["curve"],

                        "side":
                            r["side"],

                        "physical_point":
                            r[
                                "physical"
                            ].tolist(),
                    }
                    for r in records
                ],
        }


    # ========================================================
    # Write simple C++ feature file
    #
    # line 1:
    #   number_of_curves
    #
    # Each curve:
    #
    # face_id closed start_class end_class n_points
    # x y z
    # ...
    #
    # ========================================================

    with OUTPUT_TXT.open(
        "w",
        encoding="ascii"
    ) as f:

        f.write(
            f"{len(curve_records)}\n"
        )


        for r in curve_records:

            f.write(
                f"{r['face_id']} "
                f"{int(r['closed'])} "
                f"{r['start_class']} "
                f"{r['end_class']} "
                f"{r['n_output_points']}\n"
            )


            for p in r["points"]:

                f.write(
                    f"{p[0]:.17g} "
                    f"{p[1]:.17g} "
                    f"{p[2]:.17g}\n"
                )


    # ========================================================
    # Acceptance
    # ========================================================

    pass_status = bool(

        finite_ok

        and

        bounds_ok

        and

        global_max_plane_error
        <= PLANE_TOL

        and

        global_max_node_f
        <= F_TOL

        and

        global_min_segment
        > MIN_SEGMENT

        and

        global_max_segment
        <= MAX_SEGMENT + 1.0e-10

        and

        max_endpoint_class_mismatch
        <= PERIODIC_TOL
    )


    # ========================================================
    # JSON report
    # ========================================================

    report = {

        "case_id":
            CASE_ID,

        "cell_size_mm":
            L,

        "n_master_feature_curves":
            int(
                len(curve_records)
            ),

        "face_curve_counts": {

            "X0":
                int(
                    face_local_count[0]
                ),

            "Y0":
                int(
                    face_local_count[1]
                ),

            "Z0":
                int(
                    face_local_count[2]
                ),
        },

        "finite_ok":
            finite_ok,

        "bounds_ok":
            bounds_ok,

        "global_min_segment_mm":
            float(
                global_min_segment
            ),

        "global_max_segment_mm":
            float(
                global_max_segment
            ),

        "global_max_node_abs_f":
            float(
                global_max_node_f
            ),

        "global_max_plane_error_mm":
            float(
                global_max_plane_error
            ),

        "global_max_feature_chord_normal_error_mm":
            float(
                global_max_chord_error
            ),

        "max_endpoint_class_mismatch_mm":
            float(
                max_endpoint_class_mismatch
            ),

        "endpoint_classes":
            endpoint_report,

        "curves":
            [
                {
                    k: v
                    for k, v
                    in r.items()
                    if k != "points"
                }
                for r
                in curve_records
            ],

        "pass":
            pass_status,
    }


    with OUTPUT_JSON.open(
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
        "================================================"
    )
    print(
        "PERIODIC_3 FEATURE SUMMARY"
    )
    print(
        "================================================"
    )

    print(
        "master feature curves       =",
        len(curve_records)
    )

    print(
        "X0 / Y0 / Z0 curves         =",
        face_local_count[0],
        "/",
        face_local_count[1],
        "/",
        face_local_count[2]
    )

    print(
        "segment minimum             =",
        global_min_segment
    )

    print(
        "segment maximum             =",
        global_max_segment
    )

    print(
        "max node |f|               =",
        global_max_node_f
    )

    print(
        "max feature chord error     =",
        global_max_chord_error
    )

    print(
        "max endpoint class mismatch =",
        max_endpoint_class_mismatch
    )


    # Export a compact runtime configuration for the C++ mesher.
    # The equation is read at runtime; changing the surface does not require
    # recompiling the CGAL executable.
    c = CFG.cgal
    with OUTPUT_CGAL_CONFIG.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"L={CFG.L}\n")
        f.write(f"expression={CFG.expression}\n")
        f.write(f"edge_size={float(c['edge_size_mm'])}\n")
        f.write(f"facet_angle={float(c['facet_angle_deg'])}\n")
        f.write(f"facet_size={float(c['facet_size_mm'])}\n")
        f.write(f"facet_distance={float(c['facet_distance_mm'])}\n")
        f.write(f"cell_radius_edge_ratio={float(c['cell_radius_edge_ratio'])}\n")
        f.write(f"cell_size={float(c['cell_size_mm'])}\n")
        f.write(f"random_seed={int(c['random_seed'])}\n")

    print()
    print("Saved:")
    print(" ", OUTPUT_TXT)
    print(" ", OUTPUT_JSON)
    print(" ", OUTPUT_CGAL_CONFIG)


    print()
    print(
        "================================================"
    )

    if pass_status:

        print(
            "PERIODIC_3 FEATURE PREP STATUS: PASS"
        )

    else:

        print(
            "PERIODIC_3 FEATURE PREP STATUS: FAIL"
        )

    print(
        "================================================"
    )


    if not pass_status:

        raise SystemExit(3)


if __name__ == "__main__":
    main()
