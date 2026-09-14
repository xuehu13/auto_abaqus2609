# -*- coding: utf-8 -*-

"""Step 05 — Build and strictly validate the final canonical shell mesh.

Purpose
-------
Read CGAL's canonical triangle CSV, deduplicate nodes while keeping x=0 and x=L
as distinct Abaqus nodes, orient triangles consistently, and enforce strict
checks for topology, periodic node/edge matching, element quality, connectedness,
and geometric error relative to the implicit surface.

Input : cgal_output/<case>_mesh_canonical_triangles.csv
Outputs: shell/<case>_shell.npz, <case>_shell_report.json, <case>_shell.obj
"""
from collections import defaultdict, deque
import csv
import hashlib
import itertools
import json
import math

import numpy as np
from scipy.spatial import cKDTree


# ============================================================
# Central configuration / surface definition
# ============================================================

from meshlib.config import CFG
from meshlib.surface import implicit_points, gradient_points

CASE_ID = CFG.case_id
L = CFG.L
CASE_DIR = CFG.case_dir
INPUT_CSV = CFG.cgal_output_dir / f"{CFG.mesh_prefix}_canonical_triangles.csv"
OUTPUT_DIR = CFG.shell_dir
OUTPUT_NPZ = OUTPUT_DIR / f"{CFG.case_id}_shell.npz"
OUTPUT_JSON = OUTPUT_DIR / f"{CFG.case_id}_shell_report.json"
OUTPUT_OBJ = OUTPUT_DIR / f"{CFG.case_id}_shell.obj"
DEDUP_TOL = float(CFG.tol["dedup_mm"])
FACE_TOL = float(CFG.tol["boundary_mm"])
PAIR_TOL = float(CFG.tol["final_pair_mm"])
AREA_TOL = float(CFG.tol["area_mm2"])

def implicit_function(points):
    return implicit_points(points)

def implicit_gradient(points):
    return gradient_points(points)


# ============================================================
# SHA256
# ============================================================

def sha256_file(path):

    h = hashlib.sha256()

    with path.open("rb") as f:

        while True:

            block = f.read(
                1024 * 1024
            )

            if not block:
                break

            h.update(block)

    return h.hexdigest()


# ============================================================
# Read canonical triangles
# ============================================================

def read_triangle_csv(path):

    triangles = []

    facet_ids = []

    shifts = []

    with path.open(
        "r",
        newline="",
        encoding="utf-8"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            facet_ids.append(
                int(row["facet_id"])
            )

            triangle = np.array(
                [
                    [
                        float(row["x0"]),
                        float(row["y0"]),
                        float(row["z0"]),
                    ],
                    [
                        float(row["x1"]),
                        float(row["y1"]),
                        float(row["z1"]),
                    ],
                    [
                        float(row["x2"]),
                        float(row["y2"]),
                        float(row["z2"]),
                    ],
                ],
                dtype=np.float64
            )

            triangles.append(
                triangle
            )

            shifts.append(
                [
                    int(row["shift_x"]),
                    int(row["shift_y"]),
                    int(row["shift_z"]),
                ]
            )

    return (
        np.asarray(
            triangles,
            dtype=np.float64
        ),
        np.asarray(
            facet_ids,
            dtype=np.int64
        ),
        np.asarray(
            shifts,
            dtype=np.int32
        ),
    )


# ============================================================
# Snap numerical noise exactly onto cube planes
# ============================================================

def snap_cube_planes(points):

    p = np.asarray(
        points,
        dtype=np.float64
    ).copy()

    for axis in range(3):

        low = (
            np.abs(
                p[..., axis]
            )
            <= FACE_TOL
        )

        high = (
            np.abs(
                p[..., axis] - L
            )
            <= FACE_TOL
        )

        p[..., axis][low] = 0.0

        p[..., axis][high] = L

    return p


# ============================================================
# Deterministic vertex deduplication
#
# Search neighboring spatial bins, so points close to a bin
# boundary are still merged correctly.
# ============================================================

def deduplicate_vertices(
    triangle_points
):

    nodes = []

    triangles = []

    bins = defaultdict(list)


    def bin_key(p):

        return tuple(
            np.floor(
                p / DEDUP_TOL
            ).astype(np.int64)
        )


    for triangle in triangle_points:

        tri_ids = []

        for p in triangle:

            key = bin_key(p)

            candidates = []

            for dx, dy, dz in itertools.product(
                (-1, 0, 1),
                repeat=3
            ):

                nk = (
                    key[0] + dx,
                    key[1] + dy,
                    key[2] + dz
                )

                candidates.extend(
                    bins.get(
                        nk,
                        []
                    )
                )


            found = None

            for node_id in sorted(
                candidates
            ):

                if (
                    np.linalg.norm(
                        nodes[node_id] - p
                    )
                    <= DEDUP_TOL
                ):

                    found = node_id

                    break


            if found is None:

                found = len(nodes)

                nodes.append(
                    p.copy()
                )

                bins[key].append(
                    found
                )


            tri_ids.append(
                found
            )


        triangles.append(
            tri_ids
        )


    return (
        np.asarray(
            nodes,
            dtype=np.float64
        ),
        np.asarray(
            triangles,
            dtype=np.int64
        ),
    )


# ============================================================
# Edge topology
# ============================================================

def build_edge_map(triangles):

    edge_map = defaultdict(list)

    for tid, tri in enumerate(
        triangles
    ):

        directed_edges = (
            (tri[0], tri[1]),
            (tri[1], tri[2]),
            (tri[2], tri[0]),
        )

        for u, v in directed_edges:

            a = int(
                min(u, v)
            )

            b = int(
                max(u, v)
            )

            sign = (
                +1
                if (u == a and v == b)
                else -1
            )

            edge_map[
                (a, b)
            ].append(
                (tid, sign)
            )

    return edge_map


# ============================================================
# Consistent triangle orientation
# ============================================================

def orient_triangles(
    nodes,
    triangles
):

    triangles = (
        triangles.copy()
    )

    edge_map = build_edge_map(
        triangles
    )

    n_triangles = len(
        triangles
    )

    factor = np.zeros(
        n_triangles,
        dtype=np.int8
    )

    adjacency = [
        []
        for _ in range(
            n_triangles
        )
    ]


    for edge, incidences in edge_map.items():

        if len(incidences) != 2:
            continue

        (
            t0,
            s0
        ), (
            t1,
            s1
        ) = incidences

        adjacency[t0].append(
            (
                t1,
                s0,
                s1
            )
        )

        adjacency[t1].append(
            (
                t0,
                s1,
                s0
            )
        )


    orientation_conflicts = 0

    components = []


    for root in range(
        n_triangles
    ):

        if factor[root] != 0:
            continue


        factor[root] = 1

        q = deque(
            [root]
        )

        component = []


        while q:

            t = q.popleft()

            component.append(
                t
            )


            for (
                nb,
                sign_t,
                sign_nb
            ) in adjacency[t]:

                required = (
                    -sign_t
                    * sign_nb
                    * factor[t]
                )


                if factor[nb] == 0:

                    factor[nb] = required

                    q.append(
                        nb
                    )

                elif (
                    factor[nb]
                    != required
                ):

                    orientation_conflicts += 1


        components.append(
            component
        )


    flip = np.where(
        factor < 0
    )[0]


    triangles[
        flip,
        1
    ], triangles[
        flip,
        2
    ] = (
        triangles[
            flip,
            2
        ].copy(),
        triangles[
            flip,
            1
        ].copy()
    )


    # --------------------------------------------------------
    # Choose global sign of each component using analytic grad f
    # --------------------------------------------------------

    for component in components:

        ids = np.asarray(
            component,
            dtype=np.int64
        )

        pts = nodes[
            triangles[ids]
        ]

        normal = np.cross(
            pts[:, 1] - pts[:, 0],
            pts[:, 2] - pts[:, 0]
        )

        centroid = np.mean(
            pts,
            axis=1
        )

        grad = implicit_gradient(
            centroid
        )

        score = np.sum(
            np.einsum(
                "ij,ij->i",
                normal,
                grad
            )
        )


        if score < 0.0:

            triangles[
                ids,
                1
            ], triangles[
                ids,
                2
            ] = (
                triangles[
                    ids,
                    2
                ].copy(),
                triangles[
                    ids,
                    1
                ].copy()
            )


    return (
        triangles,
        orientation_conflicts,
        components,
    )


# ============================================================
# Triangle quality
# ============================================================

def triangle_quality(
    nodes,
    triangles
):

    p = nodes[
        triangles
    ]

    e01 = np.linalg.norm(
        p[:, 1] - p[:, 0],
        axis=1
    )

    e12 = np.linalg.norm(
        p[:, 2] - p[:, 1],
        axis=1
    )

    e20 = np.linalg.norm(
        p[:, 0] - p[:, 2],
        axis=1
    )


    cross = np.cross(
        p[:, 1] - p[:, 0],
        p[:, 2] - p[:, 0]
    )

    double_area = np.linalg.norm(
        cross,
        axis=1
    )

    area = (
        0.5
        * double_area
    )


    def angle_between(
        a,
        b
    ):

        dot = np.einsum(
            "ij,ij->i",
            a,
            b
        )

        na = np.linalg.norm(
            a,
            axis=1
        )

        nb = np.linalg.norm(
            b,
            axis=1
        )

        denom = (
            na
            *
            nb
        )

        c = np.divide(
            dot,
            denom,
            out=np.ones_like(dot),
            where=denom > 0
        )

        c = np.clip(
            c,
            -1.0,
            1.0
        )

        return np.degrees(
            np.arccos(c)
        )


    angle0 = angle_between(
        p[:, 1] - p[:, 0],
        p[:, 2] - p[:, 0]
    )

    angle1 = angle_between(
        p[:, 0] - p[:, 1],
        p[:, 2] - p[:, 1]
    )

    angle2 = angle_between(
        p[:, 0] - p[:, 2],
        p[:, 1] - p[:, 2]
    )


    min_angle = np.minimum.reduce(
        [
            angle0,
            angle1,
            angle2
        ]
    )


    edge_sq_sum = (
        e01 * e01
        +
        e12 * e12
        +
        e20 * e20
    )


    shape_q = np.divide(
        4.0
        *
        np.sqrt(3.0)
        *
        area,
        edge_sq_sum,
        out=np.zeros_like(area),
        where=edge_sq_sum > 0
    )


    min_edge = np.minimum.reduce(
        [
            e01,
            e12,
            e20
        ]
    )

    max_edge = np.maximum.reduce(
        [
            e01,
            e12,
            e20
        ]
    )


    edge_ratio = np.divide(
        max_edge,
        min_edge,
        out=np.full_like(
            max_edge,
            np.inf
        ),
        where=min_edge > 0
    )


    return {
        "edges":
            np.concatenate(
                [
                    e01,
                    e12,
                    e20
                ]
            ),

        "area":
            area,

        "min_angle":
            min_angle,

        "shape_q":
            shape_q,

        "edge_ratio":
            edge_ratio,
    }


# ============================================================
# Statistical summary
# ============================================================

def stats(a):

    a = np.asarray(
        a,
        dtype=np.float64
    )

    return {
        "min":
            float(
                np.min(a)
            ),

        "q01":
            float(
                np.percentile(
                    a,
                    1
                )
            ),

        "q05":
            float(
                np.percentile(
                    a,
                    5
                )
            ),

        "median":
            float(
                np.median(a)
            ),

        "mean":
            float(
                np.mean(a)
            ),

        "q95":
            float(
                np.percentile(
                    a,
                    95
                )
            ),

        "q99":
            float(
                np.percentile(
                    a,
                    99
                )
            ),

        "max":
            float(
                np.max(a)
            ),
    }


# ============================================================
# Periodic face matching
# ============================================================

def periodic_face_check(
    nodes,
    free_edges,
    axis
):

    tangential = [
        a
        for a in range(3)
        if a != axis
    ]


    low_ids = np.where(
        np.abs(
            nodes[:, axis]
        )
        <= FACE_TOL
    )[0]


    high_ids = np.where(
        np.abs(
            nodes[:, axis] - L
        )
        <= FACE_TOL
    )[0]


    result = {
        "low_nodes":
            int(
                len(low_ids)
            ),

        "high_nodes":
            int(
                len(high_ids)
            ),
    }


    if (
        len(low_ids) == 0
        or
        len(high_ids) == 0
    ):

        result.update(
            {
                "bijective":
                    False,

                "symmetric":
                    False,

                "max_mismatch":
                    None,

                "edge_topology_equal":
                    False,

                "pairs":
                    np.empty(
                        (0, 2),
                        dtype=np.int64
                    ),
            }
        )

        return result


    low_uv = nodes[
        low_ids
    ][:, tangential]

    high_uv = nodes[
        high_ids
    ][:, tangential]


    high_tree = cKDTree(
        high_uv
    )

    d_lh, j_lh = high_tree.query(
        low_uv,
        k=1
    )


    low_tree = cKDTree(
        low_uv
    )

    d_hl, j_hl = low_tree.query(
        high_uv,
        k=1
    )


    mapped_high = high_ids[
        j_lh
    ]


    bijective = bool(
        len(low_ids)
        ==
        len(high_ids)
        ==
        len(
            np.unique(
                mapped_high
            )
        )
    )


    symmetric_count = 0

    for i, j in enumerate(
        j_lh
    ):

        if (
            j_hl[j]
            ==
            i
        ):

            symmetric_count += 1


    symmetric = bool(
        symmetric_count
        ==
        len(low_ids)
        ==
        len(high_ids)
    )


    max_mismatch = float(
        np.max(
            d_lh
        )
    )


    pairs = np.column_stack(
        [
            low_ids,
            mapped_high
        ]
    ).astype(
        np.int64
    )


    node_map = {
        int(a):
            int(b)

        for a, b
        in pairs
    }


    low_set = set(
        int(i)
        for i in low_ids
    )

    high_set = set(
        int(i)
        for i in high_ids
    )


    low_edges = set()

    high_edges = set()


    for u, v in free_edges:

        u = int(u)
        v = int(v)

        if (
            u in low_set
            and
            v in low_set
        ):

            low_edges.add(
                tuple(
                    sorted(
                        (u, v)
                    )
                )
            )


        if (
            u in high_set
            and
            v in high_set
        ):

            high_edges.add(
                tuple(
                    sorted(
                        (u, v)
                    )
                )
            )


    mapped_low_edges = set()

    map_complete = True


    for u, v in low_edges:

        if (
            u not in node_map
            or
            v not in node_map
        ):

            map_complete = False

            continue


        mapped_low_edges.add(
            tuple(
                sorted(
                    (
                        node_map[u],
                        node_map[v]
                    )
                )
            )
        )


    edge_topology_equal = bool(
        map_complete
        and
        mapped_low_edges
        ==
        high_edges
    )


    result.update(
        {
            "bijective":
                bijective,

            "symmetric":
                symmetric,

            "symmetric_matches":
                int(
                    symmetric_count
                ),

            "max_mismatch":
                max_mismatch,

            "low_free_edges":
                int(
                    len(low_edges)
                ),

            "high_free_edges":
                int(
                    len(high_edges)
                ),

            "edge_topology_equal":
                edge_topology_equal,

            "pairs":
                pairs,
        }
    )


    return result


# ============================================================
# DSU
# ============================================================

class DSU:

    def __init__(
        self,
        n
    ):

        self.parent = np.arange(
            n,
            dtype=np.int64
        )

        self.rank = np.zeros(
            n,
            dtype=np.int8
        )


    def find(
        self,
        x
    ):

        x = int(x)

        while (
            self.parent[x]
            !=
            x
        ):

            self.parent[x] = (
                self.parent[
                    self.parent[x]
                ]
            )

            x = int(
                self.parent[x]
            )

        return x


    def union(
        self,
        a,
        b
    ):

        ra = self.find(a)
        rb = self.find(b)

        if ra == rb:
            return

        if (
            self.rank[ra]
            <
            self.rank[rb]
        ):

            ra, rb = rb, ra

        self.parent[rb] = ra

        if (
            self.rank[ra]
            ==
            self.rank[rb]
        ):

            self.rank[ra] += 1


    def count_components(
        self
    ):

        roots = {
            self.find(i)
            for i in range(
                len(
                    self.parent
                )
            )
        }

        return len(roots)


# ============================================================
# OBJ
# ============================================================

def write_obj(
    path,
    nodes,
    triangles
):

    with path.open(
        "w",
        encoding="ascii"
    ) as f:

        for p in nodes:

            f.write(
                "v "
                f"{p[0]:.17g} "
                f"{p[1]:.17g} "
                f"{p[2]:.17g}\n"
            )


        for tri in triangles:

            f.write(
                "f "
                f"{tri[0] + 1} "
                f"{tri[1] + 1} "
                f"{tri[2] + 1}\n"
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
        "STEP 05 - BUILD & VALIDATE CANONICAL SHELL"
    )
    print(
        "================================================"
    )


    if not INPUT_CSV.exists():

        raise FileNotFoundError(
            INPUT_CSV
        )


    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    source_sha256 = (
        sha256_file(
            INPUT_CSV
        )
    )


    print()
    print(
        "Input:"
    )

    print(
        " ",
        INPUT_CSV
    )

    print(
        "SHA256 =",
        source_sha256
    )


    triangle_points, facet_ids, shifts = (
        read_triangle_csv(
            INPUT_CSV
        )
    )

    if len(triangle_points) == 0:
        raise RuntimeError(
            "Canonical triangle CSV contains zero triangles. "
            "Check the CGAL export file before continuing."
        )

    triangle_points = snap_cube_planes(
        triangle_points
    )


    print()
    print(
        "input triangles =",
        len(
            triangle_points
        )
    )

    print(
        "triangle vertex occurrences =",
        triangle_points.shape[0]
        *
        3
    )


    # ========================================================
    # Deduplicate
    # ========================================================

    nodes, triangles = (
        deduplicate_vertices(
            triangle_points
        )
    )


    print()
    print(
        "unique nodes =",
        len(nodes)
    )

    print(
        "triangles    =",
        len(triangles)
    )


    # ========================================================
    # Basic face validity
    # ========================================================

    repeated_node_triangle = np.any(
        np.column_stack(
            [
                triangles[:, 0]
                ==
                triangles[:, 1],

                triangles[:, 1]
                ==
                triangles[:, 2],

                triangles[:, 2]
                ==
                triangles[:, 0],
            ]
        ),
        axis=1
    )


    n_degenerate_connectivity = int(
        np.count_nonzero(
            repeated_node_triangle
        )
    )


    sorted_faces = np.sort(
        triangles,
        axis=1
    )


    _, face_counts = np.unique(
        sorted_faces,
        axis=0,
        return_counts=True
    )


    n_duplicate_face_groups = int(
        np.count_nonzero(
            face_counts > 1
        )
    )


    # ========================================================
    # Orient
    # ========================================================

    (
        triangles,
        orientation_conflicts,
        orientation_components,
    ) = orient_triangles(
        nodes,
        triangles
    )


    # ========================================================
    # Topology after orientation
    # ========================================================

    edge_map = build_edge_map(
        triangles
    )


    free_edges = np.asarray(
        [
            edge
            for edge, incidence
            in edge_map.items()
            if len(incidence) == 1
        ],
        dtype=np.int64
    )


    internal_edges = np.asarray(
        [
            edge
            for edge, incidence
            in edge_map.items()
            if len(incidence) == 2
        ],
        dtype=np.int64
    )


    nonmanifold_edges = np.asarray(
        [
            edge
            for edge, incidence
            in edge_map.items()
            if len(incidence) > 2
        ],
        dtype=np.int64
    )


    # ========================================================
    # Every free edge must lie on at least one cube face
    # ========================================================

    unintended_free_edges = []


    for u, v in free_edges:

        pu = nodes[u]
        pv = nodes[v]

        on_cube_face = False

        for axis in range(3):

            on_low = (
                abs(
                    pu[axis]
                )
                <= FACE_TOL
                and
                abs(
                    pv[axis]
                )
                <= FACE_TOL
            )

            on_high = (
                abs(
                    pu[axis] - L
                )
                <= FACE_TOL
                and
                abs(
                    pv[axis] - L
                )
                <= FACE_TOL
            )

            if (
                on_low
                or
                on_high
            ):

                on_cube_face = True

                break


        if not on_cube_face:

            unintended_free_edges.append(
                (
                    int(u),
                    int(v)
                )
            )


    # ========================================================
    # Periodicity
    # ========================================================

    periodic = {}

    pair_arrays = {}


    for name, axis in (
        ("X", 0),
        ("Y", 1),
        ("Z", 2),
    ):

        r = periodic_face_check(
            nodes,
            free_edges,
            axis
        )

        pair_arrays[name] = (
            r.pop(
                "pairs"
            )
        )

        periodic[name] = r


    # ========================================================
    # Connected components:
    #
    # cut mesh
    # glued periodic mesh
    # ========================================================

    cut_dsu = DSU(
        len(nodes)
    )


    for tri in triangles:

        cut_dsu.union(
            tri[0],
            tri[1]
        )

        cut_dsu.union(
            tri[1],
            tri[2]
        )

        cut_dsu.union(
            tri[2],
            tri[0]
        )


    cut_components = (
        cut_dsu.count_components()
    )


    glued_dsu = DSU(
        len(nodes)
    )


    for tri in triangles:

        glued_dsu.union(
            tri[0],
            tri[1]
        )

        glued_dsu.union(
            tri[1],
            tri[2]
        )

        glued_dsu.union(
            tri[2],
            tri[0]
        )


    for pairs in pair_arrays.values():

        for a, b in pairs:

            glued_dsu.union(
                a,
                b
            )


    glued_components = (
        glued_dsu.count_components()
    )


    # ========================================================
    # Quality
    # ========================================================

    q = triangle_quality(
        nodes,
        triangles
    )


    zero_area_triangles = int(
        np.count_nonzero(
            q["area"]
            <= AREA_TOL
        )
    )


    surface_area = float(
        np.sum(
            q["area"]
        )
    )


    # ========================================================
    # Implicit geometry error
    # ========================================================

    node_f = np.abs(
        implicit_function(
            nodes
        )
    )


    grad = implicit_gradient(
        nodes
    )


    grad_norm = np.linalg.norm(
        grad,
        axis=1
    )


    normal_error = np.divide(
        node_f,
        np.maximum(
            grad_norm,
            1.0e-14
        )
    )


    # ========================================================
    # Check oriented normals against grad f
    # ========================================================

    p = nodes[
        triangles
    ]


    normal = np.cross(
        p[:, 1] - p[:, 0],
        p[:, 2] - p[:, 0]
    )


    centroid = np.mean(
        p,
        axis=1
    )


    centroid_grad = (
        implicit_gradient(
            centroid
        )
    )


    normal_dot_grad = np.einsum(
        "ij,ij->i",
        normal,
        centroid_grad
    )


    positive_normal_fraction = float(
        np.mean(
            normal_dot_grad
            >
            0.0
        )
    )


    # ========================================================
    # Console report
    # ========================================================

    print()
    print(
        "================================================"
    )
    print(
        "TOPOLOGY"
    )
    print(
        "================================================"
    )

    print(
        "unique edges             =",
        len(
            edge_map
        )
    )

    print(
        "free edges               =",
        len(
            free_edges
        )
    )

    print(
        "internal edges           =",
        len(
            internal_edges
        )
    )

    print(
        "nonmanifold edges        =",
        len(
            nonmanifold_edges
        )
    )

    print(
        "unintended free edges    =",
        len(
            unintended_free_edges
        )
    )

    print(
        "duplicate face groups    =",
        n_duplicate_face_groups
    )

    print(
        "degenerate connectivity  =",
        n_degenerate_connectivity
    )

    print(
        "zero-area triangles      =",
        zero_area_triangles
    )

    print(
        "orientation conflicts    =",
        orientation_conflicts
    )

    print(
        "cut components           =",
        cut_components
    )

    print(
        "glued periodic components=",
        glued_components
    )


    print()
    print(
        "================================================"
    )
    print(
        "PERIODICITY"
    )
    print(
        "================================================"
    )


    for name in (
        "X",
        "Y",
        "Z"
    ):

        r = periodic[name]

        print()
        print(
            name
        )

        print(
            "  low/high nodes      =",
            r["low_nodes"],
            "/",
            r["high_nodes"]
        )

        print(
            "  max mismatch        =",
            r["max_mismatch"]
        )

        print(
            "  bijective           =",
            r["bijective"]
        )

        print(
            "  symmetric           =",
            r["symmetric"]
        )

        print(
            "  low/high free edges =",
            r.get(
                "low_free_edges"
            ),
            "/",
            r.get(
                "high_free_edges"
            )
        )

        print(
            "  edge topology equal =",
            r["edge_topology_equal"]
        )


    print()
    print(
        "================================================"
    )
    print(
        "QUALITY"
    )
    print(
        "================================================"
    )


    edge_stats = stats(
        q["edges"]
    )

    angle_stats = stats(
        q["min_angle"]
    )

    shape_stats = stats(
        q["shape_q"]
    )

    edge_ratio_stats = stats(
        q["edge_ratio"]
    )


    print(
        "surface area =",
        surface_area
    )

    print()
    print(
        "edge length:"
    )

    print(
        "  min   =",
        edge_stats["min"]
    )

    print(
        "  q01   =",
        edge_stats["q01"]
    )

    print(
        "  mean  =",
        edge_stats["mean"]
    )

    print(
        "  q95   =",
        edge_stats["q95"]
    )

    print(
        "  max   =",
        edge_stats["max"]
    )


    print()
    print(
        "minimum triangle angle:"
    )

    print(
        "  min   =",
        angle_stats["min"]
    )

    print(
        "  q01   =",
        angle_stats["q01"]
    )

    print(
        "  q05   =",
        angle_stats["q05"]
    )

    print(
        "  mean  =",
        angle_stats["mean"]
    )


    print()
    print(
        "shape q:"
    )

    print(
        "  min   =",
        shape_stats["min"]
    )

    print(
        "  q01   =",
        shape_stats["q01"]
    )

    print(
        "  mean  =",
        shape_stats["mean"]
    )


    print()
    print(
        "triangles angle < 5 deg  =",
        int(
            np.count_nonzero(
                q["min_angle"]
                <
                5.0
            )
        )
    )

    print(
        "triangles angle < 10 deg =",
        int(
            np.count_nonzero(
                q["min_angle"]
                <
                10.0
            )
        )
    )

    print(
        "triangles angle < 15 deg =",
        int(
            np.count_nonzero(
                q["min_angle"]
                <
                15.0
            )
        )
    )

    print(
        "triangles q < 0.2        =",
        int(
            np.count_nonzero(
                q["shape_q"]
                <
                0.2
            )
        )
    )


    print()
    print(
        "================================================"
    )
    print(
        "GEOMETRY"
    )
    print(
        "================================================"
    )

    print(
        "max node |f|        =",
        float(
            np.max(
                node_f
            )
        )
    )

    print(
        "q95 node |f|        =",
        float(
            np.percentile(
                node_f,
                95
            )
        )
    )

    print(
        "max normal error mm =",
        float(
            np.max(
                normal_error
            )
        )
    )

    print(
        "q95 normal error mm =",
        float(
            np.percentile(
                normal_error,
                95
            )
        )
    )

    print(
        "normal +grad fraction=",
        positive_normal_fraction
    )


    # ========================================================
    # Strict topology / periodic acceptance
    #
    # Mesh-size quality is NOT yet final acceptance because
    # this is still the coarse architecture probe.
    # ========================================================

    periodic_pass = True


    for name in (
        "X",
        "Y",
        "Z"
    ):

        r = periodic[name]

        periodic_pass = (
            periodic_pass

            and

            r["low_nodes"]
            ==
            r["high_nodes"]

            and

            r["bijective"]

            and

            r["symmetric"]

            and

            r["max_mismatch"]
            is not None

            and

            r["max_mismatch"]
            <= PAIR_TOL

            and

            r["edge_topology_equal"]
        )


    pass_status = bool(

        len(nodes)
        >
        0

        and

        len(triangles)
        >
        0

        and

        n_degenerate_connectivity
        ==
        0

        and

        n_duplicate_face_groups
        ==
        0

        and

        zero_area_triangles
        ==
        0

        and

        len(
            nonmanifold_edges
        )
        ==
        0

        and

        len(
            unintended_free_edges
        )
        ==
        0

        and

        orientation_conflicts
        ==
        0

        and

        periodic_pass

        and

        glued_components
        ==
        1
    )


    # ========================================================
    # Save NPZ
    # ========================================================

    np.savez_compressed(
        OUTPUT_NPZ,

        nodes=nodes,

        triangles=triangles,

        facet_ids=facet_ids,

        source_shifts=shifts,

        x_pairs=pair_arrays["X"],

        y_pairs=pair_arrays["Y"],

        z_pairs=pair_arrays["Z"],

        free_edges=free_edges,
    )


    write_obj(
        OUTPUT_OBJ,
        nodes,
        triangles
    )


    # ========================================================
    # JSON
    # ========================================================

    report = {

        "case_id":
            CASE_ID,

        "source_csv":
            str(
                INPUT_CSV
            ),

        "source_sha256":
            source_sha256,

        "cell_size_mm":
            L,

        "nodes":
            int(
                len(nodes)
            ),

        "triangles":
            int(
                len(triangles)
            ),

        "edges":
            int(
                len(edge_map)
            ),

        "free_edges":
            int(
                len(free_edges)
            ),

        "internal_edges":
            int(
                len(internal_edges)
            ),

        "nonmanifold_edges":
            int(
                len(
                    nonmanifold_edges
                )
            ),

        "unintended_free_edges":
            int(
                len(
                    unintended_free_edges
                )
            ),

        "duplicate_face_groups":
            n_duplicate_face_groups,

        "degenerate_connectivity":
            n_degenerate_connectivity,

        "zero_area_triangles":
            zero_area_triangles,

        "orientation_conflicts":
            int(
                orientation_conflicts
            ),

        "orientation_components":
            int(
                len(
                    orientation_components
                )
            ),

        "cut_components":
            int(
                cut_components
            ),

        "glued_periodic_components":
            int(
                glued_components
            ),

        "surface_area_mm2":
            surface_area,

        "periodicity":
            periodic,

        "quality":
            {

                "edge_length_mm":
                    edge_stats,

                "minimum_angle_deg":
                    angle_stats,

                "shape_q":
                    shape_stats,

                "edge_ratio":
                    edge_ratio_stats,

                "angle_lt_5_deg":
                    int(
                        np.count_nonzero(
                            q["min_angle"]
                            <
                            5.0
                        )
                    ),

                "angle_lt_10_deg":
                    int(
                        np.count_nonzero(
                            q["min_angle"]
                            <
                            10.0
                        )
                    ),

                "angle_lt_15_deg":
                    int(
                        np.count_nonzero(
                            q["min_angle"]
                            <
                            15.0
                        )
                    ),

                "shape_q_lt_02":
                    int(
                        np.count_nonzero(
                            q["shape_q"]
                            <
                            0.2
                        )
                    ),
            },

        "geometry":
            {

                "max_abs_f":
                    float(
                        np.max(
                            node_f
                        )
                    ),

                "q95_abs_f":
                    float(
                        np.percentile(
                            node_f,
                            95
                        )
                    ),

                "max_estimated_normal_error_mm":
                    float(
                        np.max(
                            normal_error
                        )
                    ),

                "q95_estimated_normal_error_mm":
                    float(
                        np.percentile(
                            normal_error,
                            95
                        )
                    ),

                "positive_gradient_normal_fraction":
                    positive_normal_fraction,
            },

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
        "Saved:"
    )

    print(
        " ",
        OUTPUT_NPZ
    )

    print(
        " ",
        OUTPUT_JSON
    )

    print(
        " ",
        OUTPUT_OBJ
    )


    print()
    print(
        "================================================"
    )

    if pass_status:

        print(
            "STEP 05 STATUS: PASS"
        )

    else:

        print(
            "STEP 05 STATUS: FAIL"
        )

    print(
        "================================================"
    )


    if not pass_status:

        raise SystemExit(3)


if __name__ == "__main__":

    main()
