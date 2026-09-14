"""Boundary-plane bit flags shared by topology/boundary stages."""
import numpy as np

X0 = np.uint8(1 << 0)
XL = np.uint8(1 << 1)
Y0 = np.uint8(1 << 2)
YL = np.uint8(1 << 3)
Z0 = np.uint8(1 << 4)
ZL = np.uint8(1 << 5)

FLAG_INFO = [("X0", X0), ("XL", XL), ("Y0", Y0), ("YL", YL), ("Z0", Z0), ("ZL", ZL)]
MASTER_FACES = [("X0", X0), ("Y0", Y0), ("Z0", Z0)]
MASTER_FACE_NAMES = ["X0", "Y0", "Z0"]
MASTER_FIXED_AXIS = [0, 1, 2]
