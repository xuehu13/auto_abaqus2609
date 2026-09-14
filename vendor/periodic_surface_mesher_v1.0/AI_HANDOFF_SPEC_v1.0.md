---
project: Periodic Surface Mesher
version: 1.0
status: validated
validated_date: 2026-09-12
validated_end_to_end: true
validated_final_gate: Abaqus 2026 Standard Data Check PASS
primary_language: Chinese
purpose_of_this_file: AI project handoff / context compression
---

# AI 项目交接说明：Periodic Surface Mesher v1.0

> **给新的 AI / 新窗口：请先完整阅读本文档，再阅读源码。**  
> 本文档是项目的“技术上下文压缩包”。它不是新手逐步教学手册，而是为了让一个新的 GPT / Claude / Codex / 其他 AI 在没有历史聊天记录的情况下，迅速、准确地理解：项目为什么存在、最终采用了什么算法、每个文件负责什么、哪些路线已经证明失败、哪些结果已经真实验证、哪些限制仍然存在、以后修改代码时必须保护哪些不变量。  
> **除非用户明确要求，不要重新设计已经通过回归验证的网格核心。** 当前 v1.0 应视为稳定基线；后续功能应优先在其外层扩展。

---

## 0. 新 AI 应如何使用这份交接文档

当用户把本源码包和本文档交给你时，按以下优先级理解项目：

1. **本文档是架构、决策和项目状态的权威说明。**
2. `REFERENCE_RESULTS.md` 是 Fig.1 的权威回归数值基线。
3. `config/case.json` 是当前 case 的单一配置入口。
4. `README.md` 是给人类操作者的详细说明；可作为补充，但不必依赖历史聊天。
5. 源码是最终真相。若本文档和代码出现矛盾，以当前源码行为为准，并指出文档需要更新。
6. 如果你修改了任何核心算法、数据格式、PASS 判据、C++ 表达式解析器、CGAL 参数传递方式或 Abaqus 导出格式，修改后必须重新跑完整回归，并更新 `REFERENCE_RESULTS.md` 和本文档。

未来 AI 不应为了“代码更漂亮”而无目标地重写核心。只有以下情况才应修改核心：

- 用户明确提出新功能，而现有架构无法满足；
- 新曲面暴露了真实的算法缺陷；
- 已定位明确 bug；
- 需要扩展现有已知限制（例如非零 iso-level、非立方体单胞、新数学函数、分叉 seam 等）；
- 有可验证的性能/鲁棒性收益，并能通过回归测试证明没有破坏现有行为。

---

# 1. 项目目标和科研背景

本项目服务于周期隐式曲面/机械超材料的自动有限元建模。核心目标不是“生成一张好看的三角网格”，而是：

**从一条周期隐式曲面方程 `f(X,Y,Z)=0` 出发，自动生成 Abaqus 可接受、边界严格周期、拓扑干净、质量合理的 S3R 三角壳网格，并为未来大量样本的自动有限元计算提供稳定网格底座。**

项目源于对论文 *Algebraic language models for inverse design of metamaterials via diffusion transformers*（Nature Machine Intelligence, 2026）工作流的复现和扩展。原论文使用隐式周期曲面构造壳体单胞，通过 Abaqus 计算力学响应，再用于生成模型训练。论文/补充材料中与后续物理模型相关的关键信息包括：

- 使用 **S3R 三角壳单元**；
- 周期兼容网格用于施加 PBC；
- 论文网格收敛比较平均边长约 `0.35 / 0.25 / 0.20 / 0.15 mm`，最终采用约 `0.20 mm`；
- 壳厚按目标相对密度计算：`h = rho_target * Vcube / A_surface`；
- 压缩模型使用上下刚性压板；侧向施加周期边界；底板固定，顶板压到 30% 应变；
- General Contact 摩擦系数约 `0.6`；
- Dynamic Implicit 模拟准静态压缩，并检查 `ALLKE < 1% ALLIE`；
- 这些“真实物理模型”内容**尚未放入 v1.0 网格模块**。

用户的工程目标是以后批量计算大量曲面，因此最重要的设计原则是：

- **自动化**：尽量不依赖 CAE GUI；
- **鲁棒性优先**：坏样本早失败，不把坏网格送入耗时 Abaqus 求解；
- **严格周期性**：不能接受“看起来差不多周期”；
- **可重复**：同一输入应尽可能得到相同网格；
- **分层验证**：CGAL 自己说 PASS 不够，还要独立 Python validator + Abaqus Data Check；
- **失败隔离**：未来批处理时单个样本失败不应拖垮整批任务。

---

# 2. v1.0 的边界：已经解决什么，尚未解决什么

## 2.1 v1.0 已经解决

当前源码已经真实完成并验证以下闭环：

```text
periodic implicit equation
        ↓
exact-periodic scalar sampling
        ↓
Marching-Cubes topology scaffold
        ↓
periodic node + edge topology checks
        ↓
master seam extraction on X0/Y0/Z0
        ↓
exact endpoint solve + arc-length resampling + projection to f=0
        ↓
CGAL Periodic_3 with protected artificial seam features
        ↓
offset-aware surface facet extraction
        ↓
whole-triangle integer-period translation into canonical cell
        ↓
strict Python shell validator
        ↓
Abaqus S3R mesh-check INP
        ↓
Abaqus 2026 Standard Data Check
        ↓
automatic .dat/.msg log validator
```

Fig.1 已经端到端实测 PASS。

## 2.2 v1.0 尚未解决

以下属于后续模块，不应混进已冻结的 00–07 网格核心：

- 真实材料模型；
- 壳厚 `h = rho_target*V/A` 的正式计算与赋值；
- X/Y 侧向 PBC 方程；
- 上下刚性压板；
- General Contact 和摩擦；
- 30% 压缩；
- Dynamic Implicit；
- 准静态判据 `ALLKE/ALLIE`；
- ODB 自动提取应力–应变曲线；
- 大批量 case runner；
- 自动超时、有限重试、失败分类、结果数据库；
- 与 DiT/扩散模型训练联动。

推荐以后新增外层文件，例如：

```text
08_build_abaqus_physical_model.py
09_run_abaqus_analysis.py
10_extract_odb_results.py
11_batch_runner.py
```

不要把真实物理模型重新塞进 `01–07`。

---

# 3. 目前的正式架构和“不变量”

以下原则是 v1.0 的核心，不要轻易破坏。

## 3.1 隐式方程坐标约定

用户在 `config/case.json` 中写的是无量纲周期角变量 `X,Y,Z`，每个变量周期为 `2*pi`：

```text
X = 2*pi*x/L
Y = 2*pi*y/L
Z = 2*pi*z/L
```

其中物理坐标 `x,y,z` 单位是 mm，当前单胞是立方体 `[0,L]^3`。

Fig.1：

```text
f(X,Y,Z) = 2.3*cos(X)*sin(Z) + 1.9*cos(Y)*cos(Z) - 0.6
```

目标曲面是零水平集 `f=0`。

## 3.2 Marching Cubes 只做拓扑，不做最终 FE 网格

Step 01 的 Marching Cubes 网格可能含大量细长三角形。它只承担：

- 识别曲面连通关系；
- 找单胞边界交线；
- 识别周期节点；
- 确认周期边拓扑；
- 为 master seam 提供拓扑骨架。

**严禁把 Step 01 的 MC 三角形直接作为 Abaqus 最终网格。**

## 3.3 只添加 master seam，不添加 slave 副本

CGAL Periodic_3 工作在平坦三维环面中。`X0` 与 `XL` 是周期等价切口，Y/Z 同理。

因此显式 feature 只来自：

```text
X0
Y0
Z0
```

不把 XL/YL/ZL 独立作为第二套 feature 加进去。

## 3.4 canonical extraction 使用“整个三角形统一周期平移”

对一个周期表面三角形，程序分别在 x/y/z 上寻找一个整数 `k`，使三个顶点**共同**加 `k*L` 后进入 `[0,L]`。

必须是：

```text
triangle vertex 0 + kL
triangle vertex 1 + kL
triangle vertex 2 + kL
```

而不是三个顶点分别 `mod L`。

逐顶点 modulo 会把跨周期的小三角形拉成横跨整个单胞的巨大假三角形。

## 3.5 人工 seam 的验收目标是 clipping = 0

如果 seam 正确成为网格边，则 canonical cut 不应穿过任何三角形内部。C++ 输出必须满足：

```text
facets requiring clipping = 0
```

这使生产架构不需要复杂、脆弱的“三角形与立方体平面裁切”算法。

## 3.6 最终 FE 节点不能周期合并

Step 05 去重时：

- 同一物理坐标的重复 triangle-soup 顶点要合并；
- 但 `x=0` 和 `x=L` 即使周期等价，也必须保留为两个不同 Abaqus 节点；
- Y/Z 同理。

以后 PBC 是通过节点关系/方程施加，不是通过提前 merge 周期边界节点。

## 3.7 生成器和验收器必须分开

CGAL mesher 负责“生成”；`05_validate_shell.py` 必须独立重新验证，不因 C++ 返回 PASS 就跳过。

之后还要 Abaqus Data Check。

---

# 4. 源码目录和职责

正式 v1.0 源码树：

```text
periodic_surface_mesher_v1.0/
│
├─ config/
│  └─ case.json
│
├─ meshlib/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ surface.py
│  └─ flags.py
│
├─ 00_check_python_environment.py
├─ 01_build_periodic_topology.py
├─ 02_extract_master_boundaries.py
├─ 03_standardize_master_boundaries.py
├─ 04_export_cgal_input.py
│
├─ cgal_mesher/
│  ├─ CMakeLists.txt
│  ├─ expression_parser.hpp
│  └─ main.cpp
│
├─ 05_validate_shell.py
├─ 06_export_abaqus_meshcheck.py
├─ 07_validate_abaqus_datacheck.py
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
├─ README.md
├─ VERSION.txt
├─ AI_HANDOFF_SPEC_v1.0.md
└─ cases/
```

`cases/` 里的运行结果不属于源码本体；每个 case 会在运行时自动建立自己的子目录。

---

# 5. 配置系统：config/case.json

这是正常换曲面时唯一应该优先修改的入口。

当前 Fig.1：

```json
{
  "case_id": "fig1",
  "description": "Figure-1 implicit periodic surface used to validate the pipeline",
  "cell_size_mm": 10.0,
  "iso_level": 0.0,
  "surface_expression": "2.3*cos(X)*sin(Z) + 1.9*cos(Y)*cos(Z) - 0.6",

  "topology_sampling_intervals": 100,
  "boundary_target_spacing_mm": 0.18,

  "cgal": {
    "edge_size_mm": 0.18,
    "facet_angle_deg": 25.0,
    "facet_size_mm": 0.15,
    "facet_distance_mm": 0.03,
    "cell_radius_edge_ratio": 2.0,
    "cell_size_mm": 0.50,
    "random_seed": 20260911
  },

  "tolerances": {
    "snap_mm": 1e-8,
    "topology_pair_mm": 1e-7,
    "boundary_mm": 1e-8,
    "feature_plane_mm": 1e-9,
    "feature_periodic_mm": 1e-8,
    "dedup_mm": 1e-9,
    "final_pair_mm": 1e-8,
    "area_mm2": 1e-14
  },

  "abaqus": {
    "element_type": "S3R",
    "meshcheck_material_E": 1.0,
    "meshcheck_material_nu": 0.30,
    "meshcheck_thickness_mm": 1.0
  }
}
```

### 配置字段含义

- `case_id`：输出 case 文件夹名和 job 前缀。
- `cell_size_mm`：立方单胞边长 L。
- `iso_level`：目前端到端生产版必须保持 `0.0`，见“已知限制”。
- `surface_expression`：唯一曲面方程来源。
- `topology_sampling_intervals`：Step 01 每个方向的采样区间数，`dx=L/n`。
- `boundary_target_spacing_mm`：Step 03 seam 重采样最大目标间距。
- `cgal.edge_size_mm`：1D feature 边尺寸 criterion。
- `cgal.facet_angle_deg`：CGAL surface facet angle criterion。
- `cgal.facet_size_mm`：CGAL surface facet size criterion。
- `cgal.facet_distance_mm`：隐式几何逼近距离 criterion。
- `cgal.cell_radius_edge_ratio`、`cell_size_mm`：内部 3D mesh criterion；最终只抽表面。
- `random_seed`：固定后有利于回归可重复。
- `tolerances`：数值噪声、边界、配对、去重的工程容差。
- `abaqus`：仅 Mesh Data Check 占位参数，不是真实物理材料。

**不要通过放大 tolerance 去“修复”真实周期错误。**

---

# 6. Python 公共模块

## 6.1 meshlib/config.py

职责：

- 读取 `config/case.json`；
- 暴露冻结的 `CFG` 对象；
- 集中管理所有 case 目录；
- 自动创建：
  - `cases/<case>/`
  - `cgal_input/`
  - `cgal_output/`
  - `shell/`
  - `abaqus_meshcheck/`

关键原则：**不要在各 stage 中重新硬编码 `F:\...` 路径或重复配置。**

换曲面一般不改本文件。

## 6.2 meshlib/surface.py

这是 Python 侧隐式方程的单一真相来源。

功能：

1. 从 `CFG.expression` 用 SymPy 解析表达式；
2. 自动求 `df/dX, df/dY, df/dZ`；
3. 乘 `2*pi/L` 转成物理坐标梯度 `df/dx,df/dy,df/dz`；
4. 提供：
   - `implicit_xyz()`
   - `implicit_points()`
   - `gradient_points()`
   - `gradient_magnitude()`
   - `periodic_scalar_field()`

最关键的函数是 `periodic_scalar_field()`：

它不在终点 `2*pi` 独立重新计算标量场，而是只计算 `n x n x n` 基础块，再把第一张 plane 直接复制为最后一张 plane。因此相对边界标量值是**位级相同**，而不仅是数学上相等。这是 Step 01 获得严格对面拓扑的基础。

当前 Python 允许函数：

```text
sin cos tan exp sqrt abs / Abs pi
```

## 6.3 meshlib/flags.py

六个 cell face 用 bit flag：

```text
X0, XL, Y0, YL, Z0, ZL
```

节点位于 cube edge/corner 时可同时拥有多个 flag。

`MASTER_FACES` 只包含：

```text
X0, Y0, Z0
```

---

# 7. Step 00：00_check_python_environment.py

目标：只做最早的环境和公式 sanity check，不生成网格。

检查：

- Python / numpy / scipy / skimage / sympy 能 import；
- `case.json` 能读取；
- f 在测试点可计算；
- 解析梯度可计算；
- 结果为有限数值。

Fig.1 已验证：

```text
Python 3.10.21
NumPy 2.2.6
SciPy 1.15.3
scikit-image 0.25.2
SymPy 1.14.0
PYTHON ENVIRONMENT STATUS: PASS
```

此步骤不代表几何有效，只代表环境/表达式基础工作正常。

---

# 8. Step 01：01_build_periodic_topology.py

## 8.1 目的

建立“拓扑骨架”，回答：

- 曲面在 cell 内如何连接？
- 是否存在内部裂缝/非流形？
- 对面边界节点能否严格配对？
- 对面自由边的连接拓扑是否一致？
- 把周期边界粘合后是否是单一连通结构？

## 8.2 算法

1. 从 `surface.periodic_scalar_field()` 得到 `(n+1)^3` 严格周期标量场；
2. `skimage.measure.marching_cubes(..., method='lewiner', allow_degenerate=False)`；
3. 将非常接近 `0/L` 的坐标吸附到精确边界面；
4. 为每个顶点建立 boundary flags；
5. 用 cKDTree 匹配：
   - X0 ↔ XL：比较切向 `(y,z)`；
   - Y0 ↔ YL：比较 `(x,z)`；
   - Z0 ↔ ZL：比较 `(x,y)`；
6. 构造 mesh edge incidence；
7. 检查自由边；内部自由边 = 裂缝；edge incidence >2 = nonmanifold；
8. 把对面边界自由边转换到同一周期切向坐标，要求 edge set 完全一致；
9. DSU/并查集建立 periodic equivalence classes；
10. 检查周期 glue 后 connected components。

## 8.3 硬性 PASS 条件

源码中的 `topology_ok`：

```text
internal_free_edges == 0
nonmanifold_edges == 0
X opposite edge topology identical
Y opposite edge topology identical
Z opposite edge topology identical
periodically glued components == 1
```

注意：Step 01 **没有**要求 Marching-Cubes 单元质量好。

## 8.4 输出数据契约

`periodic_topology.npz`：

- `vertices`：`float64 [Nv,3]`
- `faces`：`int64 [Nt,3]`
- `boundary_flags`
- `pair_x`, `pair_y`, `pair_z`：周期节点 index 对
- `periodic_class`：每个 MC 顶点的周期等价类 ID
- `free_edges`

`topology_report.json`：人类/批处理可读报告。

---

# 9. Step 02：02_extract_master_boundaries.py

## 9.1 目的

从 Step 01 的自由边中提取三个 master face：

```text
X0, Y0, Z0
```

上的交线，并把散乱的 edge graph 排成有序 polyline。

## 9.2 算法

- 过滤位于某个 master face 的 boundary edges；
- 建立无向 adjacency graph；
- 找 connected components；
- 对每个 component：
  - 开放曲线：应有 2 个 degree=1 端点，其余 degree=2；
  - 闭合曲线：全部 degree=2；
  - 任何分叉（degree>2）视为当前算法不支持；
- 按确定性节点排序沿 graph 走完曲线；
- 记录端点位于哪些 cube faces；
- 记录端点的 `periodic_class`。

Fig.1：

```text
X0: 4 curves
Y0: 2 curves
Z0: 2 curves
Total: 8
shared periodic endpoint classes = 0, 4, 107, 472
```

Step 02 只解决 seam 的**拓扑顺序**，原始 MC 边仍可能极短，不应直接给 CGAL。

## 9.3 输出数据契约

`master_boundary_curves.npz`：

- `curve_vertex_ids`：所有曲线的原始 MC vertex IDs 拼接
- `curve_offsets`：每条曲线的切片 offset
- `curve_face_id`：0/1/2 对应 X0/Y0/Z0
- `curve_closed`
- `curve_length_mm`
- `master_face_names`

---

# 10. Step 03：03_standardize_master_boundaries.py

## 10.1 目的

把 MC seam 变成 CGAL 可安全保护的 feature：

- 端点准确；
- 线段均匀；
- 全部点重新落在真实 `f=0`；
- 共享周期端点完全一致。

## 10.2 算法核心

### A. canonical endpoint classes

对共享 `periodic_class` 构造 canonical 表示，将 L 等价映射到 0，用于判断跨面端点是否实际上是同一个周期点。

### B. cube-edge 上精确 root solve

开放 seam 的端点位于两个 cube face 的交线，即立方体棱。固定两维，只对剩余自由坐标解一维 `f=0` 根，使端点不再依赖 MC 插值误差。

### C. 等弧长重采样

按累计 chord length 重采样，每段目标不超过 `boundary_target_spacing_mm`。

### D. master face 内投影

固定所在 master plane（X0/Y0/Z0），使用解析梯度的面内分量，把插值点 Newton-like 投影回 `f=0`。

### E. 重分布迭代

多轮“等弧长重采样 + 投影”，降低投影后重新出现的长度不均匀。

## 10.3 当前硬性 PASS

```text
max |f| < 1e-8
max endpoint periodic mismatch < 1e-10
number of segments < 0.05 mm == 0
number of segments > 0.20 mm == 0
```

这些是当前实现针对 Fig.1/当前长度尺度的工程阈值，不应在未来盲目放大。

## 10.4 输出数据契约

`standard_boundary_curves.npz`：

- `curve_points`：所有标准化坐标拼接
- `curve_offsets`
- `curve_face_id`
- `curve_closed`
- `curve_start_class`
- `curve_end_class`
- `endpoint_classes`
- `endpoint_canonical_coords`
- `master_face_names`

---

# 11. Step 04：04_export_cgal_input.py

## 11.1 目的

作为 Python→C++ 接口层，最后一次验证 feature，并输出纯文本输入。

## 11.2 检查

- 坐标 finite；
- 全部在 cell bounds 内；
- 每条曲线留在正确 master plane；
- node `|f|` 足够小；
- segment 长度合理；
- periodic endpoint class mismatch 足够小；
- 在 segment 的 1/4、1/2、3/4 采样处估算 chord 与真实隐式曲面的法向偏差，作为诊断量。

## 11.3 硬性 PASS

```text
finite_ok
bounds_ok
max plane error <= feature_plane_mm
max node |f| <= 1e-8
min segment > 0.05 mm
max segment <= 0.20 mm
max endpoint class mismatch <= feature_periodic_mm
```

`max feature chord error` 当前只报告，不是硬 reject 条件。

## 11.4 feature 文本格式

`periodic3_master_features.txt`：

```text
number_of_curves
face_id closed start_class end_class n_points
x y z
x y z
...
```

face_id：

```text
0 = X0
1 = Y0
2 = Z0
```

## 11.5 C++ runtime config 格式

`cgal_case.txt`：

```text
L=...
expression=...
edge_size=...
facet_angle=...
facet_size=...
facet_distance=...
cell_radius_edge_ratio=...
cell_size=...
random_seed=...
```

---

# 12. C++ expression_parser.hpp

目的：让 C++ 不再写死 Fig.1 方程，新 case 不需要重新改 main.cpp。

这是一个小型递归下降解析器。

支持：

```text
numbers
X Y Z
pi / PI
+ - * / ^
parentheses
sin() cos() tan() exp() sqrt() abs()/Abs()
```

指数 `^` 是右结合。

任何未来新数学函数若要加入，必须同时考虑：

1. `meshlib/surface.py` 的 SymPy `_ALLOWED`；
2. `expression_parser.hpp` 的 parser 和 eval；
3. 用同一批测试点比较 Python 与 C++ 数值；
4. 再跑完整 Fig.1 回归。

**不能只在 Python 加函数而忘记 C++。**

---

# 13. C++ main.cpp：CGAL Periodic_3 核心

## 13.1 关键 CGAL 类型

- `Exact_predicates_inexact_constructions_kernel`
- `Labeled_mesh_domain_3`
- `Mesh_domain_with_polyline_features_3`
- `Periodic_3_mesh_triangulation_3`
- `Mesh_complex_3_in_triangulation_3`
- `Mesh_criteria_3`
- `make_periodic_3_mesh_3`

## 13.2 运行时读取

main.cpp 从 `cgal_case.txt` 读取：

- L；
- expression；
- edge/facet/cell criteria；
- random seed。

曲面函数内部将物理坐标转换为 `X=2*pi*x/L` 等，再用 `Expression.eval()`。

## 13.3 feature 注入

只读取 Step04 的 8 条 master polyline，调用 `domain.add_features(...)`。

这些不是物理折痕，而是**人工 cut seam features**。目的只是强制周期切口成为 mesh edge，从而保证 canonical-cell extraction 不切穿三角形。

## 13.4 meshing flags

生产核心使用：

```text
features()
manifold()
no_perturb()
no_exude()
```

含义：

- `features()`：保护 1D artificial seam；
- `manifold()`：要求 surface complex 为流形；
- `no_perturb()` / `no_exude()`：关闭后续优化，减少 feature/mesh 改动并提高可重复性。

## 13.5 周期 facet 提取

必须使用 `tr.triangle(facet)`（内部考虑 periodic offsets），而不是简单用当前 fundamental cell 的 vertex coordinate 拼三角形。

## 13.6 canonical-cell whole-facet translation

对每个三角形每个轴，`find_periodic_shift()` 找一个整数 k，使所有三个顶点同时：

```text
-TOL <= coord + k*L <= L+TOL
```

若找不到，facet 记入 `_unplaceable_facets.csv`，并计为 requiring clipping。

最终生产要求：

```text
facets_requiring_clipping == 0
```

## 13.7 输出 CSV

`*_canonical_triangles.csv` header：

```text
facet_id,
x0,y0,z0,
x1,y1,z1,
x2,y2,z2,
shift_x,shift_y,shift_z
```

这是 Step05 的唯一几何输入。

---

# 14. Step 05：05_validate_shell.py

这是整个工程里最重要的独立 validator。

## 14.1 输入

`cgal_output/<case>_mesh_canonical_triangles.csv`

## 14.2 节点去重

triangle soup 中同一顶点可能被重复输出。程序使用空间 hash bins + 相邻桶搜索，在 `dedup_mm` 内确定性合并。

**周期边界不做 modulo 合并。**

## 14.3 面定向

1. 建 edge→incident triangles；
2. 对共享内部边传播三角形 orientation，使共享边方向相反；
3. 对每个 orientation component 计算 triangle normal 与解析 `grad(f)` 的总点积；
4. 若为负，整体翻面；
5. 最终正常应 `positive_gradient_normal_fraction = 1.0`。

## 14.4 拓扑检查

构造无向 edge incidence：

- incidence=1：free edge；
- incidence=2：internal edge；
- incidence>2：nonmanifold。

所有 free edge 必须位于至少一个 cube face；否则属于 unintended free edge/internal crack。

还检查：

- repeated-node triangle；
- duplicate face group；
- zero area；
- orientation conflict。

## 14.5 周期 face 检查

对 X/Y/Z 分别：

- low/high boundary node 数量相等；
- 切向 KDTree 最近邻；
- 映射一一；
- 互为最近邻（symmetric）；
- max mismatch ≤ `final_pair_mm`；
- low free-edge set 通过节点映射后必须与 high free-edge set 完全相同。

因此这里验证的不只是“边界节点差不多对得上”，而是：

**node-level + edge-topology-level strict periodicity**。

## 14.6 质量指标

报告但当前不作为硬 PASS 的主要指标：

- edge min/mean/max；
- minimum triangle angle；
- shape quality：

```text
q = 4*sqrt(3)*A/(a^2+b^2+c^2)
```

等边三角形 q=1，退化趋近 0；

- edge ratio；
- `max |f(node)|`；
- estimated normal error `|f|/|grad f|`。

## 14.7 Step05 硬性 PASS 条件

当前源码要求：

```text
nodes > 0
triangles > 0
degenerate connectivity == 0
duplicate face groups == 0
zero-area triangles == 0
nonmanifold edges == 0
unintended free edges == 0
orientation conflicts == 0
X/Y/Z periodic checks all pass
periodically glued components == 1
```

**注意：最小角和 q 当前不是硬 reject 阈值。** 这是一项未来可讨论的策略，但修改前要考虑不同曲面可能自然存在局部较差单元，并结合 Abaqus Data Check。

## 14.8 输出 shell NPZ 契约

`shell/<case>_shell.npz`：

- `nodes`：最终 FE node coordinates；
- `triangles`：0-based triangle connectivity；
- `facet_ids`：来源 C++ facet ID；
- `source_shifts`：C++ canonical translation integer shifts；
- `x_pairs`, `y_pairs`, `z_pairs`：最终周期 node pairs；
- `free_edges`。

---

# 15. Step 06：06_export_abaqus_meshcheck.py

目的：只验证网格本身能否被 Abaqus 接受，不掺杂真实力学模型。

输入：Step05 shell NPZ + report。

主要动作：

- 要求 Step05 report `pass=true`；
- 节点编号/单元编号转换成 Abaqus 1-based；
- 输出 `*Node`；
- 输出 `*Element, type=S3R, elset=EALL`；
- 建 X0/XL/Y0/YL/Z0/ZL node sets；
- 再检查周期 pairs 的真实向量分别接近：
  - X: `(L,0,0)`
  - Y: `(0,L,0)`
  - Z: `(0,0,L)`；
- 写占位 elastic material 和 shell section；
- 写一个 dummy `*Static` step；
- 导出周期 pair CSV，未来真实 PBC 可复用。

明确没有：

```text
physical PBC equations
rigid plates
contact
real material law
real shell thickness
30% compression
```

占位：

```text
E=1
nu=0.3
thickness=1 mm
```

这些只为 Data Check 模型完整，绝对不是物理模型参数。

---

# 16. Abaqus Data Check 与 Step 07

Abaqus 命令：

```text
abaqus job=<case>_meshcheck input=<case>_meshcheck.inp datacheck interactive
```

Step07 需要：

- `.dat`：required；
- `.msg`：required；
- `.sta`：optional。纯 datacheck 不生成 `.sta` 是允许的。

Step07 正则扫描：

```text
ERROR
WARNING
DISTORT
ASPECT RATIO
SHELL NORMAL / ErrElemShellNormal
NEGATIVE AREA
ZERO AREA
```

`warning` 记录但不自动算 fatal，因为 Abaqus warning 不全部意味着网格必须拒绝。

当前 fatal_count：

```text
error + distorted + aspect_ratio + shell_normal + negative_area + zero_area
```

PASS：

```text
required files exist AND fatal_count == 0
```

---

# 17. Fig.1 clean v1.0 权威回归基线

这些是**回归参考，不是所有未来曲面的通用阈值**。

验证环境：

```text
Python 3.10.21
NumPy 2.2.6
SciPy 1.15.3
scikit-image 0.25.2
SymPy 1.14.0
MSVC 19.50.35720.0
CGAL 6.0.1 environment
Abaqus 2026 Standard Data Check
```

### Step01

```text
MC vertices = 45,788
MC triangles = 89,984
periodic pairs X/Y/Z = 292 / 314 / 202
unique edges = 135,776
free edges = 1,600
internal cracks = 0
nonmanifold edges = 0
opposite edge topology X/Y/Z = all identical
periodic classes = 44,984
cut components = 1
periodically glued components = 1
surface area = 304.4657897949219 mm^2
```

### Step02

```text
X0 curves = 4
Y0 curves = 2
Z0 curves = 2
total master curves = 8
shared endpoint classes = 0, 4, 107, 472
```

### Step03

```text
standardized points = 381
segment min = 0.16757288158271053 mm
segment mean = 0.17783984235070335 mm
segment max = 0.17998120598355918 mm
max |f| = 8.938738638164523e-12
endpoint mismatch = 0
```

### Step04

```text
master features = 8
feature points = 381
max chord normal error = 0.0017215288268260308 mm
endpoint class mismatch = 0
```

### C++ CGAL

```text
periodic vertices = 13,486
surface facets = 18,164
domain cells = 53,201
protected feature edges = 405
corners = 4
facets iterated = 18,164
facets shifted by periods = 120
facets requiring clipping = 0
max physical surface edge = 0.34988197409894994 mm
max triangle axis span = 0.33958186078472963 mm
```

同一输入连续运行两次，canonical CSV SHA256 一致：

```text
61e8f550d6c3d74ba1122e985b0daf0c1ce7ed7617cdf0662f293b26a43a4c3f
```

### Step05

```text
nodes = 9,483
triangles = 18,164
unique edges = 27,651
free edges = 810
internal edges = 26,841
nonmanifold = 0
unintended free edges = 0
duplicate face groups = 0
degenerate connectivity = 0
zero area = 0
orientation conflicts = 0
cut components = 1
glued components = 1
```

Periodicity：

```text
X: 141 / 141 nodes, max mismatch 5.551115123125783e-17 mm
Y: 148 / 148 nodes, max mismatch 0
Z: 124 / 124 nodes, max mismatch 0
all mappings bijective + symmetric
all free-edge topology equal
```

Quality：

```text
surface area = 304.64827090489996 mm^2
min edge = 0.08219874121974885 mm
mean edge = 0.2018165715632065 mm
q95 edge = 0.26892352712065026 mm
max edge = 0.34988197409894994 mm
min triangle angle = 14.419297027070776 deg
mean minimum angle = 47.017817217158516 deg
q_min = 0.37424315023415416
q_mean = 0.9260424110589184
angle < 10 deg = 0
q < 0.2 = 0
max estimated normal error = 0.004279062903792588 mm
positive-gradient normal fraction = 1.0
```

### Abaqus 2026

```text
job completed normally
.dat present
.msg present
.sta absent (allowed)
ERROR = 0
WARNING = 0
DISTORT = 0
ASPECT RATIO = 0
SHELL NORMAL = 0
NEGATIVE AREA = 0
ZERO AREA = 0
fatal_count = 0
ABAQUS DATACHECK STATUS: PASS
```

历史探索版曾得到 9,482 nodes / 18,162 triangles。不要再把它当正式 baseline。clean v1.0 的 9,483 / 18,164 才是当前权威值。两者的小差异来自 runtime expression evaluator 与旧硬编码 C++ 表达式的微小浮点求值顺序差异；clean v1.0 已证明确定性、周期性、几何质量和 Abaqus Data Check 全部通过。

---

# 18. 为什么最终选择现在这条路线：已失败/淘汰方案

未来 AI 需要知道历史决策，避免重复做已经证明无效的探索。

## 18.1 直接用 raw Marching Cubes 作为 S3R：失败

早期高分辨率 MC：

```text
~45,788 vertices
~89,984 triangles
```

但质量非常差：

- 最小边可到约 `2.8e-05 mm`；
- 最小角约 `0.01°`（另一次统计甚至 ~0.002°）；
- 数千个 `<10°` 三角形；
- Abaqus Data Check 曾出现：
  - 5,661 distorted elements；
  - 114 high aspect ratio；
  - 24 ErrElemShellNormal（fatal）。

结论：**MC 只保留作为 topology scaffold。**

## 18.2 Gmsh 普通 remesh：没有形成可靠生产路线

边界/feature 分类和周期严格同步难以稳定实现，未得到可接受生产结果。

## 18.3 普通 CGAL surface_Delaunay_remeshing + external polylines：网格质量好，但严格周期失败

一次实验得到：

- min angle ~14.4°；
- 无明显 sliver；
- 但 X/Y 对面节点不是精确同步：
  - X tangential mismatch 约 `0.0176 mm`；
  - Y 可达约 `0.144 mm`；
- 甚至出现少量自由边离开 cube face。

把 16 条 polyline 再拆成数百两点 segment，输出 SHA256 完全不变，证明“segment splitting”没有修复问题。

结论：**普通 surface remesh 无法作为严格周期生产方案。**

## 18.4 后处理 snap / 强行配对：拒绝采用

把独立重网格后的边界节点强制 snap 到对面，可能破坏局部单元质量、拓扑和几何，批量化风险高。生产路线不依赖这一脆弱补丁。

## 18.5 最终成功方案

```text
exact-periodic topology scaffold
+ ordered master seams
+ standardized/projected seam features
+ CGAL Periodic_3
+ protected artificial cut features
+ whole-facet periodic placement
+ strict independent validator
```

它同时解决了：

- 周期边界离散同步；
- 三角形质量；
- canonical cell extraction；
- 可重复性；
- Abaqus 接受性。

---

# 19. 已知限制和技术债务

这是未来 AI 最应关注的部分。

## 19.1 iso_level 目前端到端仅支持 0

Python Step01 会读取 `CFG.level` 并可用于 MC level；但 C++ Periodic_3 的 domain 直接使用 `expression=0`，`cgal_case.txt` 没有传 `iso_level`。

因此当前正式使用：

```text
iso_level MUST remain 0.0
```

若未来支持非零 level，应统一定义：

```text
g(X,Y,Z) = expression(X,Y,Z) - iso_level
```

并在 Python/C++ 两端一致。

## 19.2 只支持立方体 `[0,L]^3`

配置只有一个 `cell_size_mm`。非立方体 `Lx,Ly,Lz` 不是简单改一个参数，至少涉及：

- X/Y/Z 物理→角坐标比例；
- C++ Iso_cuboid；
- periodic shift；
- boundary flags / root solve；
- pair vector validation。

应视为结构性升级。

## 19.3 表达式语法是 Python/C++ 支持集的交集

Python SymPy 能力比 C++ parser 强。正式表达式只使用双方共同支持的语法。

添加新函数时必须双端同步并回归。

## 19.4 Step01 的拓扑采样不是自适应

`n=100` 对 Fig.1 足够，不代表对高频/细颈/微小孔洞都足够。

若 feature 尺度接近或小于 `dx=L/n`，MC topology scaffold 可能漏拓扑。

未来可考虑：

- 自适应 topology precheck；
- 多分辨率一致性检查；
- 根据表达式频率自动选择 n；
- 但任何改动都需保护 exact periodic boundary construction。

## 19.5 Step02 不支持分叉 seam graph

当前排序逻辑假设每个 boundary component 是简单开放/闭合曲线，degree>2 的 branching graph 会失败。

这不是 bug，而是当前 supported geometry class 的限制。

## 19.6 Step03 假设开放端点能在 cube edge 上一维求根

若曲面在 cube edge 上切触、重根、梯度退化或形成复杂退化交线，root solve/projection 可能失败。

## 19.7 使用 manifold()，因此目标是流形周期表面

如果未来用户想生成真正非流形网络，不能简单把当前 validator 容差放宽；需要重新定义目标几何和 meshing mode。

## 19.8 C++ canonical placement 的 TOL 是 main.cpp 内固定 `1e-9`

它当前不是 case.json tolerance。若未来需要统一配置，可把它加入 `cgal_case.txt`，但修改后必须回归。

## 19.9 Step05 没有显式全局 self-intersection 检查

当前依赖 CGAL Periodic_3 的 mesh/domain 构造、manifold mode、拓扑 validator 和 Abaqus Data Check。若未来处理更复杂隐式面或担心非相邻三角形自交，可增加独立 self-intersection validator；不要用 OCR/可视化人工判断代替。

## 19.10 Step05 的 triangle-quality 目前主要是报告，不是硬 reject

当前 hard PASS 不直接要求 `min_angle > X` 或 `q_min > Y`。

如果未来批量出现 Abaqus 能接受但质量明显差的网格，可设计质量分级：

```text
PASS
PASS_WITH_WARNING
RETRY_WITH_FINER/DIFFERENT_CRITERIA
FAIL
```

不要直接把 Fig.1 的 `14.419°` 当所有曲面的普适阈值。

## 19.11 环境文件和实测 Python 包版本略有差异

`environment_geo.yml` 是较保守的复现 pin；实测通过的是 NumPy 2.2.6 等。当前结果已验证，无需仅因版本数字不同而重构。

核心算法升级时，优先记录真实环境和回归结果。

---

# 20. 未来修改代码时的回归协议

任何影响核心行为的改动都必须至少完成以下回归。

## 20.1 Python 00–04

Fig.1 应大致回归 `REFERENCE_RESULTS.md`。如果数量出现大变化，必须解释原因。

尤其要求：

```text
Step01 internal cracks = 0
Step01 nonmanifold = 0
Step01 X/Y/Z edge topology = True
Step01 glued components = 1
Step03/04 = PASS
```

## 20.2 C++ determinism

同一 Fig.1 输入运行两次：

```text
canonical_triangles.csv SHA256 identical
```

固定 seed 不等于理论上绝对跨平台 bit-identical，但在当前验证环境应保持同一输出。

## 20.3 Step05 strict shell validator

必须 PASS；尤其：

```text
nonmanifold = 0
unintended free edges = 0
duplicate = 0
degenerate = 0
orientation conflict = 0
X/Y/Z bijective = True
X/Y/Z symmetric = True
X/Y/Z edge topology equal = True
glued components = 1
```

## 20.4 Abaqus Data Check

必须真实运行 Abaqus 2026 或目标生产 Abaqus 版本，不能只检查 INP 文本。

Step07 fatal_count 必须为 0。

## 20.5 文档更新

如果新结果与基线不同但经论证是合理改进：

- 更新 `REFERENCE_RESULTS.md`；
- 更新 `VERSION.txt`；
- 版本至少升级到 v1.1；
- 在本 AI handoff 中更新“权威基线”和“已知限制”。

---

# 21. 按修改类型给未来 AI 的建议

## 21.1 只是换一条新曲面方程

优先只改：

```text
config/case.json
```

完整跑 00→07。

不要复制一份 Python/C++ 再硬编码新方程。

## 21.2 想改变最终网格尺寸

先调 `facet_size_mm`，并监测实际 `mean edge`，不要把 `facet_size` 当成真实最大/平均边长。

Fig.1：

```text
facet_size = 0.15 mm
mean final edge ≈ 0.2018 mm
max edge ≈ 0.3499 mm
```

必要时同时看：

- edge_size；
- facet_distance；
- boundary feature spacing；
- 单元质量和 Abaqus Data Check。

## 21.3 想加入新的数学函数

双端修改：

```text
meshlib/surface.py
cgal_mesher/expression_parser.hpp
```

先写小测试比较 Python/C++ 多点数值，再完整回归。

## 21.4 想支持非零 iso-level

不要只改 Python。必须把 level 传进 `cgal_case.txt`，并保证 C++ domain 求的是 `expression - level = 0`。

## 21.5 想支持非立方体单胞

视为 v2 级结构升级，不要在现有代码里打局部补丁。

## 21.6 想提高大批量鲁棒性

优先在外层增加 orchestrator，不重写 mesher core：

- case queue；
- subprocess isolation；
- timeout；
- nonzero exit code classification；
- finite retries；
- checkpoint；
- already-PASS skip；
- JSON summary；
- failed-case quarantine。

## 21.7 想继续论文真实压缩模型

应从 Step05/06 已得到的：

```text
nodes
triangles
x_pairs
y_pairs
z_pairs
surface area
```

构造新“物理 FE 层”。

论文压缩中侧向 PBC 应主要施加 X/Y；Z0/ZL 是压板接触截面，不应机械地把 Z 向也周期绑定进压缩模型。

---

# 22. 工具脚本和环境

三类终端：

```text
VS Code PowerShell + diffumeta_geo
    Python 00–07

x64 Native Tools Command Prompt + diffumeta_cgal
    build/run C++ CGAL

ordinary CMD
    abaqus launcher
```

封装脚本：

- `tools/run_preprocess.ps1`：01→04；
- `tools/build_cgal.cmd`：删除旧 build，CMake+Ninja Release 编译；
- `tools/run_cgal.cmd`：读 case_id，运行 mesher；
- `tools/run_postprocess.ps1`：05→06；
- `tools/run_abaqus_datacheck.cmd`：调用 Abaqus datacheck；
- `tools/run_datacheck_validator.ps1`：07。

任何 stage 非零 exit code 都应被未来 batch controller 当作“此 sample 停止”，而不是让整个批次崩溃。

---

# 23. 运行结果目录的数据生命周期

`cases/<case_id>/` 主要文件：

```text
periodic_topology.npz
master_boundary_curves.npz
standard_boundary_curves.npz
cgal_input/
    periodic3_master_features.txt
    cgal_case.txt
cgal_output/
    *_canonical_triangles.csv
    *_unplaceable_facets.csv
    *_1copy.mesh
    *_8copy.mesh
shell/
    *_shell.npz
    *_shell_report.json
    *_shell.obj
abaqus_meshcheck/
    *_meshcheck.inp
    *_periodic_pairs.csv
    *.dat
    *.msg
    *_datacheck_report.json
```

生产批处理建议：

- JSON report 保留；
- shell NPZ 保留；
- Abaqus INP/结果根据存储策略保留；
- `.mesh` / `.obj` 可视化文件可视情况删除；
- 已 PASS 的 checkpoint 不重复计算。

---

# 24. 当前项目状态快照

截至 2026-09-12：

```text
Periodic Surface Mesher v1.0
Status: VALIDATED
Fig.1 full regression: PASS
CGAL deterministic repeat test: PASS
Python final shell validator: PASS
Abaqus 2026 Standard Data Check: PASS
Step07 log validator: PASS
```

当前代码核心无需再无目的重构。

下一阶段推荐优先级：

1. 冻结 v1.0；
2. 建真实 Abaqus 物理模型层；
3. 验证 PBC 边/角节点方程没有过约束；
4. 加上下压板和接触；
5. 加真实材料/厚度；
6. 代表 case 网格收敛与准静态验证；
7. 再做 20–50 个随机曲面的 mesh robustness test；
8. 再进入 200+ / 23,534 样本批处理。

---

# 25. 给未来 AI 的最终操作约束

如果用户以后要求你“继续修改/重构这个项目”，请遵守：

- 先确认需求属于**网格核心**还是**外层物理/批处理模块**；
- 非必要不要改已经 PASS 的 01–07 核心；
- 不要重新采用 raw MC 作为 Abaqus 网格；
- 不要用普通 independent surface remesh 代替 Periodic_3，除非你能重新证明严格周期；
- 不要通过增大容差掩盖真实 mismatch；
- 不要逐顶点 modulo 周期坐标；
- 不要把 x=0 和 x=L FE 节点 merge；
- 不要看到 Abaqus `JOB COMPLETED` 就默认网格无警告，必须看 Step07；
- 不要把 Fig.1 的节点数/曲线数当新曲面的通用硬阈值；
- 任何核心改动都要用 Fig.1 全回归证明没有退化；
- 如果提出替代算法，必须明确它解决了哪个现有缺陷，并与 v1.0 在：周期性、拓扑、质量、确定性、Abaqus 接受性、批量鲁棒性上做对比。

**如果没有明确缺陷或新需求，最合理的选择是保留 v1.0 不动，在外层继续开发。**
