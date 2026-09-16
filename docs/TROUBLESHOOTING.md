# 故障排查与开发经验

本项目真实失败案例、诊断路径与经验教训，以及每条目的当前状态。这里没有任何条目被
白名单：每条 warning 与每个限制仍是后续里程碑（M4 力学/接触 QA 及之后）的 QA 义务。

## 如何阅读本文

状态标签：

- `RESOLVED` —— 根因已找到并修复；有回归测试守护。
- `WORKAROUND` —— 已验证的绕行方案存在；底层原因未修复。
- `KNOWN LIMITATION` —— 当前里程碑接受的边界。
- `DEFERRED` —— 有意推迟到后续里程碑。
- `HISTORICAL` —— 保留用于学习的调试证据；不再是活动问题。
- `CURRENT` —— 当前有效政策。

每个条目的证据都在 `work/<attempt>` 目录（git-ignored）与相关项目文档中。

## Abaqus General Contact preprocessing / threads-per-domain 失败

Status: `WORKAROUND`（machine/runtime-specific）

以默认并行模式（`standard_parallel=all`）运行 datacheck 或 analysis 时，`pre.exe`
在 General Contact 连接性处理阶段（`pre | Elem | ElemC | Econtp | ConnectivityAtNodes`）
中止：

```
***ERROR: EXCEEDED THE MAXIMUM AMOUNT OF THREADS TO BE USED PER DOMAIN.
PLEASE REDUCE THE NUMBER OF THREADS TO BE LESS THAN OR EQUAL TO 100.
```

诊断路径（10 次受控尝试，见开发工作区的
`work/fig1_datacheck_m2_diagnostics_summary.json`）：

1. 干净环境（最小 PATH、清空变量）→ 同样失败 → 排除继承环境污染。
2. 手工 baseline 模型（`Fig1_Compression.inp`，同一安装上完成过 20% solve）同样
   失败 → 自动 deck 无罪。
3. `cpus=1` 不能绕过；`threads_per_domain` 不是合法 CLI 选项；`standard_parallel=mpi`
   被拒绝。
4. 无 General Contact 的纯网格输入可以完成（`ANALYSIS DATACHECK COMPLETE`）→ 失败
   特定于 General Contact 并行单元/preprocessing 路径。
5. `standard_parallel=solver`（单元操作串行）消除失败：同一 deck 完成 Data Check
   与真实 20% solve。

解读：可复现的 machine/runtime-specific 并行单元/preprocessing 路径失败。这是实验
描述，不是对 Abaqus 源码级缺陷的断言。其他机器不得假设必须
`standard_parallel=solver`；采用 profile 前先验证。

## 为什么开发工作站使用 standard_parallel=solver

Status: `WORKAROUND` / 当前安全 profile

单元操作串行后 General Contact preprocessing 失败消失，solver 仍可运行（可多线程）。
这就是可移植 safe default 为 `cpus=1, standard_parallel=solver`、开发工作站验证
`cpus=4, solver`（16m33s solve）并测试过 `cpus=8, solver`（见 CPU 实验节）的原因。

## HIGH-PRIORITY DEFERRED PERFORMANCE DEBT：standard_parallel=all

Status: `DEFERRED`（高优先级性能技术债；本轮只登记，不实际运行）

`standard_parallel=all` 可让 General Contact preprocessing 并行化，可能显著缩短
wall time，但在本机触发上述 threads-per-domain ERROR。当前 workaround 是
`standard_parallel=solver`。后续优先测试方向（**先做 Data Check 验证，再谈 solve**）：

- 首选组合：`cpus=8, threads_per_mpi_process=8, standard_parallel=all`
  （`threads_per_mpi_process` 是 environment 文件级参数，不是 abaqus.bat CLI 选项，
  需通过 `abaqus_v6.env`/环境设置注入）。
- 其他候选矩阵（cpus / threads_per_mpi_process / standard_parallel）：
  `8 / automatic / all`、`8 / 8 / all`、`4 / 4 / all`、`8 / 4 / all`、
  `8 / 2 / all`、`8 / 1 / all`。
- 每个组合先用小 deck 或 Data Check 验证 preprocessing 是否仍触发 threads/domain
  ERROR；任何组合未验证前不得用于正式 solve。
- 结论无论成败都要登记到本文与 `docs/HANDOFF_CURRENT.md`。

## jleConfig reqcpus 假设及其证伪

Status: `HISTORICAL`（hypothesis falsified）

站点文件 `SMA/site/jleConfig.env` 设置 `aba_jle_std_direct_reqcpus='32'`，超过本机
14 核 / 20 逻辑处理器。严格单变量实验（SHA 校验备份、只改一行 `'32' → '4'`、通过
`information=environment` 确认生效）仍产生同样的 threads/domain 错误，假设被证伪，
原值已恢复。教训：确认配置值真的被失败代码路径**使用**后再归因；单变量实验必须有
可验证备份。

## Data Check 交互式 .log 行为

Status: `KNOWN LIMITATION`（已处理）

Abaqus 2026 datacheck 交互式运行完成时不写 `.log` 文件；stdout 承担 log 角色。
因此 M2 必需 artifact 集为 `.dat + .odb + stdout capture`；`.msg/.log/.exception`
在存在时收集。

## M2 warning 签名（10 条 warning，保留）

Status: `KNOWN LIMITATION`（M4 的 QA 义务）

已接受的 Fig.1 Data Check 报告 10 条 warning、0 error：

- 1× General Contact domain 含 double-sided facets；初始接触调整可能不正确；建议
  单侧面。
- 1× STRAINFREE 调整比例（max incremental adjustment / average characteristic
  length = 2.55003E-02，node 544）。
- 8× double-sided 主面两侧的相邻 secondary nodes（nodes 72/71、85/84、83/85、
  117/116、171/169、170/171、169/170、377/376）。

这些与手工 20% baseline 作业的诊断签名一致——不是新的自动化回归——但未证明无害。
M3 solve 在自己的 `.dat` 中原样重现同 10 条 warning（signature-identical），另有
7 条来自 `.msg` 的 solver-only zero-moment warnings。

## Zero-moment warnings

Status: `KNOWN LIMITATION`（M4 的 QA 义务）

solve 的 `.msg` 含 7×
`***WARNING: THERE IS ZERO MOMENT EVERYWHERE IN THE MODEL BASED ON THE
DEFAULT CRITERION`。历史手工 20% 作业出现过同类启动 warning。它们已记录在
solve report 中，留待 M4 力学 QA；不据此做任何验收决定。

## STRAINFREE warning

Status: `KNOWN LIMITATION`（M4 的 QA 义务）

preprocessing 的 STRAINFREE 调整比例 warning 表示 Abaqus 移动了 secondary nodes
以消除初始过盈。待 M4 提取能力就绪后，可用 time=0 的 STRAINFREE 云图/符号图复核
量级。在此之前初始接触状态未经科学确认。

## Double-sided contact warnings

Status: `KNOWN LIMITATION`（M4 的 QA 义务）

Abaqus 建议 double-sided shell facets 的 General Contact domain 使用单侧面。当前
模型有意复现手工 baseline（双重连通壳 + 压板的 ALL EXTERIOR）。改单侧面是建模
决策，必须以真实提取证据评估，不得为消警告而改。

## M3 .sta parser bug

Status: `RESOLVED`

第一次真实 20% solve 物理上已完成（stdout token、`.sta` 完成标记、0 error），但
报告给出 `SOLVE_FAILED` 且 `last_step_time=null`：原 `.sta` parser 假设固定 9 列
行，而真实 Abaqus/Standard 行是 6–7 个整数字段后跟最多三个时间列（TOTAL TIME、
STEP TIME、INC OF TIME），cutback 行带 `U` 标记（如 `1U`）。parser 现在通用消费
前导整数字段并读取前两个 float 时间列，跳过 cutback 行。回归测试使用真实的三
时间列格式。

## M3 Attempt 001：物理完成但 parser 误判

Status: `HISTORICAL` / `RESOLVED`

`work/fig1_solve_m3_20pct_001` —— wall time 约 25m07s、`returncode=0`、
`Abaqus JOB fig1_m3_solve COMPLETED`、分析物理完成——但因上述 parser bug 被报为
`SOLVE_FAILED`。保留为证据；bug 已修复并有回归测试。

## M3 Attempt 002：意外重复 solve 与手动终止

Status: `HISTORICAL`

`work/fig1_solve_m3_20pct_002` —— 意外重复的 solve 调用（约 5m40s，分析尚在早期
增量），被发现后立即以进程树终止方式手动终止。它没有
command.json/solve_report.json（这些在正常完成后才写）。不是有效仿真数据点；
保留为事件与手动清理路径的证据。

## M3 Attempt 003：已接受的验证 solve

Status: `RESOLVED`（official M3 evidence）

`work/fig1_solve_m3_20pct_003` —— parser 修复后 wall time 约 16m33s、59 增量、
`last_step_time = 1.00 = target`、0 error、17 warnings、完整 ODB。正式已接受的
M3 solve 证据（`SOLVE_COMPLETED_WITH_WARNINGS`）。

## 8-CPU solver 实验

Status: `HISTORICAL`（实验结果已记录；4 CPU 仍为首选）

同一已接受 deck 的单变量实验（`work/fig1_solve_cpu8_validation_001`，仅把
`cpus: 4 → 8`，保持 `standard_parallel=solver`）：solve 完成
（`SOLVE_COMPLETED_WITH_WARNINGS`，59 增量，相同 cutback 模式，0 error，17
warnings，相同 ODB 大小 16,075,836 bytes）但耗时约 32m51s，而 4 CPU 约 16m33s
——明显更慢。本机 preferred profile 因此保持 `cpus=4, standard_parallel=solver`；
实验保留为证据：本机 wall time 对这个非线性作业并非随 CPU 数单调下降。

## 30曲面临时 runner double-reserve bug

Status: `HISTORICAL` / `RESOLVED IN LOCAL EXPERIMENT`

2026-09-15 夜间 30 曲面批量实验使用的**临时 local batch runner**
（`work/night_batch_30surfaces_20260915/run_batch.py`，不属正式 production
pipeline）首启时把全部 30 个 case 判为 `MESH_FAILED (OUTPUT_EXISTS)`：其
mesh 阶段先 `reserve_directory` 创建了 attempt 目录，`prepare_mesh` 内部又对同一
目录 reserve，必然触发 OUTPUT_EXISTS。当场修复（去掉外层 reserve）、删除 30 个
空目录并重置状态后重跑，Phase A 正常。

**定性**：这是 local runner 的 bug，不是正式 mesh/build/datacheck pipeline 的
bug。正式 pipeline 中每个 stage 只调用一次 `reserve_directory`（`pipeline/common.py`
定义，`mesher_adapter/prepare_fe/physical_builder/physical_datacheck/physical_solve`
各一处），并且 `OUTPUT_EXISTS` 拒绝覆盖行为有单元测试锁定
（`tests/test_core.py` 多处）。同批实验还暴露同类的 BOM 解析问题（runner 用
`utf-8` 读带 BOM 的 JSON 失败）——正式 `pipeline/common.read_json` 一直使用
`utf-8-sig`，无此问题。两者均无需修改正式代码。

## Windows Update 强制重启中断批量实验

Status: `HISTORICAL`（环境事件；非代码问题）

2026-09-16 01:30–01:33，Windows Update（KB5129195，2026-09-15 13:41 安装并标记
"需要重启"）强制重启系统，杀死了正在运行的 ref30_05 solve（step time ≈0.979）与
runner。证据：System 日志连续 5 条 Kernel-Power 107（Power Action: Reboot，
Kernel API）；Setup 日志 01:33:02 KB5129195 → Installed；ref30_05 最后 .sta/.odb
写入时间 01:28:40 与重启时间吻合。**教训**：过夜批量前必须暂停 Windows Update
自动重启或设置活动时间，否则 solve 窗口会被同类事件打断。

ref30_05 的部分 ODB 无完成标记，**不是有效完成结果**（见 attempt 保存政策）。

## 30曲面 difficult solve cases

Status: `NUMERICAL / MECHANICAL INVESTIGATION PENDING`

统一 20% physics 下 4 个 solve 尝试全部未完成（0 个有效 ODB）：

| case | 现象 | 终止方式 |
|---|---|---|
| ref30_02 | step time ≈0.312 收敛停滞（增量缩至 ~1e-7，77 增量） | 人工终止 |
| ref30_03 | ≈0.39 处 TOO MANY ATTEMPTS，2 errors，分析被 Abaqus 终止 | 数值失败 |
| ref30_04 | step time ≈0.532 收敛停滞（增量 ~6e-8，81 增量） | 人工终止 |
| ref30_05 | 推进至 ≈0.979（75 增量），被 Windows Update 强制重启中断 | 外部中断 |

上述标记为 **NUMERICAL / MECHANICAL INVESTIGATION PENDING**：尚未做任何力学/数值
归因，**不能断言模型错误**，也不据此修改任何物理参数。增量自适应、stabilization
等数值策略调整属科研决策，留待 M4 提取与 QA 能力就绪后系统研究。
ref30_01/ref30_22 的 mesh 失败（stage05 周期性校验未过 / CGAL access violation）
同样待单独调查。

## Timeout / child process tree 限制

Status: `DEFERRED`（M7 可靠性）

solve 超过 wall 限时，`subprocess.TimeoutExpired` 会在 `command.json`/
`solve_report.json` 写出前中止 Python 侧，attempt 保留原始输出但结构化证据不完整；
且只有 launcher 层进程被杀，可能遗留 SMALauncher/standard.exe 后代需手动清理。
Watchdog、kill-tree、retry、resume 与接管属于 M7 可靠性里程碑。

## Attempt 保存政策

Status: `CURRENT`

每个 attempt 位于自己的 `work/<attempt>` 目录，永不被覆盖或清理。失败的 attempt
（包括误判、中断实验与上述意外重复运行）逐字保留，任何结论都应能从原始
`.dat/.msg/.sta/.odb` 文件与报告重新推导。**partial ODB + 无成功完成证据 =
不是有效的已完成 solve**。

## 如何诊断一次失败的运行

1. 读 `solve_report.json` / `datacheck_report.json`：`status`、`failure_reasons`、
   `diagnostics`（含来源文件与行号的 errors）、`claims`。
2. 读 `stdout.txt` 看 launcher 层结果与 `Abaqus JOB <name> COMPLETED` token。
3. 读 `.sta`（完成标记、最后增量、cutback 行）与 `.dat`/`.msg` 的
   `***ERROR`/`***WARNING` 上下文。
4. 检查 `.exception` 文件中的 Abaqus abort 调用栈。
5. 在怀疑 deck 本身之前，先与 `work/fig1_solve_m3_20pct_003`（已接受 solve）的
   参考证据对比。
6. 绝不重跑进同一 attempt 目录；新建目录并说明新运行的原因。

## 30% 压缩非收敛（历史）

Status: `HISTORICAL` / `KNOWN LIMITATION`

早期对同一模型推到 30% 压缩（U3 = −3 mm）的手工尝试在达到目标前停滞，而 20%
（U3 = −2 mm）完成。这不意味着自动化流水线无效：20% 算例被有意用作 M3 基础设施
验证目标，30% 是后续数值/研究验证目标（M4+ 提取与 QA 必须先行）。没有为强制收敛
而改任何参数。
