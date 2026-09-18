> **[SUPERSEDED 2026-09-16]** 本文件描述的旧架构（identity v2 / staging planner /
> 三层 schema / 旧 CLI / 旧配置文件）已被单目录流水线取代，本文件不再更新，内容仅作历史存档。
> 当前以 `README.md`、`AGENTS.md`、`docs/HANDOFF_CURRENT.md` 为准。

# Auto Abaqus 项目总体开发路线

## 1. 项目最终目标

本项目的长期目标不是机械复制某一篇论文中的所有参数，而是建立一套可复用的科研计算平台：

曲面/结构描述  
→ Python 自动生成周期网格  
→ Abaqus 自动建立有限元模型  
→ 自动 Data Check  
→ 自动求解  
→ 自动读取 ODB  
→ 自动进行数值与物理质量检查  
→ 输出标准化力学结果  
→ 支持后续批量有限元计算、参数研究和机器学习数据集构建。

论文中的曲面、材料参数、压缩比例、样本数量等主要作为当前开发和验证案例，而不是程序中的固定规则。

以后更换曲面方程、材料、压缩量、接触参数、输出变量、样本数量等，应主要通过配置文件完成，而不是修改主程序。

---

## 2. 总体架构

标准主链定义为：

```text
PREFLIGHT
    ↓
MESH
    ↓
MESH_QA
    ↓
MESH_DATACHECK
    ↓
BUILD
    ↓
PHYSICAL_DATACHECK
    ↓
SOLVE
    ↓
EXTRACT
    ↓
QA
    ↓
PUBLISH
```

其中：

- MESH：生成周期曲面有限元网格。
- MESH_QA：检查网格拓扑、周期对应关系和质量。
- MESH_DATACHECK：由 Abaqus 对网格输入进行验证。
- BUILD：根据网格和配置自动生成完整物理 Abaqus 输入文件。
- PHYSICAL_DATACHECK：检查完整材料、边界、PBC、接触、刚板、分析步等。
- SOLVE：正式调用 Abaqus Solver。
- EXTRACT：通过 Abaqus Python/odbAccess 提取结果。
- QA：判断计算是否完整、可信和可用于科研。
- PUBLISH：发布标准化结果或加入数据集。

---

## 3. 当前开发原则

当前阶段采用“纵向优先”原则。

不首先追求：

- 大规模批处理；
- 多任务并发；
- 多种材料模型；
- UMAT；
- n×n×n 多胞；
- 多种加载方式；
- 自动修改物理参数以提高收敛；
- 完整生产级调度系统。

首先建立一条最窄但完整、真实可运行的单案例链路。

即：

```text
已验证 mesh bundle
        ↓
完整 physical.inp
        ↓
Physical Data Check
        ↓
Abaqus Solve
        ↓
ODB
        ↓
自动提取
        ↓
QA
        ↓
标准结果
```

只有这一条链路真实跑通后，才向前接入自动网格，并向外扩展批量和恢复能力。

---

## 4. 模块边界

### 4.1 网格模块

`vendor/periodic_surface_mesher_v1.0` 为当前验证过的冻结模块。

除非发现明确缺陷，否则不得为了代码整洁、统一风格或未来扩展而重写。

其对后续系统的主要输出是标准 mesh bundle，例如：

```text
shell.npz
shell_report.json
periodic_pairs.csv
```

后续 Abaqus 模块不得依赖 CGAL 和网格算法内部实现。

### 4.2 Abaqus Build 模块

输入：

```text
mesh bundle
+ physics config
+ material config
+ numerics config
+ output config
```

输出：

```text
physical.inp
model_manifest.json
build_report.json
必要的 *.inc
```

BUILD 阶段只证明模型被正确生成，不代表 Abaqus 求解成功。

### 4.3 Abaqus runtime

Abaqus 始终作为独立外部运行时存在。

普通 Python/Pixi：

- 管理配置；
- 生成输入；
- 启动进程；
- 分析日志；
- 管理状态；
- 处理普通数据。

Abaqus Python：

- 使用 odbAccess；
- 读取 ODB；
- 执行只有 Abaqus 环境才能完成的操作。

不得把 Abaqus Python 环境与 Pixi Python 混合。

### 4.4 QA

必须区分：

```text
代码运行成功
≠
Abaqus正常结束
≠
达到目标加载
≠
数值结果可信
≠
科研样本可接受
```

每层必须留下独立证据。

---

## 5. 开发阶段

### M0：开发基线

保持当前已验证：

- Pixi 环境；
- frozen mesher；
- mesh contract；
- PBC；
- prepare-fe；
- history读取；
- 基础 QA；
- 状态记录。

原则上不再重新设计。

### M1：完整 Physical INP Writer

从已经验证的 mesh bundle 自动生成完整 Abaqus 模型。

包含：

- shell；
- sets；
- material；
- section；
- rigid platens；
- reference points；
- PBC；
- boundary conditions；
- contact；
- analysis step；
- amplitude/loading；
- output request。

退出条件：

仅根据 mesh bundle 和配置即可生成完整 `physical.inp`，无需人工进入 Abaqus/CAE。

### M2：Physical Data Check

Python 自动启动 Abaqus Data Check。

自动保存：

- 命令；
- 输入文件；
- 返回码；
- `.dat/.msg/.log`；
- Data Check 报告。

退出条件：

自动生成的模型能够被 Abaqus 独立验证，并能准确报告输入错误和严重初始化问题。

### M3：单作业自动求解

实现：

```text
Python
→ Abaqus launcher
→ solver
→ 完成/失败判断
```

退出条件：

无需人工点击 CAE，即可完成一个真实有限元作业并得到 ODB。

### M4：ODB 自动后处理

自动提取：

- 位移；
- 反力；
- 能量；
- 必要场变量；
- 接触信息；
- 元数据。

生成标准化原始结果。

### M5：单案例闭环 run-case

串联：

```text
BUILD
→ DATACHECK
→ SOLVE
→ EXTRACT
→ QA
```

首先使用已经验证的 mesh bundle。

退出条件：

输入一个配置，最终自动得到可信的力学响应结果。

### M6：接入自动网格

把已经成熟的：

```text
surface equation
→ mesh bundle
```

接到 M5 前面。

此时形成真正的：

```text
surface equation
→ mesh
→ Abaqus
→ result
```

全自动闭环。

### M7：可靠性工程

在真实失败样本基础上增加：

- failure classification；
- watchdog；
- heartbeat；
- bounded retry；
- resume；
- crash reconciliation。

自动重试不得偷偷修改：

- 材料；
- 厚度；
- 摩擦；
- PBC；
- 目标加载。

### M8：批量计算

逐级扩展：

```text
1
→ 5
→ 20~50
→ 200
→ 更大规模
```

根据真实 CPU、内存、许可证和磁盘使用情况决定并发数量。

不得在单案例闭环尚未稳定时直接大规模运行。

---

## 6. 配置化原则

科研变量必须尽可能与程序逻辑分离。

建议长期保持：

```text
case
material
physics
numerics
outputs
quality
environment
resources
```

例如：

`case`：曲面、尺寸、网格相关参数。

`material`：材料本构。

`physics`：边界条件、接触、加载目标。

`numerics`：分析步、时间增量、求解器设置。

`outputs`：history/field 输出。

`quality`：样本验收标准。

`environment`：Abaqus launcher 等机器相关信息。

`resources`：CPU、内存、并发和运行预算。

原则：

修改科研参数通常只修改配置，不修改 pipeline 核心代码。

---

## 7. 当前明确暂缓的工作

在单案例闭环建立以前，不优先开展：

- 大规模批处理；
- 高并发；
- 通用 UMAT 框架；
- 多胞模型；
- 三维 PBC；
- 大量材料模型；
- GUI 自动点击；
- CAE replay 自动化；
- 复杂自适应重试；
- 过度抽象的插件系统。

这些均可在已有主链稳定以后扩展。

---

## 8. 开发纪律

每一阶段遵循：

```text
设计
→ 实现
→ 静态检查
→ 自动测试
→ 真实案例验证
→ 保存证据
→ 再进入下一阶段
```

不得把：

“代码存在”

描述成：

“功能已经真实验证”。

所有真实运行必须使用新的 attempt 目录，不覆盖旧成功或失败结果。

旧结果是验证证据，不是临时文件。

---

## 9. 当前最近目标

当前唯一主目标：

# M4：ODB 自动提取与结果 QA

M1/M2/M3 均已完成（2026-09-15）：Fig.1 自动 physical.inp 通过真实 Abaqus 2026 Data Check（COMPLETED_WITH_WARNINGS）并完成真实 20% 自动求解（`work/fig1_solve_m3_20pct_003`：SOLVE_COMPLETED_WITH_WARNINGS，target step time 达标，完整 ODB）。当前下一目标：**M4 ODB 自动提取与结果 QA**（2026-09-16 曾对 5 个已有 ODB 做过 ad-hoc/read-only history diagnostic，见 `docs/EXPERIMENT_30_SURFACES_20260915.md`，但不构成 M4 进展）。30% 压缩验收、准静态判定与接触/PBC 科学检查属于 M4/后续阶段。

暂不扩大问题范围。

M1/M2/M3 已完成并通过真实 Abaqus 验证后，下一阶段进入 M4 ODB 提取与结果 QA。

---

## 10. 最终判断标准

项目真正成功，不是“写出了很多自动化代码”，而是做到：

```text
给定一个新的合法曲面和一组科研参数

无需人工进入 Abaqus/CAE

程序能够自动：

生成网格
→ 建模
→ 检查
→ 求解
→ 提取
→ QA
→ 输出结果

并且任何失败都能够被定位和保留证据。
```

这是本项目所有后续开发工作的最高优先级。