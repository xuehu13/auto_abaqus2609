# -*- coding: utf-8 -*-
"""Step 00 — Fast sanity check before running the pipeline.

This does not create a mesh.  It verifies imports, reads config/case.json, evaluates
f and grad(f) at a few points, and reports the directories that will be used.
"""
import sys
import numpy as np
import scipy
import skimage
import sympy

from meshlib.config import CFG
from meshlib.surface import implicit_points, gradient_points, describe


def main():
    pts = np.array([[0.0, 0.0, 0.0], [0.25 * CFG.L] * 3], dtype=float)
    f = implicit_points(pts)
    g = gradient_points(pts)

    print("PYTHON ENVIRONMENT CHECK")
    print("python =", sys.version.split()[0])
    print("numpy  =", np.__version__)
    print("scipy  =", scipy.__version__)
    print("skimage=", skimage.__version__)
    print("sympy  =", sympy.__version__)
    print("case   =", CFG.case_id)
    print("surface=", describe())
    print("case dir=", CFG.case_dir)
    print("test f  =", f)
    print("test |g|=", np.linalg.norm(g, axis=-1))

    if not (np.all(np.isfinite(f)) and np.all(np.isfinite(g))):
        raise SystemExit("FAIL: surface expression produced non-finite values")

    print("PYTHON ENVIRONMENT STATUS: PASS")


if __name__ == "__main__":
    main()
