# Review Backlog（review / 审查意见总账）

> 用途：记录用户、ChatGPT、GLM 或其他 reviewer 对本仓库指出的潜在问题、改进建议、
> 未处理问题、已拒绝建议与已解决问题。本文是**索引和跟踪表**，不替代
> `IMPLEMENTATION_PLAN.md` / `docs/TROUBLESHOOTING.md` / `docs/PROJECT_STATUS.md`；
> 详细技术内容放在对应文件，本文只登记条目并链接。
>
> 规则：
> 1. 条目一旦登记不删除；状态只演进：`OPEN → ACCEPTED / DEFERRED / RESOLVED / REJECTED / NO_ACTION`。
> 2. 已解决 → `RESOLVED` + 解决方式与 commit；不修改 → `NO_ACTION`/`REJECTED` + 原因；暂不做 → `DEFERRED`。
> 3. AI/reviewer 提出的意见**不是**自动成为项目要求；每条必须有"当前决定"。
>
> 初始登记：2026-09-16（来源：Pre-M4 cleanup 轮的自查与外部审查意见）。

## 索引

| ID | 类别 | 状态 | 优先级 | 摘要 |
|---|---|---|---|---|
| RB-001 | config | RESOLVED | HIGH | Fig.1 20% validation profile 缺少 tracked 可复现配置 |
| RB-002 | environment/release | RESOLVED | HIGH | environment.local.json 损坏静默 fallback；abaqus_release_required 未真正 gate |
| RB-003 | docs | RESOLVED | MEDIUM | HANDOFF/ROADMAP/PLAN 存在旧状态文字与过期测试数量 |
| RB-004 | docs/evidence | RESOLVED | MEDIUM | Kernel-Power 事件 ID 107/109 记录不一致 |
| RB-005 | docs | RESOLVED | MEDIUM | 5-case ad-hoc ODB stress-strain diagnostic 已发生但未记录；M4 状态表述过时 |
| RB-006 | pipeline | RESOLVED | MEDIUM | M2 Data Check 未检查 zero-byte ODB |
| RB-007 | pipeline/docs | RESOLVED | LOW | STAGES 中 SOLVE 描述宣称 watchdog，但 production watchdog 未实现 |
| RB-008 | config schema | DEFERRED | MEDIUM | numerics.example.json 混合 physical numerics 与 runtime/resource/retry 参数 |
| RB-009 | repo | DEFERRED | LOW | .gitattributes `* -text` 作用于全仓库，长期应缩小 byte-exact 范围 |
| RB-010 | data/reproducibility | DEFERRED | MEDIUM | 30 validation equations 位于 git-ignored reference，公开仓库不能完整复现 |
| RB-011 | pipeline | DEFERRED | MEDIUM | curve_qa.py TARGETS 硬编码到 0.30 |
| RB-012 | performance | DEFERRED | HIGH | standard_parallel=all / threads_per_mpi_process 性能债 |
| RB-013 | mechanics QA | DEFERRED | HIGH | M2/M3 contact warnings、PBC 大变形、准静态有效性 |
| RB-014 | reliability | DEFERRED | HIGH | solve timeout / child process tree / resume & reconciliation |

## 条目详情

### RB-001 — Fig.1 20% validation profile 缺少 tracked 可复现配置

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：HIGH；状态：**RESOLVED**（本轮）；类别：config / reproducibility
- 问题：`config/physics.example.json` 的 `target_compression_strain=0.30`（prototype），而正式 M3 验证成功的是 20%；公开仓库缺少与 M3 成功案例一致的 physics profile。
- 证据：`work/m3_fig1_20pct_inputs/physics.json`（M3 正式使用，SHA256 `9340898e6705049390e5e0005314240a2e2f4720d185a97c1102ed938523601e`）；`work/fig1_solve_m3_20pct_003/solve_report.json`。
- 当前决定：新增 tracked 文件 `config/physics.fig1_20pct_validation.json`，与本地 M3 physics **逐字段一致（byte-identical）**；`physics.example.json`（30%）保留不动，README 明确区分两者。
- 下一步：无需进一步动作；30% target solve 验证属后续里程碑。
- 相关文件：`config/physics.fig1_20pct_validation.json`、`config/physics.example.json`、`README.md`。

### RB-002 — environment.local.json 损坏静默 fallback；release 要求未强制

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：HIGH；状态：**RESOLVED**（本轮）；类别：environment / release gate
- 问题：① `pipeline/physical_datacheck.py::resolve_launcher` 中，environment.local.json 存在但 JSON 损坏时被 `except: configured=None` 静默吞掉并继续到 PATH 找 launcher（可能命中另一套 Abaqus）；schema 错误同样被忽略。② `abaqus_release_required="2026"` 只在 report 里记录，运行前不比对。
- 证据：`pipeline/physical_datacheck.py` 原 `resolve_launcher`/`query_release` 实现。
- 当前决定：新增 `load_environment_config`（损坏/非法 schema → `CONFIG_INVALID`，不 fallback）与 `enforce_release_gate`（required release 与 launcher 报告 release 不一致或无法确定 → `ABAQUS_RELEASE_MISMATCH`；gate 位于 `reserve_directory` 之前，不产生 partial attempt）；datacheck 与 solve 均接入；report 记录 `release_gate`。回归测试：malformed env 不 fallback、2026/2025 → fail、2026/2026 → pass、unknown → fail、gate 前 no attempt。
- 下一步：无需进一步动作；launcher 系统不大重构。
- 相关文件：`pipeline/physical_datacheck.py`、`pipeline/physical_solve.py`、`tests/test_core.py`。

### RB-003 — HANDOFF / ROADMAP / IMPLEMENTATION_PLAN 旧状态文字

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**RESOLVED**（本轮）；类别：docs consistency
- 问题：① `docs/HANDOFF_CURRENT.md` 测试数量写 `115/115`（当前实际 142/142 core + 8/8 boundary）；② `docs/PROJECT_ROADMAP.md` 第 9 节标题仍写"当前唯一主目标：M3"；③ `docs/IMPLEMENTATION_PLAN.md` 开头的 2026-09-13 历史性描述（"下列求解/Data Check……本次没有启动"）无 HISTORICAL 标注。
- 证据：上述文件对应行。
- 当前决定：测试数量更新为当前真实结果；ROADMAP 第 9 节目标改为 M4；IMPLEMENTATION_PLAN 旧描述加 `[HISTORICAL / SUPERSEDED]` 标注（历史文字保留不删除）。HANDOFF 基准 SHA 改为 "last reviewed checkpoint" 表述，避免每个 docs commit 立即过期。
- 下一步：文档状态描述以后随 checkpoint 更新。
- 相关文件：`docs/HANDOFF_CURRENT.md`、`docs/PROJECT_ROADMAP.md`、`docs/IMPLEMENTATION_PLAN.md`。

### RB-004 — Kernel-Power 事件 ID 107/109 记录不一致

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查（发现取证对话报告与 work 内 forensic 文件编号不一致）
- 优先级：MEDIUM；状态：**RESOLVED**（本轮核实并统一）；类别：docs / evidence
- 问题：`docs/EXPERIMENT_30_SURFACES_20260915.md` 与 `docs/TROUBLESHOOTING.md` 写 "Kernel-Power 107"，而 `work/night_batch_30surfaces_20260915/FORENSIC_REVIEW_20260916.md` 写 "109/577"。
- 证据：2026-09-16 只读查询 Windows System 事件日志（`wevtutil qe System`，Microsoft-Windows-Kernel-Power provider）：9/16 01:30:49、01:31:08、01:32:33（本地时间）存在 **Event ID 109**（"内核电源管理器已启动关闭转换"，原因 Kernel API）共 3 条，配套 521/577/125/578；该窗口内**无任何 107**（107 = 系统从低功耗状态返回，与强制重启事实不符）。
- 当前决定：统一修正为 **Kernel-Power 109**；证据不足时不允许凭印象写编号。
- 下一步：无需进一步动作。
- 相关文件：`docs/EXPERIMENT_30_SURFACES_20260915.md`、`docs/TROUBLESHOOTING.md`、`work/night_batch_30surfaces_20260915/FORENSIC_REVIEW_20260916.md`（本地证据）。

### RB-005 — 5-case ad-hoc ODB stress-strain diagnostic 已发生但未记录

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**RESOLVED**（本轮记录）；类别：docs / M4 boundary
- 问题：2026-09-16 已对 5 个已有 ODB（Fig.1 complete + ref30_02/03/04/05 partial）做只读 history 提取并绘制工程应力–应变曲线，但文档未记录；README "已完成的 solve ODB 尚未被读取" 的说法已不准确；`step time != engineering strain` 与 "interruption artifact point" 两条经验必须留存给 M4。
- 证据：`work/diagnostic_stress_strain_5cases_20260916/`（summary.json、5×CSV、图）。
- 当前决定：`docs/EXPERIMENT_30_SURFACES_20260915.md` 增加 "已有 ODB 的 ad-hoc stress-strain diagnostic" 章节；README 措辞改为 "正式 M4 自动 ODB extraction 尚未接入；已有 ODB 曾进行 ad-hoc/read-only history extraction（验证与诊断用），不构成正式 M4 或 mechanics QA"。**M4 仍 NOT STARTED。**
- 下一步：M4 实现时必须：保留 solver completion status；partial/failed history 与 complete result 严格区分；不把最后一个 datum 自动视为真实最终力学状态；不允许外推 partial curve。
- 相关文件：`docs/EXPERIMENT_30_SURFACES_20260915.md`、`README.md`、`work/diagnostic_stress_strain_5cases_20260916/`（本地证据）。

### RB-006 — M2 Data Check 未检查 zero-byte ODB

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**RESOLVED**（本轮）；类别：pipeline hardening
- 问题：M3 solve 已要求 ODB exists AND size>0，但 M2 Data Check 只检查 ODB 存在；0 字节 ODB 会被当成 artifact 证据。
- 证据：`pipeline/physical_datacheck.py` 原 accept 判定（仅 `missing` 检查）。
- 当前决定：Data Check accepted 现在要求 required artifacts（dat/odb）**存在且非零字节**；零字节 → `DATACHECK_FAILED` + failure_reasons "zero-byte required artifacts: ..."。不加任何额外科学判断。回归测试 `test_zero_byte_datacheck_odb_fails`。
- 下一步：无需进一步动作。
- 相关文件：`pipeline/physical_datacheck.py`、`tests/test_core.py`。

### RB-007 — STAGES 中 SOLVE 描述宣称 watchdog

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：LOW；状态：**RESOLVED**（本轮）；类别：pipeline/docs wording
- 问题：`pipeline/mesher_adapter.py` STAGES 的 SOLVE 描述为 "Dynamic implicit solve with resource limits and watchdog"，而 production watchdog 属 M7、尚未实现；`pixi run plan` 会误导读者。
- 证据：`pipeline/mesher_adapter.py` STAGES 定义。
- 当前决定：描述改为 "Dynamic implicit solve with resource limits; production watchdog/recovery is deferred to M7"。只改措辞，不实现 watchdog。
- 下一步：无需进一步动作。
- 相关文件：`pipeline/mesher_adapter.py`。

### RB-008 — numerics.example.json 混合 physical numerics 与 runtime/resource/retry 参数

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**DEFERRED**；类别：config schema
- 问题：`config/numerics.example.json` 同时包含物理数值（procedure/increments/stabilization）与 runtime/资源/重试类参数，长期应拆分（physical numerics vs execution policy）。
- 当前决定：DEFERRED。schema 拆分影响 builder 契约与已验证案例的身份键，不宜在本轮顺手做；待 M4/M5 阶段统一设计。
- 下一步：进入 M4/M5 设计时评估。
- 相关文件：`config/numerics.example.json`、`pipeline/physical_builder.py`。

### RB-009 — .gitattributes `* -text` 作用范围过宽

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：LOW；状态：**DEFERRED**；类别：repo policy
- 问题：`.gitattributes` 当前 `* -text`（全仓库禁用换行转换，保护 vendor SHA 校验值）；长期看应缩小 byte-exact 范围（如仅 vendor/ 与特定二进制），让普通文本正常归一化。
- 当前决定：DEFERRED。改动会影响全部 tracked 文件的历史 diff 与校验值，收益低、风险高；vendor 冻结期间不动。
- 下一步：vendor 结构调整或大版本整理时一并评估。
- 相关文件：`.gitattributes`。

### RB-010 — 30 validation equations 位于 git-ignored reference

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**DEFERRED**；类别：data / reproducibility
- 问题：30 曲面验证实验的方程清单在 `reference/`（git-ignored 本地证据），公开仓库无法完整复现该实验的输入集。
- 当前决定：DEFERRED。以后考虑在仓库中新增 `examples/validation_30_surfaces.json`（或等价 tracked manifest），记录 30 个方程与 SHA；`reference/` 本身保持只读不动。本轮不做，避免把大批科研输入直接纳入仓库前未经用户确认。
- 下一步：用户确认后设计 tracked manifest。
- 相关文件：`reference/selected_30_diverse_cases_report.md`（本地）、`docs/EXPERIMENT_30_SURFACES_20260915.md`。

### RB-011 — curve_qa.py TARGETS 硬编码到 0.30

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**DEFERRED（TO M4/M5）**；类别：pipeline
- 问题：`pipeline/curve_qa.py` 的历史 11 点 TARGETS 按手工 30% 目标标定，与 20% validation profile 不匹配；本轮 ad-hoc 诊断未使用它（正确）。
- 当前决定：DEFERRED TO M4/M5。curve QA 策略（targets、tolerance、policy）在 ODB extraction 与 mechanics QA 设计时统一 config 化，不提前改。
- 下一步：M4/M5 设计 curve-QA policy 时处理。
- 相关文件：`pipeline/curve_qa.py`、`config/quality.example.json`。

### RB-012 — standard_parallel=all / threads_per_mpi_process 性能债

- 日期：2026-09-16；来源：既有登记（2026-09-16 复盘时正式化）
- 优先级：HIGH；状态：**DEFERRED**；类别：performance
- 问题与方案：见 `docs/TROUBLESHOOTING.md` "HIGH-PRIORITY DEFERRED PERFORMANCE DEBT" 与 `docs/IMPLEMENTATION_PLAN.md` 对应章节（候选矩阵 `8/automatic/all`、`8/8/all`、`4/4/all` 等）。
- 当前决定：DEFERRED，本轮不实际运行任何实验。
- 下一步：按登记的矩阵先 Data Check 后 solve。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/HANDOFF_CURRENT.md`。

### RB-013 — M2/M3 contact warnings、PBC 大变形、准静态有效性

- 日期：2026-09-16；来源：既有登记
- 优先级：HIGH；状态：**DEFERRED（TO mechanics QA）**；类别：mechanics QA
- 问题：M2 的 10 条 Data Check warnings（double-sided facets、STRAINFREE 调整、8 组相邻 secondary nodes）与 M3 的 7 条 zero-moment warnings 未做力学判定；PBC 在大变形下的有效性、准静态假设（动能/内能比）均未验证。
- 证据：`docs/TROUBLESHOOTING.md` 对应条目；`work/fig1_datacheck_m2_final_001`、`work/fig1_solve_m3_20pct_003` 报告。
- 当前决定：DEFERRED TO mechanics QA（M4 提取能力就绪后系统评估）。禁止在无提取证据时白名单任何 warning。
- 下一步：M4 mechanics/contact QA。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/HANDOFF_CURRENT.md`。

### RB-014 — solve timeout / child process tree / resume & reconciliation

- 日期：2026-09-16；来源：既有登记
- 优先级：HIGH；状态：**DEFERRED（TO M7）**；类别：reliability
- 问题：solve 超时只杀 launcher 层进程，可能遗留 SMALauncher/standard.exe 后代；timeout 时结构化证据不完整；无 watchdog/retry/resume/reconciliation。30曲面实验的临时 runner 问题（double-reserve 等）也属这一层的教训，正式 pipeline 无同类缺陷（2026-09-16 审计）。
- 证据：`docs/TROUBLESHOOTING.md` "Timeout / child process tree 限制" 与 "30曲面临时 runner double-reserve bug"。
- 当前决定：DEFERRED TO M7 可靠性里程碑。
- 下一步：M7 设计 watchdog/kill-tree/resume。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/IMPLEMENTATION_PLAN.md`（阶段 E/F）。

