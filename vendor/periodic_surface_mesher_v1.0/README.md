# 周期隐式曲面 → CGAL Periodic_3 → Abaqus S3R 自动网格：精简生产版

这是对原 `pipeline_v2` 的**生产路线重构版**。目标不是保存研发过程，而是只留下已经验证成功、后续真正会继续使用的代码。

原目录中用于试错/验证路线的 Stage 14–23、普通 CGAL surface remesh、Gmsh/segment constraint、双次 SHA 比较、S16/S17/S18 参数扫描等代码都已从生产目录移除。它们有研究记录价值，但不应再混入日常批处理代码。

当前生产主线只有：

```text
隐式方程
  ↓
01 周期拓扑骨架（Marching Cubes 仅用于找拓扑）
  ↓
02 提取 X0/Y0/Z0 三个 master face 上的切割曲线
  ↓
03 曲线等弧长重采样 + 投影回 f=0 + 精确端点
  ↓
04 输出 CGAL master features + CGAL 运行配置
  ↓
C++ CGAL Periodic_3 生成严格周期三角壳网格
  ↓
05 Python 严格验证最终 shell
  ↓
06 导出 Abaqus S3R mesh-only Data Check INP
  ↓
Abaqus datacheck
  ↓
07 自动解析 dat/msg → PASS / FAIL
```

---

## 1. 为什么这样重构

原来的 20 多个文件是“探索过程”的真实记录：里面既有成功路线，也有为了排除方案而写的 probe、diagnose、sweep、segment test。继续沿用那套文件名会有三个问题：

1. 新接手的人很难分清“哪些必须跑、哪些永远不用再跑”。
2. Fig.1 方程、`L=10`、路径和网格参数散落在多个 Python/C++ 文件里，换曲面容易漏改。
3. 中间实验文件和 build/输出文件很多，不适合 Git 管理和后续批量化。

这版做了以下重构：

- 只保留最终成功路线。
- 所有 Python 路径和参数统一从 `config/case.json` 读取。
- Python 的隐式函数与解析梯度统一由 `meshlib/surface.py` 根据同一条公式自动生成。
- C++ CGAL 程序不再把 Fig.1 方程写死在源码里，而是运行时读取 `cgal_case.txt` 中的公式；因此换曲面不需要重新改 C++ 源码。
- 输出目录统一为 `cases/<case_id>/...`。
- 每个主脚本都加了“目的 / 输入 / 输出 / 停止条件”的顶部说明。
- 提供 PowerShell/CMD 辅助脚本，减少新手手输命令。

---

# 2. 文件夹结构

```text
periodic_surface_mesher_clean/
│
├─ config/
│  └─ case.json                      ← 用户最重要的配置文件
│
├─ meshlib/
│  ├─ config.py                      ← 读取配置、统一路径
│  ├─ surface.py                     ← 由公式自动生成 f 和解析梯度
│  └─ flags.py                       ← X0/XL/Y0/YL/Z0/ZL 标志
│
├─ 01_build_periodic_topology.py     ← 周期拓扑骨架
├─ 02_extract_master_boundaries.py   ← 提取 master 切割曲线
├─ 03_standardize_master_boundaries.py ← 标准化/投影曲线
├─ 04_export_cgal_input.py           ← 输出 CGAL feature 和运行配置
│
├─ cgal_mesher/
│  ├─ CMakeLists.txt
│  ├─ expression_parser.hpp          ← C++ 运行时公式解析器
│  └─ main.cpp                       ← 最终 CGAL Periodic_3 mesher
│
├─ 05_validate_shell.py              ← 最终 shell 严格验证
├─ 06_export_abaqus_meshcheck.py     ← 导出 Abaqus S3R Data Check INP
├─ 07_validate_abaqus_datacheck.py   ← 自动解析 Abaqus dat/msg
│
├─ tools/
│  ├─ run_preprocess.ps1
│  ├─ build_cgal.cmd
│  ├─ run_cgal.cmd
│  ├─ run_postprocess.ps1
│  ├─ run_abaqus_datacheck.cmd
│  └─ run_datacheck_validator.ps1
│
├─ environment_geo.yml
├─ environment_cgal.yml
├─ REFERENCE_RESULTS.md
└─ .gitignore
```

`cases/` 是运行后自动生成的结果目录，不属于核心源码。

---

# 3. 三种终端不要混用

本项目最容易让新手混乱的地方不是算法，而是环境。

## 3.1 VS Code PowerShell：跑 Python

用于步骤 01、02、03、04、05、06、07。

典型提示符：

```text
(diffumeta_geo) PS F:\...\periodic_surface_mesher_clean>
```

这里使用 `diffumeta_geo`。

## 3.2 x64 Native Tools Command Prompt：编译/运行 CGAL C++

必须从 Windows 开始菜单打开：

```text
x64 Native Tools Command Prompt for VS
```

然后激活：

```cmd
F:\Anaconda\Scripts\activate
conda activate diffumeta_cgal
```

检查：

```cmd
where cl
```

应能找到 `Hostx64\x64\cl.exe`。

这里使用 `diffumeta_cgal`。

## 3.3 普通 CMD：运行 Abaqus

检查：

```cmd
abaqus information=release
```

只要能显示 Abaqus 版本，就可以运行 Data Check。

---

# 4. 第一次安装环境

如果你已经有原来的 `diffumeta_geo` 和 `diffumeta_cgal`，可以继续使用；只需要确认 `diffumeta_geo` 里新增了 `sympy`。

## 4.1 Python 几何环境

在 Anaconda Prompt / PowerShell：

```powershell
cd <本项目目录>
conda env create -f environment_geo.yml
conda activate diffumeta_geo
```

如果环境已经存在：

```powershell
conda activate diffumeta_geo
conda install -c conda-forge sympy
```

检查：

```powershell
python -c "import numpy, scipy, skimage, sympy; print('OK')"
```

## 4.2 CGAL 环境

在 x64 Native Tools Command Prompt：

```cmd
F:\Anaconda\Scripts\activate
conda env create -f environment_cgal.yml
conda activate diffumeta_cgal
where cl
cmake --version
ninja --version
```

当前验证路线使用 CGAL 6.0.1。

---

# 5. 新曲面首先只改 `config/case.json`

这是整个重构最重要的变化。

Fig.1 当前配置：

```json
{
  "case_id": "fig1",
  "cell_size_mm": 10.0,
  "surface_expression": "2.3*cos(X)*sin(Z) + 1.9*cos(Y)*cos(Z) - 0.6"
}
```

这里的 `X/Y/Z` **不是毫米坐标**，而是周期角坐标：

```text
X = 2*pi*x/L
Y = 2*pi*y/L
Z = 2*pi*z/L
```

所以一个单胞 `[0,L]^3` 正好对应 `[0,2π]^3`。

支持的公式语法：

```text
+  -  *  /  ^
()
sin() cos() tan()
exp() sqrt() abs()
pi
X Y Z
```

例如：

```text
2.3*cos(X)*sin(Z) + 1.9*cos(Y)*cos(Z) - 0.6
```

Python 端用 SymPy 自动求导，因此不再需要手工在四个文件里重复修改 `df/dx,df/dy,df/dz`。

> 重要：`surface_expression` 表示 `f(X,Y,Z)`，最终曲面是 `f=iso_level`。目前生产流程默认 `iso_level=0`。

---

# 6. 配置文件中的主要参数

## 6.1 `topology_sampling_intervals`

当前：

```text
100
```

对于 `L=10 mm`，意味着拓扑采样间隔：

```text
10 / 100 = 0.1 mm
```

这个 Marching Cubes 只用于获得拓扑与边界曲线，不是最终 Abaqus 网格。

## 6.2 `boundary_target_spacing_mm`

当前：

```text
0.18 mm
```

控制 master seam 曲线上的目标最大间距。

## 6.3 CGAL 参数

当前验证后的 Fig.1 生产候选：

```text
edge_size       = 0.18 mm
facet_angle     = 25 deg
facet_size      = 0.15 mm
facet_distance  = 0.03 mm
cell_size       = 0.50 mm
random_seed     = 20260911
```

`facet_size=0.15` 对 Fig.1 最终得到约 `0.2018 mm` 的平均物理边长。

这些不是对所有未来曲面都永远正确的“物理定律”。如果 `L`、曲面频率或几何尺度发生显著改变，需要重新做网格收敛/鲁棒性确认。

---

# 7. Step 01：建立周期拓扑骨架

界面：VS Code PowerShell，`diffumeta_geo`。

```powershell
conda activate diffumeta_geo
cd <本项目目录>
python .\01_build_periodic_topology.py
```

## 目的

1. 在 `(n+1)^3` 周期标量网格上采样 `f`。
2. 最后一个采样平面不是重新计算，而是直接复制第一个平面，保证标量场逐位周期一致。
3. 使用 Marching Cubes 提取一个**临时拓扑三角面**。
4. 建立 X/Y/Z 对面节点配对。
5. 检查自由边、内部裂纹、非流形边。
6. 检查对面边拓扑是否完全相同。
7. 将周期对面节点用并查集粘合，确认周期空间中仍然连通。

## 为什么 Marching Cubes 不能直接给 Abaqus

它容易产生大量极小边和尖瘦三角形。我们最早的 raw MC 曾出现数千个 distorted elements，并触发 Abaqus shell-normal 错误。因此它现在只负责“找拓扑”，不负责最终网格质量。

## Fig.1 参考结果

```text
vertices  = 45788
triangles = 89984
X pairs   = 292
Y pairs   = 314
Z pairs   = 202
internal cracks   = 0
nonmanifold edges = 0
glued components  = 1
TOPOLOGY STATUS: PASS
```

输出：

```text
cases/fig1/periodic_topology.npz
cases/fig1/topology_report.json
```

任何 `internal cracks > 0`、`nonmanifold > 0` 或周期边拓扑不一致，都应直接停止该样本。

---

# 8. Step 02：提取 master boundary curves

```powershell
python .\02_extract_master_boundaries.py
```

## 目的

最终 Periodic_3 不应该把 X0/XL、Y0/YL、Z0/ZL 六组边界都作为独立 constraint 输入，否则可能破坏 flat-torus 的周期关系。

所以我们只保留：

```text
X0
Y0
Z0
```

这三张 master face 上的交线。

脚本会：

- 从 topology mesh 的自由边中取出每张 master face 上的边；
- 建图；
- 分连通分量；
- 将每个分量排序成一条有序 polyline；
- 记录曲线端点所对应的周期 equivalence class。

Fig.1：

```text
X0: 4 curves
Y0: 2 curves
Z0: 2 curves
总计: 8 curves
MASTER BOUNDARY STATUS: PASS
```

输出：

```text
master_boundary_curves.npz
master_boundary_report.json
```

---

# 9. Step 03：标准化 master curves

```powershell
python .\03_standardize_master_boundaries.py
```

## 为什么要做

Step 02 的曲线仍继承 Marching-Cubes 的不规则离散。若原样交给 CGAL，可能把糟糕的小边带进 feature。

Step 03 做四件事情：

1. 对 polyline 按弧长重新采样。
2. 让目标段长约 `0.18 mm`。
3. 对落在 cube edge 上的端点，用一维求根把它精确放回 `f=0`。
4. 对内部 feature 点做面内 Newton 投影，使其回到隐式曲面。

Fig.1：

```text
8 curves
381 points
segment min  ≈ 0.16757 mm
segment max  ≈ 0.17998 mm
max |f|      ≈ 9e-12
endpoint periodic mismatch = 0
STANDARD BOUNDARY STATUS: PASS
```

这一步是把“不规则 MC 边界”变成“可保护、可周期复制的高质量 seam”。

---

# 10. Step 04：输出 CGAL 输入

```powershell
python .\04_export_cgal_input.py
```

输出三个文件：

```text
cases/<case>/cgal_input/periodic3_master_features.txt
cases/<case>/cgal_input/periodic3_master_features_report.json
cases/<case>/cgal_input/cgal_case.txt
```

其中：

- `periodic3_master_features.txt`：8 条 master seam polyline。
- `cgal_case.txt`：C++ 运行时使用的 `L`、曲面公式、CGAL 参数、随机种子。

Fig.1 应看到：

```text
master feature curves = 8
X0/Y0/Z0 = 4/2/2
max feature chord error ≈ 0.00172 mm
max endpoint class mismatch = 0
STATUS: PASS
```

---

# 11. 第一次只需要编译一次 CGAL C++

界面：x64 Native Tools Command Prompt。

```cmd
F:\Anaconda\Scripts\activate
conda activate diffumeta_cgal
cd /d <本项目目录>
tools\build_cgal.cmd
```

它会自动执行：

```cmd
cmake -S cgal_mesher -B cgal_mesher\build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build cgal_mesher\build
```

成功后得到：

```text
cgal_mesher/build/periodic_surface_mesher.exe
```

## 和旧代码最大的区别

旧 Stage 25 的 C++ 里把 Fig.1 方程写死了，所以换方程要改 C++ 再编译。

现在 `expression_parser.hpp` 在运行时解析 `cgal_case.txt` 中的公式，因此：

```text
换方程 → 改 case.json → 跑 Step 01–04 → 直接复用同一个 exe
```

不需要为每一个曲面重新编译 C++。

---

# 12. 运行 CGAL Periodic_3

还是 x64 Native Tools：

```cmd
cd /d <本项目目录>
tools\run_cgal.cmd
```

等价于：

```cmd
periodic_surface_mesher.exe ^
  cases\fig1\cgal_input\cgal_case.txt ^
  cases\fig1\cgal_input\periodic3_master_features.txt ^
  cases\fig1\cgal_output\fig1_mesh
```

## CGAL 做什么

- 建立 flat-torus 周期域 `[0,L]^3`；
- 把 8 条 master seam 加为 artificial protected features；
- `features().manifold().no_perturb().no_exude()`；
- 生成 Periodic_3 tetrahedral background mesh；
- 只提取其中的零水平 surface facets；
- 对跨周期边界的三角形使用**一个整数周期向量整体平移**到 canonical cell；
- 不进行任意三角形-plane clipping。

这是我们整个研究阶段最关键的架构结论。

## 必须看到

```text
facets requiring clipping = 0
PERIODIC SURFACE MESHER STATUS: PASS
```

核心输出：

```text
cases/<case>/cgal_output/<case>_mesh_canonical_triangles.csv
```

另外 `.mesh` 1-copy/8-copy 文件仅用于调试/可视化，可在批量生产时选择不长期保存。

---

# 13. Step 05：最终 shell 严格验收

回 VS Code PowerShell：

```powershell
conda activate diffumeta_geo
cd <本项目目录>
python .\05_validate_shell.py
```

这不是“简单看一下网格”，而是生产流程的硬门槛。

它检查：

### 节点/单元

- 三角形 CSV 是否为空；
- 坐标去重；
- x=0 和 x=L **绝不能因为周期性而合并为同一个 Abaqus 节点**；
- 重复三角形；
- 退化 connectivity；
- zero-area triangle。

### 拓扑

- free edges；
- internal free edges；
- non-manifold edges；
- cut-cell connected components；
- 周期粘合后的 connected components。

### 周期性

对 X/Y/Z 三组面分别检查：

- low/high 节点数相同；
- 坐标映射双射；
- 最近邻映射对称；
- mismatch 小于阈值；
- free-edge topology 完全一致。

### 单元质量

- min/mean/max edge；
- minimum angle；
- shape quality `q`；
- edge ratio；
- `<5° / <10° / <15°` 的三角形数量；
- `q<0.2` 数量。

### 几何误差

- `max |f(node)|`；
- `|f|/|grad f|` 估算的法向几何误差；
- 每个三角形法向是否与解析 `grad f` 一致。

Fig.1 S15 参考：见 `REFERENCE_RESULTS.md`。

只有：

```text
STEP 05 STATUS: PASS
```

才允许进入 Abaqus。

---

# 14. Step 06：生成 Abaqus S3R mesh-only 检查模型

```powershell
python .\06_export_abaqus_meshcheck.py
```

输出：

```text
cases/<case>/abaqus_meshcheck/<case>_meshcheck.inp
cases/<case>/abaqus_meshcheck/<case>_periodic_pairs.csv
cases/<case>/abaqus_meshcheck/<case>_meshcheck_export_report.json
```

这个 INP 故意只有：

- 节点；
- S3R 三角壳单元；
- X0/XL/Y0/YL/Z0/ZL node sets；
- 占位 elastic material；
- 占位 shell thickness；
- dummy step。

**没有**：

- PBC equations；
- 刚性压板；
- 接触；
- 真正材料；
- 压缩载荷。

这样 Abaqus 报错时，可以确定问题来自 mesh 本身，而不是物理模型耦合。

---

# 15. Abaqus Data Check

普通 CMD：

```cmd
cd /d <本项目目录>
tools\run_abaqus_datacheck.cmd
```

它会自动执行类似：

```cmd
abaqus job=fig1_meshcheck input=fig1_meshcheck.inp datacheck interactive
```

正常应：

```text
Abaqus JOB fig1_meshcheck COMPLETED
```

注意：`COMPLETED` 只是 Abaqus 命令结束，不代表 `.dat/.msg` 中完全没有网格警告，所以还要做 Step 07。

---

# 16. Step 07：自动判断 Abaqus Data Check

回 VS Code PowerShell：

```powershell
python .\07_validate_abaqus_datacheck.py
```

或：

```powershell
.\tools\run_datacheck_validator.ps1
```

脚本自动检查：

```text
ERROR
DISTORT
ASPECT RATIO
SHELL NORMAL / ErrElemShellNormal
NEGATIVE AREA
ZERO AREA
```

`.dat` 和 `.msg` 是必须文件。

`.sta` 对纯 datacheck 不是必需，因此缺失不会再误判 FAIL。

最终目标：

```text
fatal count = 0
ABAQUS DATACHECK STATUS: PASS
```

到这里才算“自动网格模块真正通过”。

---

# 17. 新手最快操作方式

Python 预处理全部跑完：

```powershell
conda activate diffumeta_geo
cd <本项目目录>
.\tools\run_preprocess.ps1
```

第一次编译 CGAL：

```cmd
conda activate diffumeta_cgal
cd /d <本项目目录>
tools\build_cgal.cmd
```

生成网格：

```cmd
tools\run_cgal.cmd
```

Python 后处理：

```powershell
conda activate diffumeta_geo
.\tools\run_postprocess.ps1
```

Abaqus：

```cmd
tools\run_abaqus_datacheck.cmd
```

最后：

```powershell
.\tools\run_datacheck_validator.ps1
```

---

# 18. 换一个新曲面时到底要改什么

理论上只需要改：

```text
config/case.json
```

至少修改：

```json
"case_id": "new_case",
"cell_size_mm": 10.0,
"surface_expression": "你的公式"
```

然后从 Step 01 重新运行。

如果只是换公式而 `L`、几何频率尺度和目标单元尺寸大致相同，可以先沿用当前 CGAL 参数；但在真正大批量前，应对一批“最难的曲面”重新确认鲁棒性。

如果 `L` 大幅改变，建议按无量纲比例重新考虑：

- topology sampling interval；
- boundary spacing；
- edge/facet size；
- facet distance；
- cell size。

---

# 19. 为什么 x=0 与 x=L 节点不能去重

这是 FE 周期边界最常见的坑。

几何意义上：

```text
x=0 与 x=L 是同一个周期位置
```

但 Abaqus PBC 需要两个**独立节点自由度**，之后通过 equation constraint 建立：

```text
u(XL) - u(X0) = prescribed macroscopic relation
```

如果 Python 在去重阶段把两端节点直接合并，后面就失去了施加周期边界方程的自由度。

所以 Step 05 只按真实 Cartesian 坐标去重，不做 `mod L` 去重。

---

# 20. 哪些旧代码已经明确删除，不要再恢复到主线

以下属于研发试验，不属于生产流程：

- `14_cgal_probe`
- `15_export_cgal_input.py`（OFF 中间路线）
- `16_cgal_mesh_io_probe`
- `17_prepare_full_periodic_constraints.py`
- `17b_prepare_segment_constraints.py`
- `18_cgal_delaunay_probe`
- `19_validate_cgal_periodic_mesh.py`
- `19b_diagnose_cgal_periodicity.py`
- `20_periodic3_probe`
- `22_periodic3_feature_cut_probe`
- `23_periodic3_shell_export`
- `25_validate_mesh_size_sweep.py`
- `25b_validate_S15.py`
- 所有 `build/`、`.exe/.obj/.pdb`、`__pycache__`
- S16/S17/S18 调参输出
- ordinary CGAL remesh / segment-remesh 输出

它们帮助我们证明“为什么最终路线是对的”，但不应再进入正式自动计算程序。

---

# 21. 当前代码哪些地方仍然值得后续继续改

这版已经解决了“源码太乱、方程散落、失败代码混在一起”的问题，但距离最终数万样本批处理仍有下一层工作：

### 21.1 将 01–07 包装成统一 batch runner

未来应该有一个入口：

```text
python run_case.py config/case_xxx.json
```

自动完成环境内 Python 步骤，并负责调用外部 CGAL/Abaqus 命令。

### 21.2 建立失败分类码

建议至少分：

```text
GEOMETRY_INVALID
BOUNDARY_EXTRACTION_FAIL
BOUNDARY_PROJECTION_FAIL
CGAL_FAIL
CGAL_CLIPPING_REQUIRED
TOPOLOGY_FAIL
PERIODICITY_FAIL
QUALITY_FAIL
ABAQUS_DATACHECK_FAIL
ABAQUS_SOLVE_FAIL
```

批量运行时一个样本失败不能让整个任务停掉。

### 21.3 超时与有限重试

CGAL / Abaqus 都需要：

```text
最大运行时间
失败后有限次数重试
仍失败则记录并跳过
```

不能无限重试。

### 21.4 批量结果只保留必要文件

长期批量时建议保留：

```text
case.json
最终 shell npz
validator report.json
Abaqus inp
Abaqus 结果/提取曲线
失败日志
```

`.mesh`、大 CSV、中间 MC topology 可以在成功后按需要清理，以节省大量磁盘。

---

# 22. 回归验证说明

这次重构不是纯粹“改名字”。Python 主链 01–04 已在提供的 Fig.1 源码/数据上回归运行：

- topology 的 vertices/faces/pairs 与原成功版本一致；
- master boundary connectivity 一致；
- standardized curves 与原版最大坐标差约机器精度；
- Step 05 对原 S15 canonical triangle CSV 得到与原版相同的 9482 nodes / 18162 triangles / 质量与周期指标；
- Step 06 成功导出同等 S3R mesh-check 模型；
- Step 07 用原 Abaqus `.dat/.msg` 重新检查得到 PASS；
- 新 C++ 运行时公式解析器已单独通过 C++17 编译/数值测试。

CGAL `main.cpp` 是由原来已经成功编译运行的 Stage-25 Periodic_3 mesher 重构而来，核心 CGAL 类型、feature 输入、`make_periodic_3_mesh_3`、offset-aware triangle extraction、whole-facet canonical translation 与 clipping=0 判据均保留。由于本重构环境不是你的 Windows+CGAL 环境，**新的整合版 C++ 仍应在你的 x64 Native Tools + diffumeta_cgal 上执行一次 `tools\build_cgal.cmd` 和 Fig.1 回归运行**。只要 Fig.1 得到接近 `REFERENCE_RESULTS.md` 的结果，即可将该 C++ 重构版冻结。

---

# 23. Git 建议

清理后的目录非常适合直接作为一个新的 Git 项目：

```powershell
git init
git add .
git commit -m "periodic mesher clean production baseline"
```

以后不要把：

```text
build/
__pycache__/
Abaqus 大型临时结果
CGAL 大型中间输出
```

提交到 Git；`.gitignore` 已经做了基础排除。

---

# 24. 最终原则

生产流程真正信任的不是“CGAL 没报错”，而是连续四道门：

```text
Python 周期拓扑 PASS
        ↓
CGAL canonical placement: clipping = 0
        ↓
Python final shell validator PASS
        ↓
Abaqus Standard Data Check PASS
```

只有四道门都通过，这个样本才有资格进入后续真实材料、PBC、接触和 30% 压缩求解。
