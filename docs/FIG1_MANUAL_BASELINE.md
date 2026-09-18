# Fig.1 手动 Abaqus 基准模型与性能记录

> 本文件记录用户在 Abaqus/CAE 2026 中**手动建立并真实求解成功**的 Fig.1 模型设置与运行数据。
> 用途：
>
> 1. 自动化模型回归参考；
> 2. Standard / Explicit 比较；
> 3. 性能排查（为什么自动化比手动慢）；
> 4. 后续修改参数时判断是否偏离手动成功基准。
>
> 它是"**本项目手动成功基准**"，**不是**声称完全复现论文作者未公开的所有 Abaqus 设置。
> 所有数字都来自本机真实文件（路径见文末"证据"），不是记忆值；记忆与文件冲突时以文件为准。

---

## 1. 手动模型身份

| 项目 | 值 | 证据 |
|---|---|---|
| Abaqus | **2026** | `Fig1_Compression.log`："Abaqus 2 0 2 6" |
| Model | `Fig1_Physical` | INP 第 3 行注释 `** Job name: Fig1_Compression Model name: Fig1_Physical` |
| Job | `Fig1_Compression` | LOG / MSG / STA 文件名与内容 |
| 实际求解内容 | **20% compression** | 压缩步 `RP_TOP, 3, 3, -2.`，单胞高 10 mm → 2/10 = 20% |

**关于 "30%" 文字**：手动 INP 的 Heading 与步说明仍写着

```text
*Heading
 Fig1 periodic shell 30% compression
*Step, name=Compression, nlgeom=YES, inc=10000
30% quasi-static compression
```

但真正参与求解的边界条件只有 `RP_TOP U3 = -2.0 mm`（单胞高 10 mm）→ **实际是 20% 压缩**。
description 只是文字，不参与求解；不要用 Heading 文字判断压缩量。

---

## 2. Geometry / Mesh

| 项目 | 值 |
|---|---|
| unit cell | 10 × 10 × 10 mm |
| shell nodes | **9483** |
| shell elements | **18164** |
| element | **S3R** |
| 手动 shell thickness | **0.32825 mm** |
| 当前自动化精确厚度 | **0.3282473906809612 mm** |
| 两者差别 | 约 **0.0008 %** → 视为同一物理厚度 |
| shell section 积分点 | **5** |

INP 原始行：

```text
*Element, type=S3R
*Elset, elset=EALL, generate
     1,  18164,      1
*Shell Section, elset=EALL, material=DemoPolymer
0.32825, 5
```

说明：这是**后期正式 periodic mesh**（周期网格），不是早期 raw Marching Cubes 网格。
自动化侧同一 mesh 的指纹：`fig1_shell.npz` sha256 `ef9197791cbdd5cbfb05d64f1367137279fc09daeafba1ca871c08f1bf5c74ec`。

---

## 3. Material

名称 `DemoPolymer`：

```text
*Density
 1.1e-09,
*Elastic
484., 0.4
*Plastic
   8.,    0.
  9.5,  0.02
  11.,  0.05
 12.5,  0.08
 13.5,  0.11
 14.2, 0.147
 14.5,   0.2
  15.,   0.3
 15.6,   0.5
 16.3,   0.8
  17.,   1.2
  18.,    2.
```

| 量 | 值 |
|---|---|
| Density | 1.1e-9 tonne/mm³ |
| Young's modulus | 484 MPa |
| Poisson ratio | 0.4 |
| Plastic | 12 行真应力–塑性应变 |

**第二列是 plastic strain（塑性应变）**，第一列是 yield stress（MPa）。
（INP 里另有一个 `MESH_CHECK_MAT`：`*Elastic 1., 0.3`，只用于网格检查 INP，不属于物理模型。）

---

## 4. Rigid platens

| 项目 | 值 |
|---|---|
| plate size | **18 × 18 mm**（节点坐标 −9 … +9） |
| element | **R3D4** |
| mesh size | **1.0 mm** |
| Bottom RP | **(5, 5, 0)** |
| Top RP | **(5, 5, 10)** |
| RP_X_CTRL | **(15, 5, 5)** |
| RP_Y_CTRL | **(5, 15, 5)** |

INP 结构：`*Part, name=RigidPlate`（局部坐标 −9…+9，节点 1/2/3…，参考点 362 为内部 RefPt），装配时

```text
*Instance, name=BottomPlate, part=RigidPlate
           5.,           5.,           0.
*Instance, name=TopPlate, part=RigidPlate
           5.,           5.,          10.
*Node
      1,          15.,           5.,           5.        → RP_X_CTRL
*Node
      2,           5.,          15.,           5.        → RP_Y_CTRL
```

板宽比：18/10 = **1.8**（与自动化 `platen.width_factor = 1.8` 一致）。

---

## 5. Periodic boundary conditions

| 项目 | 值 |
|---|---|
| 周期节点对（本 mesh） | **X pairs = 141，Y pairs = 148，Z pairs = 124**（合计 413） |
| 本压缩模型实际使用 | **只用 X / Y lateral PBC**（Z 不使用） |
| raw lateral relations | 141 + 148 = **289** |
| spanning forest 删除 | **2** 条 redundant relations |
| independent relations | **287** |
| 每个 S3R 周期约束自由度 | **DOF 1–6**（含转动） |
| 方程约束总数 | 287 × 6 = **1722** |

证据：手动 INP 中

- `*Equation` 块数 = **1722**（精确计数）；
- `*Nset, nset=PBCN_*` 周期节点集 = **570** 个；
- 最后一条约束注释为 `** Constraint: PBC_EQ_00287_DOF6`。

**Z 方向不施加 PBC**：Z 是上下压板压缩方向。
（Z pairs = 124 是 mesh 自身的周期配对数量，仅说明周期拓扑存在；压缩模型不把它们写成约束。）

宏观横向自由度：

```text
RP_X_CTRL.U1
RP_Y_CTRL.U2
```

这两个控制节点**不额外施加 guide BC**（只有 `*Boundary` 中的 bottom fixed 与 top guide，见 §6）。

---

## 6. Boundary conditions

初始（`*Step` 之前）：

```text
** Name: BC_BOTTOM_FIXED Type: Displacement/Rotation
*Boundary
RP_BOTTOM, 1, 1
RP_BOTTOM, 2, 2
RP_BOTTOM, 3, 3
RP_BOTTOM, 4, 4
RP_BOTTOM, 5, 5
RP_BOTTOM, 6, 6
** Name: BC_TOP_GUIDE Type: Displacement/Rotation
*Boundary
RP_TOP, 1, 1
RP_TOP, 2, 2
RP_TOP, 4, 4
RP_TOP, 5, 5
RP_TOP, 6, 6
```

- Bottom：`RP_BOTTOM` U1 = U2 = U3 = UR1 = UR2 = UR3 = 0（全固定）
- Top guide：`RP_TOP` U1 = U2 = UR1 = UR2 = UR3 = 0；**初始 U3 自由**
- 压缩步内：

```text
*Boundary, amplitude=AMP_COMPRESSION
RP_TOP, 1, 1
RP_TOP, 2, 2
RP_TOP, 3, 3, -2.
RP_TOP, 4, 4
RP_TOP, 5, 5
RP_TOP, 6, 6
```

即 **U3 = −2.0 mm → 20% compression**。

---

## 7. Contact

```text
*Surface Interaction, name=ContactProp
1.,
*Friction, slip tolerance=0.005
 0.6,
*Surface Behavior, pressure-overclosure=HARD
*Contact
*Contact Inclusions, ALL EXTERIOR
*Contact Property Assignment
  ,  , ContactProp
```

| 项目 | 值 |
|---|---|
| 形式 | **General Contact**（`*Contact`） |
| 域 | `ALL EXTERIOR` → **包含 self contact**（双面 facet） |
| Normal | **Hard Contact** |
| Separation | **allowed**（未写 `no separation`） |
| Tangential | Penalty friction |
| friction coefficient | **0.6** |
| Standard slip tolerance | **0.005**（Standard 专属；Explicit 不接受该参数） |
| 可选表面标量行 | `1.,`（2D / node-based pair 用；3D element-based 不适用，自动化故意省略） |

---

## 8. Standard Step

```text
*Step, name=Compression, nlgeom=YES, inc=10000
30% quasi-static compression
*Dynamic,application=MODERATE DISSIPATION,initial=NO
0.001,1.,1e-08,0.02
```

| 项目 | 值 |
|---|---|
| procedure | **Dynamic, Implicit** |
| NLGEOM | **YES** |
| application | **MODERATE DISSIPATION** |
| initial acceleration | **NO** |
| time period | **1.0 s** |
| initial increment | 0.001 s |
| minimum increment | 1e-8 s |
| **maximum increment** | **0.02 s** |
| maximum increments | 10000 |

**关于 maximum increment = 0.02**：早先曾怀疑手动模型的 maximum increment 不是 0.02；
现已由真实 INP 数据行 `0.001,1.,1e-08,0.02` 与 STA（后段增量稳定在 0.02000）**双重证实就是 0.02**。

---

## 9. Loading

```text
*Amplitude, name=AMP_COMPRESSION, definition=SMOOTH STEP
             0.,              0.,              1.,              1.
```

- 形状：**Smooth Step**
- 作用对象：`RP_TOP U3 = −2 mm`（`*Boundary, amplitude=AMP_COMPRESSION`）
- 时间尺度：0 → 1.0 s（与 step time period 一致）

---

## 10. Output

```text
*Restart, write, frequency=0
*Output, field, variable=PRESELECT, frequency=50
*Output, history, frequency=1
*Energy Output
ALLAE, ALLIE, ALLKE, ALLPD, ALLWK, ETOTAL
*Node Output, nset=RP_TOP
RF3, U3
*Node Output, nset=RP_X_CTRL
U1,
*Node Output, nset=RP_Y_CTRL
U2,
*Output, history, variable=PRESELECT
```

| 项目 | 手动基准 | 自动化（当前） | 性质 |
|---|---|---|---|
| field | `variable=PRESELECT, frequency=50` | 同 | 一致 |
| history 基础频率 | `frequency=1` | 同 | 一致 |
| energy | ALLAE, ALLIE, ALLKE, ALLPD, ALLWK, ETOTAL | 同 | 一致 |
| 节点历史 | RP_TOP RF3/U3；RP_X_CTRL U1；RP_Y_CTRL U2 | 同 | 一致 |
| restart | `*Restart, write, frequency=0`（不写 restart） | 同 | 一致 |
| 额外 PRESELECT history | `*Output, history, variable=PRESELECT`（未写 frequency → 默认 1） | 明确写成 `frequency=10` | **仅输出频率细节差异，不是物理模型差异** |

---

## 11. 手动成功 Job 的真实求解统计

来自 `Fig1_Compression.log` / `.sta` / `.msg`（同一 Job，2026-09-12 19:17–19:28）：

| 项目 | 实测值 | 来源 |
|---|---|---|
| status | `THE ANALYSIS HAS COMPLETED SUCCESSFULLY` | STA / LOG `Abaqus JOB Fig1_Compression COMPLETED` |
| successful increments | **59** | MSG "TOTAL OF 59 INCREMENTS"；STA 59 行 |
| cutbacks | **1** | MSG "1 CUTBACKS IN AUTOMATIC INCREMENTATION"（STA 中一处 ATT 列 = 2） |
| nonlinear iterations | **241** | MSG "241 ITERATIONS INCLUDING CONTACT ITERATIONS" |
| equation solver passes | **241**（其中 241 次含矩阵分解） | MSG 紧随其后的 4 行 |
| STA 行内合计 iters | 231（severe discontinuity 140 + equilibrium 91） | STA 列求和；与 MSG 的 241 计数口径不同 |
| warning / error | 10 input processing + 7 analysis warnings，**0 error** | MSG ANALYSIS SUMMARY |
| 末增量 | Δt = 9.117e-3，2 severe discontinuity + 8 equilibrium iters | STA 第 59 行 |
| final step time | **1.0**（= target） | STA "1 59 1 2 8 10 1.00 1.00 0.009117" |
| equations | **55190** | MSG "NUMBER OF EQUATIONS: 55190" |
| ODB | `Fig1_Compression.odb`，16,897,560 bytes | 文件 |

时间（LOG 原始行）：

```text
Begin Analysis Input File Processor   2026/9/12 19:17:47
Run pre.exe                           2026/9/12 19:17:53
End Analysis Input File Processor
Begin Abaqus/Standard Analysis        2026/9/12 19:17:53
Run standard.exe                      2026/9/12 19:28:29
End Abaqus/Standard Analysis
Run SMASimUtility.exe                 2026/9/12 19:28:29 → 19:28:30
Abaqus JOB Fig1_Compression COMPLETED
```

| 时间量 | 值 |
|---|---|
| input processor (pre.exe) | **6 s** |
| **standard.exe wall time** | **636 s ≈ 10.6 min** |
| SIM wrap-up | 1 s |
| whole Job | **≈ 10.7 min** |
| MSG JOB TIME SUMMARY wallclock | 634 s |
| USER TIME / SYSTEM TIME / TOTAL CPU | ≈ 2.E+03 / ≈ 2.E+02 / ≈ 2.E+03 s（MSG 只给 1 位有效数字） |
| CPU ÷ wallclock | ≈ 3.2 … 3.5（4 threads 上限 4.0） |
| license | "Abaqus/Standard checked out 8 tokens"（LOG 原文） |

**必须明确记录**：目前找到并核实的这一组成功手动 Fig.1 20% Job **不是"不到 8 分钟"**，真实文件证据是
**standard.exe ≈ 636 s ≈ 10.6 min**。
如果以后找到另一份真正 < 8 min 的 Job，再追加为**另一组**性能记录，
**不要用记忆覆盖真实日志**。

---

## 12. 手动 Job 并行设置

MSG 第 123 行起的真实并行配置：

```text
ELEMENT OPERATIONS WILL BE CARRIED OUT IN PARALLEL USING   4 THREADS ON 1 DOMAIN
PARALLEL CONTACT TRACKING ENABLED
PARALLEL ASETI ENABLED
PARALLEL CONTACT VALID VS INVALID ENABLED
PARALLEL CONTACT ASSIGNING ENABLED
PARALLEL CONTACT DB STORE ENABLED

     INITIAL ELEMENT LOAD BALANCE
            DOMAIN    1     THREAD    NUMBER OF ELEMENTS
                              1            4608
                              2            4864
                              3            4864
                              4            4804
      SPARSE STORAGE WAS USED FOR NODAL DATA ON WORKER THREADS

	UNSYMMETRIC HYBRID DIRECT SPARSE SOLVER RUNNING ON
	1 HOST x 1 MPI RANK PER HOST x 4 THREADS PER RANK
        NUMBER OF EQUATIONS:  55190
        NUMBER OF RHS:        1
        NUMBER OF FLOPS:      9.410e+09
        SOLVER ELAPSED TIME:  364ms
```

| 项目 | 手动基准 |
|---|---|
| element operations | **并行，4 threads on 1 domain** |
| contact（tracking / ASETI / valid-vs-invalid / assigning / DB store） | **全部并行启用** |
| equation solver | **1 host × 1 MPI rank per host × 4 threads per rank** |
| MPI ranks / domains | 1 / 1 |
| 每线程元素数（初始 load balance） | 4608 / 4864 / 4864 / 4804 |

因此这一成功手动 Job 的执行行为相当于：

```text
cpus = 4
standard_parallel = all
```

**核心经验**：手动 Job 不仅 equation solver 并行，**element operations 也并行**。

对照：项目此前自动化 runtime 用的是

```text
cpus = 4
standard_parallel = solver
```

其 MSG 第 123 行是：

```text
ELEMENT OPERATIONS WILL NOT BE CARRIED OUT IN PARALLEL
```

即**只有方程求解器并行，element operations 串行**。这是当前认为自动化 Standard 变慢的**主要性能嫌疑**。

---

## 13. 性能经验

同一模型、同一增量序列：

| 配置 | element ops | MSG wallclock | USER / SYSTEM / TOTAL CPU | solver passes |
|---|---|---|---|---|
| 手动 4 threads + element parallel | **parallel** | **634 s** | ≈2.E+03 / ≈2.E+02 / ≈2.E+03 | 241 |
| 旧自动化 `cpus=4, standard_parallel=solver` | **NOT parallel** | **984 s** | ≈1.E+03 / ≈9.E+01 / ≈1.E+03 | 243 |

（旧自动化数据来自 `work/fig1_solve_m3_20pct_003/fig1_m3_solve.msg`：同样是 "1 HOST x 1 MPI RANK x 4 THREADS"，
wallclock 984 s；`.sta` 也是 59 increments / 1 cutback / 243 passes。）

按 MSG 的 solver statistics：sparse direct solver 每次 **0.35–0.47 s**（抽样 359 / 364 / 377 / 378 / 380 / 388 /
391 / 393 / 396 / 402 / 403 / 407 / 409 / 410 / 436 ms），平均约 **0.39 s**。
241 次累计约 **94 s**；而完整 Standard wallclock ≈ **634–636 s**。

即：**direct sparse solver 只占总时间的 ~15% 量级**。其余大量时间属于：

- element calculations
- material update
- General Contact（tracking / assigning / DB store）
- contact 状态判断
- assembly
- constraints（1722 equations）
- nonlinear iteration

因此本模型应优先使用：

```text
standard_parallel = all
```

而不是只设置 `standard_parallel = solver`。**这条是本模型最重要的性能经验。**

---

## 14. 自动化与手动基准的一致性

当前自动化 Fig.1 Standard baseline 与手动成功模型在下列核心项目一致：

| 项目 | 手动 | 自动化 | 判定 |
|---|---|---|---|
| mesh | 9483 nodes / 18164 S3R | 同（npz sha256 见 §2） | 一致 |
| material | DemoPolymer 1.1e-9 / 484 / 0.4 / 12 行 plastic | 同 | 一致 |
| element / section | S3R + 5 integration points | 同 | 一致 |
| shell thickness | 0.32825 mm | 0.3282473906809612 mm（差 0.0008%） | 只有极小舍入差 |
| rigid platens | R3D4, 18×18 mm, 1 mm 网格, RP (5,5,0)/(5,5,10) | 同 | 一致 |
| PBC | X/Y lateral，DOF 1–6，1722 equations | 同（287 relations × 6） | 一致 |
| BC | bottom fixed + top guide + U3 = −2 mm | 同 | 一致 |
| Contact | General Contact ALL EXTERIOR + friction 0.6 + slip tolerance 0.005 | 同 | 一致 |
| Step | Dynamic Implicit, NLGEOM=YES, MODERATE DISSIPATION | 同 | 一致 |
| time period / increments | T=1.0, 0.001 / 1e-8 / 0.02 / 10000 | 同 | 一致 |
| Loading | Smooth Step，U3 = −2 mm（20%） | 同 | 一致 |
| Output | field 50 / history 1 / energy 6 变量 / 4 组节点输出 | 同（preselect history 频率 10 vs 默认） | 一致（细节差异） |

因此以后出现**结果差异**或**运行时间差异**，优先检查：

```text
CPU
standard_parallel
mp_mode
memory / runtime
Abaqus execution settings
```

而**不是**首先修改物理模型。

---

## 15. 证据

| 内容 | 路径 |
|---|---|
| 手动 INP（Model `Fig1_Physical`） | `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.inp`（1,152,781 bytes，38,602 行） |
| 手动 LOG（pre/standard/SIM 时间） | `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.log` |
| 手动 MSG（并行、solver stats、summary、job time） | `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.msg`（599,135 bytes） |
| 手动 STA（59 increments / 1 cutback） | `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.sta` |
| 手动 DAT / ODB | `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.dat` / `.odb`（16,897,560 bytes） |
| 手动期 ingredients 记录（9483 / 18164 / 1722 / thickness） | `work/takeover_20260913_01/fe_inputs/model_inputs.json` |
| 周期配对（X 141 / Y 148 / Z 124） | `work/audit_std/fig1/mesh/engine/cases/fig1/abaqus_meshcheck/fig1_periodic_pairs.csv` |
| PBC 287 relations / 1722 equations | `work/audit_std/fig1/abaqus/ingredients/pbc_map.json` |
| 旧自动化 4/solver MSG（element ops NOT parallel, 984 s） | `work/fig1_solve_m3_20pct_003/fig1_m3_solve.msg` |
| 冻结 Standard deck 指纹 | `tests/fixtures/fig1_20pct_regression/deck_sha256.json` |

约定：`reference/`、`baseline_test/`、已有 `work/` attempt 均为**只读历史证据**，本文件只引用，不修改。

