# 30曲面阶段性验证实验记录（2026-09-15/16）

Status: `COMPLETED AS LOCAL EXPERIMENT`（阶段性验证；不是 batch framework 验收）

## 实验目的

在 M3 单曲面验证（Fig.1 20%）之后，检验自动化链 **mesh → physical build →
Abaqus Data Check** 在一组明显不同的周期曲面上的泛化能力，并初步观察 solve 层面
的收敛行为。这不是 batch framework 的验收实验——正式 batch/retry/recovery 仍属
M7/M8。

## 30 个曲面来源

- 清单：`reference/selected_30_diverse_cases_report.md`（从约 23,534 个周期曲面
  方程池中按差异度挑选的 30 个；`reference/` 为 git-ignored 本地证据）。
- 每个方程的 SHA256 记录在实验目录的 `batch_source_manifest.json`（equation-level
  traceability）。
- **tracked reference**：用于本次 30 曲面验证的精选 case 列表及其原始方程已整理为
  `references/validation_30_surfaces.md`（该文件描述"**测试对象是什么**"；本文件仍是
  "实际运行了什么、结果如何"的唯一权威记录，`work/` 为本地原始运行证据）。
- case 配置由 fig1 模板生成，唯一差异为 `case_id` 与 surface 表达式（剥离尾部
  ` = 0`）。

## 统一 physics 与运行环境

- 全部 case 共用同一 20% physics 配置（来自 M3 验证的 local config；SHA 记录于
  batch log 首行）、同一 demo_surrogate 材料、同一 numerics/outputs。**无物理参数
  漂移**。
- 执行策略：Data Check `cpus=1, standard_parallel=solver`；solve
  `cpus=4, standard_parallel=solver`（与 M3 一致）。
- 环境：Windows + Abaqus 2026 + Pixi；CGAL mesher 为冻结的 vendor v1.0。

## Phase A 结果（mesh → build → Data Check）

| 阶段 | 结果 |
|---|---|
| 进入自动化测试 | 30 / 30 |
| 自动网格通过 | **28 / 30** |
| physical build 通过 | **28 / 28** |
| Abaqus Data Check accepted | **28 / 28**（0 failed；每 case 9–10 条 preprocessing warnings，全部保留） |

mesh 失败 2 例：

- `ref30_01`：mesh stage05 shell QA 未过（Z 方向周期性非双射，max_mismatch ≈0.031）。
- `ref30_22`：CGAL 崩溃（return code 3221225477 = 0xC0000005，输出目录为空）。

两者均保留完整 stage stdout/stderr 证据，待单独诊断；不能断言 mesher 算法错误。

### 证据优先级（Evidence precedence）

`work/night_batch_30surfaces_20260915/` 内同时存在两代 summary 产物，引用时必须区分：

- **终态统计（权威来源）**：`batch_status.json`（`batch_status=PHASE_A_DONE`、`mesh_pass 28 / mesh_fail 2 / build_pass 28 / datacheck_accepted 28 / datacheck_failed 0 / solve_completed 0`）、`batch_log.txt`、`FORENSIC_REVIEW_20260916.md`。
- **HISTORICAL STALE SUMMARY（非终态，保留不删）**：`BATCH_SUMMARY.md` 与 `batch_summary.json` 记录的是**首轮 double-reserve bug 运行**（30 个 case 全部 `MESH_FAILED (OUTPUT_EXISTS)`，mesh pass 0 / fail 30）。它们按"证据不覆盖"原则保留，但**不得**当作本次实验的最终 batch 结果引用。

本文以及 `docs/PROJECT_STATUS.md`、`docs/HANDOFF_CURRENT.md` 中的 28/30、28/28、28/28 一律以上述**终态统计**为准。`work/` 内文件属 git-ignored 本地证据，2026-09-16 maintenance checkpoint 未对其做任何修改。

## Solve 情况（Phase B，4 个尝试，0 完成）

| case | 现象 | 终止方式 |
|---|---|---|
| ref30_02 | step time ≈0.312 收敛停滞（增量缩至 ~1e-7，77 增量） | 人工终止 |
| ref30_03 | ≈0.39 处 TOO MANY ATTEMPTS，2 errors，Abaqus 自行终止 | 数值失败 |
| ref30_04 | step time ≈0.532 收敛停滞（增量 ~6e-8，81 增量） | 人工终止 |
| ref30_05 | 推进至 step time ≈0.979（75 增量），被外部事件中断 | 见下 |

### Windows Update 强制重启

2026-09-16 01:30–01:33，Windows Update（KB5129195，2026-09-15 13:41 安装并标记
"需要重启"）强制重启系统，杀死正在运行的 ref30_05 solve 与 runner。证据：System
日志连续多条 Kernel-Power **109**（"内核电源管理器已启动关闭转换"，Power Action:
Reboot，Kernel API；01:30:49 / 01:31:08 / 01:32:33，配套 521/577/125/578）；Setup
日志 01:33:02 KB5129195 → Installed；ref30_05 最后 .sta/.odb 写入时间 01:28:40 与
重启时间吻合。

### 结果判定

**本次实验没有得到完整有效 ODB**（0 个 `SOLVE_COMPLETED*`）。ref30_05 的部分
ODB（≈16.8MB）无 `.sta` 完成标记，**不作为成功结果**——partial ODB + 无成功完成
证据 = 不是有效的已完成 solve。

## 失败分类

| 类别 | case | 状态 |
|---|---|---|
| MESH 失败 | ref30_01、ref30_22 | 单独诊断 PENDING |
| SOLVE 收敛停滞（人工终止） | ref30_02、ref30_04 | NUMERICAL / MECHANICAL INVESTIGATION PENDING |
| SOLVE 数值失败 | ref30_03 | NUMERICAL / MECHANICAL INVESTIGATION PENDING |
| SOLVE 外部中断 | ref30_05 | 环境事件；可直接重跑 |

尚未做任何力学/数值归因，**不能断言模型错误**；不据此修改任何物理参数。

## 可复用中间结果

28 个 case 的 accepted Data Check attempt（`work/nb30_ref30_XX_datacheck`）完整
保留，后续可在新 attempt 中直接进入 solve，无需重新 mesh/build/datacheck。全部
原始证据（per-case stdout/stderr、.dat/.msg/.sta、reports、batch log/status）
保留在 `work/night_batch_30surfaces_20260915/`（git-ignored）。

## 与正式代码的关系

- 实验使用临时 local batch runner（`run_batch.py`，位于实验目录内），**不是正式
  production pipeline**。
- 实验暴露的 double-reserve 与 BOM 解析问题均为 local runner bug；正式代码已审计：
  `reserve_directory` 每 stage 单次调用、`read_json` 使用 `utf-8-sig`、
  `OUTPUT_EXISTS` 拒绝覆盖有测试锁定。**正式代码无需为此修改**（2026-09-16 审计）。

## 已有 ODB 的 ad-hoc stress-strain diagnostic（2026-09-16）

**性质**：ad-hoc 只读诊断，不是正式 M4。未运行任何新 Abaqus 作业；使用
`abaqus python` + `abaqus_worker/export_history.py` 以 `readOnly=True` 打开 5 个
**已有** ODB，从 `Compression` step 的 RP_TOP history region 提取 `U3`/`RF3`，
绘制同一张工程应力–应变图。结果目录：`work/diagnostic_stress_strain_5cases_20260916/`
（summary.json、5×CSV、PNG/PDF，git-ignored 本地证据）。

| case | ODB 状态 | history 点数 | final strain | final stress (MPa) | max stress (MPa) |
|---|---|---|---|---|---|
| Fig.1 | complete（20% 达标） | 60 | 0.20000 | 0.3141 | 0.3141 |
| ref30_02 | partial（人工终止） | 70 | 0.03586 | 0.2082 | 0.2665 |
| ref30_03 | partial（TOO MANY ATTEMPTS） | 28 | 0.06015 | 0.0000（末点伪影） | 0.1257 |
| ref30_04 | partial（人工终止） | 80 | 0.11213 | 0.3626 | 0.3626 |
| ref30_05 | partial（Windows Update 重启中断） | 70 | 0.19551 | 0.1080 | 0.2562 |

符号约定（先以 Fig.1 完整结果核实：final U3=−2.0mm、final RF3=−31.41N，压缩时
RF3 为负，未使用 `abs()`）：`strain = -U3 / 10`（L=10mm）、`stress = -RF3 / 100`
（A=100mm²，compression-positive，MPa）；5 条曲线定义完全相同。partial 曲线只画到
ODB 中实际存在的最后一个 history 点，无外推。

**明确边界**：本诊断不构成 M4 DONE，不构成 mechanics QA，不改变任何 case 的
`SOLVE_FAILED`/partial 判定；ref30_05 的部分 ODB 仍不是有效完成结果。

**留给 M4 的两条关键经验**：

1. **step time ≠ engineering strain**。正式应变必须来自
   `strain = -U3 / L`（本模型 L=10mm），不能用 `step_time × target_strain` 替代
   （Smooth Step amplitude 非线性，且 history 最后写入时刻落后于 `.sta` 最后行）。
2. **failed / interrupted ODB 的最后 history point 可能包含终止伪点**。本次
   ref30_03 出现 final RF3≈0 的 interruption artifact（同一时刻 RF3 前一点为
   −12.57N）。因此未来 M4 必须：保留 solver completion status；partial/failed
   history 与 complete result 严格区分；不把最后一个 datum 自动视为真实最终力学
   状态；不允许外推 partial curve。

（早期版本本文与 TROUBLESHOOTING 曾把事件 ID 写为 Kernel-Power 107，2026-09-16
经事件日志核实统一修正为 **109**，见 `docs/REVIEW_BACKLOG.md` RB-004。）

## 下一步

1. 恢复批量前先消除 Windows Update 强制重启风险（暂停更新/设置活动时间）。
2. ref30_01/ref30_22 的 mesh 失败单独开小轮次诊断（与批量恢复解耦）。
3. 正式方向仍是 M4 ODB 提取与 raw result integrity；solve 收敛性研究与
   standard_parallel=all 性能债（见 IMPLEMENTATION_PLAN）按里程碑推进。
4. 正式 batch/resume/watchdog 属 M7/M8，本实验不改变该规划。
