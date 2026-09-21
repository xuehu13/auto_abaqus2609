"""G/P/D/I-WP 2x2 周期 Sigmoid：独立几何预览与轻量体检。

依赖：numpy scipy scikit-image matplotlib
运行：pixi run -e geo -- python -B scripts/test_sigmoid_2x2_geometry.py --no-show
可调：修改下方参数；也可命令行 --kappa 5 --step 0.2 --no-show。
只测试零厚度曲面几何；不生成最终 Abaqus 网格，也不证明力学连接强度。
"""
from pathlib import Path
import argparse
from datetime import datetime
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from skimage.measure import marching_cubes
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# ========== 直接修改这些参数 ==========
L = 10.0                  # 单胞尺寸 (mm)，RVE 总尺寸为 (2L, 2L, L)
KAPPA = 7.0              # 周期 Sigmoid 无量纲陡峭参数；大 -> 过渡窄
STEP = 0.25              # 临时可视化采样间距 (mm)；0.2 更细但更慢
OFFSET = 0.2             # 原代码四种函数共同使用的常数 c
NORMALIZE_RMS = False    # True: 将四个完整函数按全域 RMS 归一化；默认忠实保留原代码系数
PREVIEW_FACES = 14000    # 三维预览最多绘制多少个三角形，防止 Matplotlib 卡顿
SHOW_WINDOW = True       # 弹出可旋转的 Matplotlib 窗口；无界面环境可设 False
OUT_DIR = (Path(__file__).resolve().parents[1] / 'work'
           / f'sigmoid_preview_{datetime.now():%Y%m%dT%H%M%S%f}')
# =====================================


def tpms_fields(x, y, z, length, offset):
    """原 generate_2x2_heterogeneous_rve.py 中的四种隐式函数，向量化实现。"""
    w = 2.0 * np.pi / length
    X, Y, Z = w*x, w*y, w*z
    sx, sy, sz = np.sin(X), np.sin(Y), np.sin(Z)
    cx, cy, cz = np.cos(X), np.cos(Y), np.cos(Z)
    g = sx*cy + sy*cz + sz*cx + offset
    p = 0.75*(cx + cy + cz) + offset
    d = 1.2*(sx*sy*sz + sx*cy*cz + cx*sy*cz + cx*cy*sz) + offset
    iwp = 0.5*(2*(cx*cy + cy*cz + cz*cx)
               - (np.cos(2*X) + np.cos(2*Y) + np.cos(2*Z))) + offset
    return g, p, d, iwp


def sigmoid(t):
    return 1.0 / (1.0 + np.exp(-np.clip(t, -80.0, 80.0)))


def field(x, y, z, scales):
    """单一三维隐式场；对数组或标量坐标均适用。"""
    p = sigmoid(KAPPA * np.sin(np.pi*(x-L)/L))
    q = sigmoid(KAPPA * np.sin(np.pi*(y-L)/L))
    g, sp, d, iwp = tpms_fields(x, y, z, L, OFFSET)
    g, sp, d, iwp = (f/s for f, s in zip((g, sp, d, iwp), scales))
    return ((1-p)*(1-q)*g + p*(1-q)*sp
            + (1-p)*q*d + p*q*iwp)


def periodic_pairs(vertices, axis, domain, tol):
    """仅用于诊断周期截面配对、计算周期拓扑连通性。"""
    transverse = [a for a in range(3) if a != axis]
    left = np.flatnonzero(abs(vertices[:, axis]) < tol)
    right = np.flatnonzero(abs(vertices[:, axis]-domain[axis]) < tol)
    quant = tol
    key = lambda v: tuple(np.rint(v[transverse]/quant).astype(np.int64))
    lookup = {key(vertices[i]): i for i in right}
    pairs = [(i, lookup[key(vertices[i])]) for i in left
             if key(vertices[i]) in lookup]
    return pairs, len(left), len(right)


def diagnose(vol, vertices, faces, steps, scales):
    domain = np.array((2*L, 2*L, L))
    # 场值周期检查：直接对采样数组首尾比较，不依赖网格节点匹配。
    xerr = float(np.max(abs(vol[0, :, :] - vol[-1, :, :])))
    yerr = float(np.max(abs(vol[:, 0, :] - vol[:, -1, :])))
    # 表面连通分量：报告普通盒子内与 XY 周期拼接后的两种结果。
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]],
                            faces[:, [2, 0]]], axis=0).astype(np.int32)
    e = np.sort(edges, axis=1)
    unique_edges, counts = np.unique(e, axis=0, return_counts=True)
    boundary = unique_edges[counts == 1]
    midpoint = vertices[boundary].mean(axis=1) if len(boundary) else np.empty((0, 3))
    on_cut = (np.any((abs(midpoint) < 1e-4) |
                     (abs(midpoint-domain) < 1e-4), axis=1)
              if len(midpoint) else np.array([], dtype=bool))
    interior_open = int(np.sum(~on_cut))
    nonmanifold = int(np.sum(counts > 2))

    def components(extra):
        pairs = np.concatenate((edges, extra), axis=0) if len(extra) else edges
        matrix = coo_matrix((np.ones(2*len(pairs), dtype=np.int8),
                             (np.r_[pairs[:, 0], pairs[:, 1]],
                              np.r_[pairs[:, 1], pairs[:, 0]])),
                            shape=(len(vertices), len(vertices))).tocsr()
        n, labels = connected_components(matrix, directed=False)
        sizes = np.bincount(labels)
        return int(n), sizes

    n_box, sizes_box = components(np.empty((0, 2), dtype=np.int32))
    tol = max(1e-6, L*1e-7)  # 仅识别精确落在切面上的顶点，勿把邻近点算进来
    pair_x, xl, xr = periodic_pairs(vertices, 0, domain, tol)
    pair_y, yl, yr = periodic_pairs(vertices, 1, domain, tol)
    joined = np.asarray(pair_x + pair_y, dtype=np.int32).reshape(-1, 2)
    n_periodic, sizes_periodic = components(joined)

    # 隐式场梯度：采样网格的有限差分 + 顶点三线性插值；只是奇异风险筛查。
    grads = np.gradient(vol, *steps, edge_order=2)
    coords = (vertices/np.asarray(steps)).T
    gradient = np.column_stack([map_coordinates(g, coords, order=1,
                                                mode='nearest') for g in grads])
    grad_norm = np.linalg.norm(gradient, axis=1)
    med = float(np.median(grad_norm))
    small_grad = int(np.count_nonzero(grad_norm < 0.01*med)) if med else len(vertices)

    print('\n========== 几何体检（有限采样下的初筛） ==========')
    print(f'RVE={domain.tolist()} mm, κ={KAPPA:g}, 实际步长={steps}')
    print(f'四种隐式场缩放因子 [G,P,D,IWP]: {np.round(scales, 4).tolist()}')
    print(f'场值周期误差: X={xerr:.3e}, Y={yerr:.3e}')
    print(f'提取曲面: {len(vertices)} 顶点, {len(faces)} 三角形（临时预览面）')
    print(f'盒内连通分量={n_box}, XY周期合并后={n_periodic}; '
          f'周期最大分量顶点占比={sizes_periodic.max()/len(vertices):.2%}')
    print(f'周期截面节点配对: X {len(pair_x)}/{xl}/{xr}, Y {len(pair_y)}/{yl}/{yr} '
          '(格式: 匹配数/左节点数/右节点数)')
    print(f'非流形边(关联面>2)={nonmanifold}; 非外部截断面的开放边={interior_open}')
    print(f'曲面顶点 |grad Psi|: 最小={grad_norm.min():.3e}, 中位={med:.3e}, '
          f'低于中位数1%的顶点={small_grad}')
    if n_periodic > 1:
        print('提示: 存在多个周期连通分量，需观察是否为非预期孤立面片；不能自动等同于失败。')
    if small_grad:
        print('提示: 低梯度区域值得局部放大；此采样筛查不能严格判定数学奇点。')
    if interior_open or nonmanifold or xerr > 1e-6 or yerr > 1e-6:
        print('警示: 出现潜在几何/周期问题，请先检查，不宜直接进入 Abaqus。')
    else:
        print('初筛未见明显周期场值或网格拓扑错误；仍需目视检查细颈、自交与连接合理性。')
    print('本测试不检验有限壳厚自交或连接强度；盒内多个分量也不一定为错误。')


def visualize(vol, vertices, faces, axes, out):
    fig = plt.figure(figsize=(14, 9), constrained_layout=True)
    ax = fig.add_subplot(2, 2, 1, projection='3d')
    rng = np.random.default_rng(20260919)
    chosen = (rng.choice(len(faces), PREVIEW_FACES, replace=False)
              if len(faces) > PREVIEW_FACES else np.arange(len(faces)))
    tri = vertices[faces[chosen]]
    centers = tri.mean(axis=1)
    # 按象限染色只是为了看出四个胞元所在区域，并非真实材料/应力分布。
    ci = (centers[:, 0] >= L).astype(int) + 2*(centers[:, 1] >= L).astype(int)
    palette = np.array([[0.34, 0.59, 0.78, 0.88], [0.82, 0.54, 0.35, 0.88],
                        [0.38, 0.65, 0.49, 0.88], [0.64, 0.50, 0.72, 0.88]])
    surface = Poly3DCollection(tri, linewidths=0, facecolors=palette[ci])
    ax.add_collection3d(surface)
    ax.set(xlim=(0, 2*L), ylim=(0, 2*L), zlim=(0, L),
           xlabel='X (mm)', ylabel='Y (mm)', zlabel='Z (mm)',
           title='3D surface (drag to rotate)')
    ax.set_box_aspect((2, 2, 1)); ax.view_init(elev=26, azim=-65)

    xs, ys, zs = axes
    slices = [
        (fig.add_subplot(2, 2, 2), xs, ys, vol[:, :, len(zs)//2].T,
         f'XY slice: z={zs[len(zs)//2]:g} mm', 'X', 'Y'),
        (fig.add_subplot(2, 2, 3), ys, zs, vol[len(xs)//2, :, :].T,
         f'YZ slice: x={xs[len(xs)//2]:g} mm (center interface)', 'Y', 'Z'),
        (fig.add_subplot(2, 2, 4), xs, zs, vol[:, len(ys)//2, :].T,
         f'XZ slice: y={ys[len(ys)//2]:g} mm (center interface)', 'X', 'Z'),
    ]
    for a, xx, yy, vals, title, xlabel, ylabel in slices:
        if vals.min() <= 0 <= vals.max():
            a.contour(xx, yy, vals, levels=[0], colors='black', linewidths=1.3)
        a.set(xlim=(xx[0], xx[-1]), ylim=(yy[0], yy[-1]), xlabel=xlabel+' (mm)',
              ylabel=ylabel+' (mm)', title=title)
        a.set_aspect('equal', adjustable='box'); a.grid(alpha=0.16)
    fig.suptitle(f'2x2 Sigmoid TPMS | kappa={KAPPA:g}, step={STEP:g} mm', fontsize=14)
    fig.savefig(out, dpi=160)
    print(f'已保存预览图: {out}')
    if SHOW_WINDOW:
        plt.show()
    plt.close(fig)


def main():
    global KAPPA, STEP, OFFSET, NORMALIZE_RMS, SHOW_WINDOW
    # Windows/Pixi：先加载 NumPy linalg，避免 SciPy 之后的 Matplotlib 3D DLL 加载失败。
    np.linalg.inv(np.eye(2))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kappa', type=float, default=KAPPA)
    parser.add_argument('--step', type=float, default=STEP)
    parser.add_argument('--offset', type=float, default=OFFSET)
    parser.add_argument('--normalize', action='store_true', help='按各隐式函数 RMS 归一化')
    parser.add_argument('--no-show', action='store_true', help='只保存 PNG，不弹窗口')
    args = parser.parse_args()
    KAPPA, STEP, OFFSET = args.kappa, args.step, args.offset
    NORMALIZE_RMS = NORMALIZE_RMS or args.normalize
    SHOW_WINDOW = SHOW_WINDOW and not args.no_show
    if not (KAPPA > 0 and 0 < STEP <= L/2):
        parser.error('需要 kappa>0 且 0<step<=L/2')
    OUT_DIR.mkdir(parents=True, exist_ok=False)
    n = max(4, int(round(L/STEP)))
    xs = np.linspace(0, 2*L, 2*n+1)
    ys = np.linspace(0, 2*L, 2*n+1)
    zs = np.linspace(0, L, n+1)
    steps = (float(xs[1]-xs[0]), float(ys[1]-ys[0]), float(zs[1]-zs[0]))
    x, y, z = np.meshgrid(xs, ys, zs, indexing='ij', sparse=True)
    original = tpms_fields(x, y, z, L, OFFSET)
    scales = np.array([float(np.sqrt(np.mean(np.broadcast_to(f, (len(xs), len(ys), len(zs)))**2)))
                       for f in original]) if NORMALIZE_RMS else np.ones(4)
    vol = field(x, y, z, scales).astype(np.float32)
    del original
    vertices, faces, _, _ = marching_cubes(vol, level=0, spacing=steps)
    diagnose(vol, vertices, faces, steps, scales)
    img = OUT_DIR / f'sigmoid_k{KAPPA:g}_h{steps[0]:g}.png'
    visualize(vol, vertices, faces, (xs, ys, zs), img)


if __name__ == '__main__':
    main()
