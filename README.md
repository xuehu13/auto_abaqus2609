# Abaqus 周期曲面自动建模与计算流水线

面向周期多孔曲面结构的自动化 Abaqus/Standard 流水线：
曲面方程 → 周期网格 → 物理模型生成 → 真实 Abaqus Data Check → 真实单作业 Solve
→（下一阶段）ODB 提取与力学 QA。

## 项目简介

本仓库包含一套 Python 驱动的自动化流水线，在不打开 Abaqus/CAE 的情况下完成周期曲面
结构（单胞壳）在两块刚板之间单轴压缩的建模与求解。每个阶段运行在独立的、不可覆盖的
attempt 目录中，产出结构化 JSON 报告与原始 Abaqus 证据；每一个成功与失败都可追溯。

代码与报告的工作语言为英文；项目文档以中文为主（技术术语保留英文）。

## 项目目的与背景

本项目源于对扩散式力学超材料研究中"仿真/数据生成"工作流的学习与部分复现：周期多孔
曲面壳在两块刚性压板之间单轴压缩，横向施加周期边界条件（PBC），接触采用 General
Contact。

项目目标**不是**逐项复制源论文的每个材料参数、压缩目标或实现细节，而是建立一套健壮、
可复用的 Abaqus 自动化流水线，支撑后续多曲面研究与数据集生成。一个已验证的手工模型
（`Fig1_Compression.inp`，20% 压缩）作为 keyword 语义 baseline；一个验证算例（Fig.1）
已端到端跑通整条自动化链。

## 当前已经实现的功能

以下功能已在开发工作站（Abaqus 2026）上实现并真实验证：

- 周期网格准备（冻结的 `vendor/periodic_surface_mesher_v1.0` 流水线）与网格契约校验。
- 完整物理模型生成：壳网格、材料/截面、刚板与参考点、边界条件、横向 XY 周期边界
  方程、General Contact、Dynamic Implicit 压缩分析步与输出请求——装配为顶层
  `physical.inp`，并通过仓库自有的 13 项静态检查。
- 生成 deck 的真实 Abaqus Physical Data Check（Fig.1：0 error，10 条 warning 保留）。
- 通过 Data Check 的 deck 的真实 Abaqus/Standard 单作业 Solve（Fig.1 20% 验证算例：
  完成、target step time 达标、0 error、17 条 warning 保留、产出 ODB artifact）。
- 30 个差异曲面的阶段性自动验证（mesh → build → Data Check 泛化验证，见下文
  "30曲面阶段性验证"）。

## 当前尚未实现的功能

- ODB 提取 / 结果 QA（M4）——已完成的 solve ODB 尚未被读取。
- 30% 压缩验收（后续验证目标；早期手工 30% 尝试未收敛，见 `docs/TROUBLESHOOTING.md`）。
- 批量/多曲面执行框架、重试/watchdog/恢复、数据集导出（M7/M8）。
- UMAT、n×n×n 多胞、3D PBC——当前有意不做。

本阶段 `dataset_eligible` 恒为 `false`。

## 整体流程

```
surface equation/config
        |  prepare-mesher (frozen CGAL mesher)      [implemented]
        v
periodic mesh (shell.npz + report + pairs.csv)
        |  mesh QA / contract validation            [implemented]
        v
        |  build-physical                           [implemented]
        v
physical.inp + blocks/ + ingredients/ + model_manifest.json
        |  repository static validation (13 checks) [implemented]
        v
        |  datacheck (real Abaqus)                  [implemented]
        v
datacheck_report.json (accepted deck)
        |  solve (real Abaqus/Standard)             [implemented]
        v
solve_report.json + ODB artifact
        |  M4: ODB extraction                       [NEXT]
        v
histories / fields / metadata
        |  M4+: mechanics QA, curve QA              [planned]
        v
stress-strain curve, standardized results
        |  future: multi-surface batch, ML          [future]
```

## 仓库结构

| 路径 | 内容 |
|---|---|
| `run.py` | CLI 入口（`pixi run cli <command>`） |
| `pipeline/` | 自动化模块（builder、datacheck、solve、PBC、QA、state 等） |
| `abaqus_worker/` | 仅由 Abaqus Python 运行的 worker 脚本（M4，尚未接入） |
| `config/` | 示例配置（`*.example.json`）与机器本地配置（`*.local.json`，git-ignored） |
| `tests/` | 单元测试（全部为合成 fixture；不依赖真实 Abaqus 或真实 Fig.1 结果） |
| `docs/` | 项目文档（见"文档索引"） |
| `vendor/periodic_surface_mesher_v1.0/` | 冻结的已验证周期曲面网格程序（禁止修改） |
| `scripts/` | Pixi 任务包装与迁移边界测试 |
| `work/<attempt>/` | 每次运行一个不可变目录（git-ignored） |

## 环境要求

- Windows，以及一套 Abaqus/Standard 安装。实际验证过的版本是 Abaqus 2026；其他版本未测试。
- 可用的 Abaqus launcher：`abaqus.bat`/`abq2026.bat` 在 PATH 上，或在
  `config/environment.local.json` 中配置（见下文 runtime 配置）。
- [Pixi](https://pixi.sh) 管理 Python 环境（`pixi.toml` + `pixi.lock` 定义一切；无需
  Conda activation——历史 Conda 工作流保留在 `docs/HISTORICAL_v0.1_README.md`）。
- 网格生成需要冻结 mesher 所需的 CGAL 工具链（`pixi run build-cgal --check-only` 可检查）。

## Pixi Python 与 Abaqus Python

两个 runtime，绝不可混用：

- **Pixi Python**（`default` 环境）：全部流水线代码、配置、JSON 报告、staging 与进程启动。
- **Abaqus Python**（Abaqus 自带）：仅用于 ODB 访问与 Abaqus 内部任务（`abaqus_worker/`，M4）。

流水线绝不把 odbAccess 导入 Pixi Python，也绝不把自己的环境注入 Abaqus。两个 runtime
之间只通过 attempt 目录内的文件交换数据。

## 快速开始

```powershell
pixi run check        # 校验三个 Pixi 环境
pixi run test         # 运行测试套件（合成 fixture，不涉及 Abaqus）
pixi run plan         # 打印流水线阶段与实现状态
pixi run cli-help     # 列出全部 CLI 命令
```

真实 Abaqus 链（每个 `--out` 必须是**新目录**）：

```powershell
pixi run cli build-physical --npz <shell.npz> --report <report.json> --pairs <pairs.csv> --out work/<new-attempt>
pixi run cli datacheck --build-dir work/<build-attempt> --out work/<new-attempt>
pixi run cli solve --datacheck-dir work/<datacheck-attempt> --out work/<new-attempt>
```

`build-physical` 需要冻结 mesher 流水线产出的已验证网格 bundle
（`shell.npz` + `shell_report.json` + `periodic_pairs.csv`）。

## 配置文件

| 文件 | 用途 |
|---|---|
| `config/cases/fig1.json` | 已验证 baseline 曲面的 case 定义 |
| `config/physics.example.json` | 边界模式、PBC、接触、压板、压缩目标、分析步时间 |
| `config/materials/demo_surrogate.json` | 材料定义（demo surrogate，非生产数据） |
| `config/numerics.example.json` | Procedure、增量、stabilization 策略（分析步数值） |
| `config/outputs.example.json` | ODB 输出请求（restart/field/history） |
| `config/quality.example.json` | 曲线 QA 策略草稿（M4 起使用） |
| `config/environment.example.json` | Abaqus launcher 与版本要求（机器本地） |
| `config/datacheck_runtime.example.json` | Data Check 执行策略（cpus、standard_parallel） |
| `config/solve_runtime.example.json` | Solve 执行策略（cpus、standard_parallel） |

`*.example.json` 是纳入版本管理的可移植模板。复制为同名 `.local.json`（该后缀被
git-ignored）即可配置本机。runtime 策略解析顺序：CLI 参数 → `*.local.json` → 内置
safe default。本地配置永不进入仓库。

## 单曲面标准流程

1. `prepare-mesher` → 运行冻结的 CGAL mesher → `mesh-post`/`mesh-check`，
   得到已验证网格 bundle。
2. 用 bundle 与 physics/material 配置运行 `build-physical` → 静态验证通过的
   `physical.inp` 与 `model_manifest.json`。
3. 用 build attempt 运行 `datacheck` → 由 Abaqus 本身判定 deck
   （`DATACHECK_PASSED` 或 `DATACHECK_COMPLETED_WITH_WARNINGS` 均算接受；
   两者都要求 `ANALYSIS DATACHECK COMPLETE` 标记且 0 error）。
4. 用 datacheck attempt 运行 `solve` → 真实分析；完成判定依据：
   return code + 指名本作业的 stdout 完成 token + `.sta` 完成标记
   （`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`）+ 达到 target step time + ODB 非空。

## attempt 与结果目录

**核心不变量：已存在的 attempt 目录永不被覆盖、永不被清理。**

- 每次运行必须使用新的 `work/<attempt>` 目录；目标目录已存在时直接报
  `OUTPUT_EXISTS` 并拒绝执行（有测试锁定）。
- 失败的 attempt（包括误判、中断实验、意外重复运行）逐字保留，任何结论都应能从
  原始 `.dat/.msg/.sta/.odb` 文件与报告重新推导。
- **partial ODB 不是成功结果**：solve 只有在 `.sta` 完成标记 + stdout 完成 token +
  target step time 达标 + ODB 非空同时满足时才判 `SOLVE_COMPLETED*`。被外部中断
  （例如系统重启）留下的部分 ODB 一律视为无效 solve 证据。

## runtime 配置

- Data Check 执行策略：`config/datacheck_runtime.example.json`（本机覆盖：
  `config/datacheck_runtime.local.json`）。
- Solve 执行策略：`config/solve_runtime.example.json`（本机覆盖：
  `config/solve_runtime.local.json`）。
- 内置 safe default 为 `cpus=1, standard_parallel=solver`；开发工作站验证过的
  preferred profile 为 `cpus=4, standard_parallel=solver`。
- 已知机器特定问题：默认 `standard_parallel=all` 在本机 General Contact
  preprocessing 中可复现触发 threads-per-domain ERROR。详见
  `docs/TROUBLESHOOTING.md`（含 HIGH-PRIORITY DEFERRED PERFORMANCE DEBT 登记与
  后续实验方案）。

## 当前验证结果

- **M1**（physical INP writer）：DONE——真实 Fig.1 网格 bundle 冒烟通过，13/13 静态
  检查 PASS（`work/fig1_build_m17_smoke_001`）。
- **M2**（Physical Data Check）：DONE——自动 `physical.inp` 通过真实 Abaqus 2026
  Data Check：0 error / 10 warnings 保留（`work/fig1_datacheck_m2_final_001`）。
- **M3**（单曲面 Solve）：DONE——20% 验证算例真实求解完成：
  `SOLVE_COMPLETED_WITH_WARNINGS`、last_step_time=1.00=target、0 error、17 warnings
  保留、完整 ODB（`work/fig1_solve_m3_20pct_003`，cpus=4, standard_parallel=solver）。
- M2 的 10 条 warning（General Contact double-sided facets、STRAINFREE 调整比例、
  主面两侧 8 组相邻 secondary nodes）与 solve 的 7 条 zero-moment warning
  **保留为 M4 的 QA 义务**——未白名单，未证明无害。

## 30曲面阶段性验证（2026-09-15/16）

使用 `reference/selected_30_diverse_cases_report.md` 中挑选的 30 个明显不同的周期曲面
方程，在统一 20% physics 配置下运行自动化链的阶段性实验：

- **30 个曲面进入自动化测试**。
- **28 / 30 自动网格通过**（ref30_01：stage05 周期性校验未过；ref30_22：CGAL 崩溃）。
- **28 / 28 physical build 通过**。
- **28 / 28 Abaqus Data Check accepted**（0 个 Data Check 失败）。
- 4 个进入真实 Solve，**0 个完成**：
  - ref30_02：收敛停滞后人工终止（step time ≈0.312，增量缩至 ~1e-7）；
  - ref30_03：TOO MANY ATTEMPTS（step time ≈0.39 中断，2 errors）；
  - ref30_04：收敛停滞后人工终止（step time ≈0.532）；
  - ref30_05：推进到 step time ≈0.979 时被 **Windows Update（KB5129195）强制重启中断**。
- **本次实验没有得到完整有效 ODB**；ref30_05 的部分 ODB 无完成标记，不作为成功结果。

结论：这证明 **mesh → build → Data Check 已经在一组明显不同的曲面上得到初步泛化
验证**；但正式 batch/recovery framework 尚未完成，solve 层面的收敛性与失败分类仍待
M4 之后的系统研究。实验详情见 `docs/EXPERIMENT_30_SURFACES_20260915.md`。

## 已知限制

- 单胞、仅横向 XY PBC；无 3D PBC、无 n×n×n。
- demo surrogate 材料——非实验标定数据。
- M2/M3 warnings（接触初始化、zero moment）在任何科学使用前需要力学 QA。
- 30% 压缩目标在自动化中未验证（历史手工 30% 尝试未收敛；见
  `docs/TROUBLESHOOTING.md`）。
- 无 ODB 提取、无 batch、无 retry/watchdog；solve 超时会留下不完整的结构化证据
  （登记为 M7 技术债）。
- 仅在开发工作站（Abaqus 2026）与 Fig.1 20% 验证算例上验证；其他机器/版本/算例未测试。
- 30 曲面实验中 4 个 solve 尝试均未完成（收敛停滞 ×2、数值失败 ×1、外部重启中断 ×1）；
  失败分类见 `docs/TROUBLESHOOTING.md`。

## 故障排查

见 `docs/TROUBLESHOOTING.md`——本项目真实失败案例及其诊断路径与当前状态：并行
preprocessing 失败、被证伪的 `jleConfig` 假设、`.sta` parser bug、Data Check warning
签名、solve timeout 注意事项、30曲面临时 runner 的 double-reserve bug、Windows Update
强制重启事件、difficult solve cases，以及失败运行如何诊断与保全。

## 历史开发记录

开发与调试历史被有意完整保留——包括失败假设、30% 非收敛记录、重复 solve 事件与
parser 误判：

- `docs/HISTORICAL_v0.1_README.md` —— 完整的被取代 v0.1 README。
- `docs/HANDOFF_CURRENT.md` —— 当前接管快照。
- `docs/PROJECT_STATUS.md` —— 已验证工程事实与证据分级。
- `docs/IMPLEMENTATION_STATUS.md` —— 逐里程碑实现历史。
- `docs/IMPLEMENTATION_PLAN.md` —— 计划中、进行中与延后的工作。
- `docs/LOCAL_ENVIRONMENT.md` —— 开发机证据（`[LEGACY]` Conda 章节为复现而保留；
  当前工作流仅用 Pixi）。
- `docs/TROUBLESHOOTING.md` —— 失败与调试经验。
- `docs/EXPERIMENT_30_SURFACES_20260915.md` —— 30曲面阶段性验证实验记录。

## 路线图

M0 环境/baseline ✅ → M1 physical INP writer ✅ → M2 Physical Data Check ✅ →
M3 单作业 solve ✅ → **M4 ODB 提取 + raw result integrity（下一步）** →
M5 单算例闭环 → M6 网格自动化 → M7 可靠性工程 → M8 batch。详见
`docs/PROJECT_ROADMAP.md`。

## 文档索引

| 文档 | 角色 |
|---|---|
| `README.md` | 公共入口（本文件） |
| `AGENTS.md` | AI/贡献者编码规则 |
| `docs/PROJECT_ROADMAP.md` | 稳定架构与里程碑定义 |
| `docs/PROJECT_STATUS.md` | 已验证工程事实 |
| `docs/IMPLEMENTATION_STATUS.md` | 详细实现历史 |
| `docs/IMPLEMENTATION_PLAN.md` | 计划与延后工作 |
| `docs/HANDOFF_CURRENT.md` | 当前开发者/AI 接管快照 |
| `docs/LOCAL_ENVIRONMENT.md` | 历史/当前开发机证据 |
| `docs/TROUBLESHOOTING.md` | 失败、调试与经验教训 |
| `docs/HISTORICAL_v0.1_README.md` | 被取代的 v0.1 README（历史） |
| `docs/VERIFICATION.md` | 历史验证证据 |
| `docs/EXPERIMENT_30_SURFACES_20260915.md` | 30曲面阶段性验证实验记录 |
| `docs/Abaqus_Automation_Design_v1.0.md` | 原始设计文档（历史架构参考） |
| `docs/LOCAL_EVIDENCE.json` / `docs/source_inventory.json` | 历史本地证据快照（非可移植配置） |

## License

仓库许可尚未选定。
