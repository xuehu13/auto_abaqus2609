# Fig.1 clean-v1.0 regression reference

These values are **regression references for the validated clean pipeline**, not universal acceptance thresholds for every future surface.

Validated on 2026-09-12 with the refactored production pipeline:

- Python 3.10.21
- NumPy 2.2.6
- SciPy 1.15.3
- scikit-image 0.25.2
- SymPy 1.14.0
- MSVC 19.50.35720.0
- CGAL 6.0.1 environment
- Abaqus 2026 Standard Data Check

## Step 00 — environment / expression

- Case: `fig1`
- Cell size: 10 mm
- Expression: `2.3*cos(X)*sin(Z) + 1.9*cos(Y)*cos(Z) - 0.6`
- Status: PASS

## Step 01 — periodic topology scaffold

- Marching-Cubes vertices: 45,788
- Marching-Cubes triangles: 89,984
- Periodic node pairs: X 292, Y 314, Z 202
- Unique edges: 135,776
- Free edges: 1,600
- Internal cracks: 0
- Non-manifold edges: 0
- Opposite-face edge topology: X/Y/Z all identical
- Periodic equivalence classes: 44,984
- Cut-cell components: 1
- Periodically glued components: 1
- Surface area: 304.4657897949219 mm^2
- Status: PASS

## Step 02 — master boundary extraction

- X0 curves: 4
- Y0 curves: 2
- Z0 curves: 2
- Total master curves: 8
- Shared endpoint periodic classes: 0, 4, 107, 472
- Status: PASS

## Step 03 — standardized master boundaries

- Master curves: 8
- Total standardized points: 381
- Segment minimum: 0.16757288158271053 mm
- Segment mean: 0.17783984235070335 mm
- Segment maximum: 0.17998120598355918 mm
- Segments < 0.05 mm: 0
- Segments < 0.10 mm: 0
- Segments > 0.20 mm: 0
- Maximum |f|: 8.938738638164523e-12
- Endpoint periodic mismatch: 0
- Status: PASS

## Step 04 — Periodic_3 feature export

- Master feature curves: 8
- X0/Y0/Z0: 4/2/2
- Feature points: 381
- Maximum feature chord normal error: 0.0017215288268260308 mm
- Maximum endpoint-class mismatch: 0
- Status: PASS

## C++ CGAL Periodic_3 mesher — clean v1.0

- Runtime expression was read from `cgal_case.txt`
- Periodic vertices: 13,486
- Surface facets: 18,164
- Domain cells: 53,201
- Protected feature edges: 405
- Corners: 4
- Surface facets iterated: 18,164
- Facets shifted by one or more periods: 120
- Facets requiring geometric clipping: 0
- Maximum physical surface edge: 0.34988197409894994 mm
- Maximum triangle axis span: 0.33958186078472963 mm
- Same input was run twice and the canonical-triangle CSV SHA256 was identical
- Canonical triangle CSV SHA256: `61e8f550d6c3d74ba1122e985b0daf0c1ce7ed7617cdf0662f293b26a43a4c3f`
- Status: PASS

## Step 05 — final canonical shell validator

- Nodes: 9,483
- Triangles: 18,164
- Unique edges: 27,651
- Free edges: 810
- Internal edges: 26,841
- Non-manifold edges: 0
- Unintended free edges: 0
- Duplicate face groups: 0
- Degenerate connectivity: 0
- Zero-area triangles: 0
- Orientation conflicts: 0
- Cut components: 1
- Periodically glued components: 1

Periodicity:

- X boundary nodes: 141 / 141; max mismatch 5.551115123125783e-17 mm
- Y boundary nodes: 148 / 148; max mismatch 0
- Z boundary nodes: 124 / 124; max mismatch 0
- X/Y/Z node matching is bijective and symmetric
- X/Y/Z free-edge topology matches exactly

Quality:

- Surface area: 304.64827090489996 mm^2
- Minimum edge: 0.08219874121974885 mm
- Mean edge: 0.2018165715632065 mm
- 95% edge quantile: 0.26892352712065026 mm
- Maximum edge: 0.34988197409894994 mm
- Minimum triangle angle: 14.419297027070776 deg
- Mean minimum angle: 47.017817217158516 deg
- Minimum shape quality q: 0.37424315023415416
- Mean shape quality q: 0.9260424110589184
- Triangles with minimum angle < 10 deg: 0
- Triangles with q < 0.2: 0

Geometry:

- Maximum node |f|: 0.00756612140997992
- Maximum estimated normal error: 0.004279062903792588 mm
- 95% estimated normal error: 0.003181971976152623 mm
- Fraction of triangle normals aligned with +grad(f): 1.0
- Status: PASS

## Step 06 — Abaqus S3R mesh-check export

- The Step-05 shell was exported as S3R shell elements.
- X0/XL, Y0/YL and Z0/ZL node sets and exact periodic node-pair CSV were exported.
- Placeholder elastic material and shell thickness are used only to make the mesh-only Data Check model complete.
- No physical PBC equations, plates, contact, real material law or compression loading are included in this step.
- Status: PASS

## Abaqus 2026 Data Check + Step 07

- Abaqus job: `fig1_meshcheck`
- Abaqus/Standard Data Check completed normally.
- `.dat`: present
- `.msg`: present
- `.sta`: absent, which is allowed for a pure Data Check run
- ERROR: 0
- WARNING: 0
- DISTORT: 0
- ASPECT RATIO: 0
- SHELL NORMAL / ErrElemShellNormal: 0
- NEGATIVE AREA: 0
- ZERO AREA: 0
- Fatal count: 0
- Status: PASS

## Important interpretation

The old exploratory pipeline produced a closely related S15 mesh with 9,482 nodes and 18,162 triangles. The clean v1.0 runtime-expression implementation produces 9,483 nodes and 18,164 triangles. The new clean result is the authoritative regression baseline for this source tree. The tiny topological-count difference is acceptable because the geometry, periodicity, element quality, determinism and Abaqus Data Check all pass.
