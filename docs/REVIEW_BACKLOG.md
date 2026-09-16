# Review Backlog（review / 审查意见总账）

> [AI EXECUTION WARNING]
>
> 本文件是 **advisory-only** 的审查意见总账，**不是施工指令**。
> 任何条目，无论 Priority 是 HIGH 还是 Status 是 ACCEPTED，
> 都**不能单独授权** AI 修改代码、配置、文档、运行 Abaqus、
> 开始新 milestone 或扩大当前任务范围。

> 定位：专家 / 用户 / ChatGPT / GLM / 其他 reviewer 提出的审查意见、潜在风险、
> 设计建议和历史判断的登记表。它是 advisory review registry、historical decision
> log、future-review index。它**不是**：task queue、implementation plan、
> requirements specification、automatic TODO list、execution authorization。
> 本文是索引和跟踪表，不替代 `IMPLEMENTATION_PLAN.md` /
> `docs/TROUBLESHOOTING.md` / `docs/PROJECT_STATUS.md`；详细技术内容放在对应
> 文件，本文只登记条目并链接。

## AI 使用规则（coding agent 必读）

### 默认情况下不要读取本文件

普通 coding agent 在执行 implementation / bug fix / test / refactor / CLI 修改 /
documentation update / Abaqus workflow 任务时：
**DO NOT read or scan `docs/REVIEW_BACKLOG.md` by default.**
它不属于普通编程任务的 startup context。

只有以下情况可以读取：

- A. 用户明确要求 review backlog / 审查意见 / 整理改进建议 / repository review；
- B. 用户明确引用某个 `RB-xxx` 条目；
- C. 当前正式 `IMPLEMENTATION_PLAN` 或用户任务明确指定处理某个 RB 条目；
- D. 用户明确要求专家审查、技术债盘点或未来规划。

其他情况下不要主动扫描 REVIEW_BACKLOG。

### 读取范围限制

如果任务只引用 RB-015，则优先只阅读 RB-015 及其链接的必要 evidence/docs。
**禁止 scope expansion**：不得"既然看到了 RB-012，顺便修一下"、不得"RB-013 是
HIGH，一起实现"、不得"发现 DEFERRED 项，顺手解决"。

### Priority 不等于授权

`Priority`（HIGH/MEDIUM/LOW）只表示 reviewer 认为问题的重要程度；
**不表示** implementation priority、current milestone priority 或修改代码的许可。
**HIGH ≠ do now**。

### Status 的执行语义

| Status | 对 coding AI 的含义 |
|---|---|
| `OPEN` | 尚未完成项目决策；AI 不得自动实现。 |
| `ACCEPTED` | 项目认可该问题值得未来处理；**ACCEPTED ≠ authorized to implement now**。只有用户指令或 active IMPLEMENTATION_PLAN 纳入当前 scope 后才能施工。 |
| `DEFERRED` | **DO NOT IMPLEMENT NOW**；除非用户后来明确重新激活。 |
| `RESOLVED` | 历史记录；默认不要重新打开或重新修改，只有出现新的相反证据时才可提出重新审查建议。 |
| `REJECTED` | 不要实施。 |
| `NO_ACTION` | 已判断当前无需修改；不要实施。 |
| `CURRENT` / `CURRENT LIMITATION` | 当前事实、政策或已知限制；不是任务。 |

### 施工转换规则

```
reviewer / expert / AI 发现问题
        ↓
REVIEW_BACKLOG 登记
        ↓
项目判断是否接受
        ↓
如果决定施工：用户明确授权，或 active IMPLEMENTATION_PLAN 纳入当前任务
        ↓
coding AI 执行 → 测试 / 验证
        ↓
PROJECT_STATUS / TROUBLESHOOTING 更新
        ↓
REVIEW_BACKLOG → RESOLVED
```

**REVIEW_BACKLOG 本身永远不产生施工授权。**

### 执行权威顺序

对 coding agent，任务 scope 的来源优先级：

1. 用户当前明确指令
2. `AGENTS.md` 的项目规则
3. 当前 active milestone / `IMPLEMENTATION_PLAN`
4. 当前任务明确引用的设计或证据
5. REVIEW_BACKLOG 仅作为 advisory context

REVIEW_BACKLOG 与用户当前指令、AGENTS、正式 active plan 冲突时，
**REVIEW_BACKLOG 不得覆盖它们**。

### 禁止通过本文件自动扩大 scope

任何 coding AI 不得因为看到 `OPEN`、`ACCEPTED`、`HIGH` 或 `Next Action` 就修改
代码、重构、运行 Abaqus、新增测试、修改 config、提交 Git 或执行实验——除非当前
用户任务明确授权。`Next Action` 只代表未来建议，不是现在必须执行的命令。

### 条目写入规则

新增条目必须区分 **Observed Fact / Hypothesis / Recommendation / Decision**；
不要把"可能存在问题"写成"系统存在 bug"。每条保留：ID、Date、Source/Reviewer、
Priority、Status、Category、Issue、Evidence/Rationale、Decision、Next Action、
Related Files、Resolved Commit。`Source/Reviewer` 可写：User、ChatGPT review、
GLM audit、external expert、code experiment、forensic evidence；**不要把 AI 的
判断伪装成用户决定**。

### 本文件不是 startup 文档

REVIEW_BACKLOG **不加入**"新会话 / 新 AI 首先阅读"列表。新 AI 仍按 `AGENTS.md`
顺序（AGENTS → HANDOFF_CURRENT → PROJECT_ROADMAP → PROJECT_STATUS →
LOCAL_ENVIRONMENT → IMPLEMENTATION_PLAN → IMPLEMENTATION_STATUS）阅读；
REVIEW_BACKLOG 默认不读。

> 定位补充：本文是索引和跟踪表，不替代 `IMPLEMENTATION_PLAN.md` /
> `docs/TROUBLESHOOTING.md` / `docs/PROJECT_STATUS.md`；详细技术内容放在对应
> 文件，本文只登记条目并链接。
>
> 工作流：
>
> ```
> Review 提出问题            → REVIEW_BACKLOG 登记
> 决定要实施                 → IMPLEMENTATION_PLAN
> 真实发生故障               → TROUBLESHOOTING
> 成为已验证事实             → PROJECT_STATUS
> 解决                       → REVIEW_BACKLOG item → RESOLVED
> 被否决                     → REJECTED / NO_ACTION
> 延后                       → DEFERRED
> ```
>
> 规则：
> 1. 条目一旦登记**永不删除**（包括 RESOLVED）。
> 2. 状态只演进：`OPEN → ACCEPTED / DEFERRED / RESOLVED / REJECTED / NO_ACTION`
>    （另有 `CURRENT` 标记"当前有效事实/政策"，不是待办）。
> 3. AI/reviewer 提出的意见**不是**自动成为项目要求；必须经用户/维护者决定。
> 4. 强相关问题可合并为一个 ID，但不得丢失问题本身；索引表的
>    "Review items" 列记录每个 ID 覆盖的原始审查意见编号。
>
> 初始登记：2026-09-16（来源：Pre-M4 cleanup 轮的自查与外部审查意见）。
> 扩充登记：2026-09-16（对照 checkpoint 22e1a59 的完整外部 review，26 项全覆盖）。
> Governance 收紧：2026-09-16（AI execution policy，本节）。

## 索引

| ID | Review items | 类别 | 状态 | 优先级 | 摘要 |
|---|---|---|---|---|---|
| RB-001 | 1 | config | RESOLVED | HIGH | Fig.1 20% validation profile 缺少 tracked 可复现配置 |
| RB-002 | 2+3 | environment/release | RESOLVED | HIGH | environment.local.json 损坏静默 fallback；abaqus_release_required 未真正 gate |
| RB-003 | 5 | docs | RESOLVED | MEDIUM | HANDOFF/ROADMAP/PLAN 存在旧状态文字与过期测试数量 |
| RB-004 | 6 | docs/evidence | RESOLVED | MEDIUM | Kernel-Power 事件 ID 107/109 记录不一致 |
| RB-005 | 7 | docs | RESOLVED | MEDIUM | 5-case ad-hoc ODB stress-strain diagnostic 已发生但未记录；M4 状态表述过时 |
| RB-006 | 10 | pipeline | RESOLVED | MEDIUM | M2 Data Check 未检查 zero-byte ODB |
| RB-007 | 11 | pipeline/docs | RESOLVED | LOW | STAGES 中 SOLVE 描述宣称 watchdog，但 production watchdog 未实现 |
| RB-008 | 4 | config schema | DEFERRED | MEDIUM | numerics config 混合 physical numerics 与 runtime/orchestration 参数 |
| RB-009 | 12 | repo | DEFERRED | LOW/MEDIUM | .gitattributes `* -text` 作用于全仓库 |
| RB-010 | 13 | data/reproducibility | DEFERRED | MEDIUM | 30 validation equations 位于 git-ignored reference |
| RB-011 | 14 | pipeline | DEFERRED | HIGH (M4/M5) | curve_qa TARGETS 硬编码到 0.30 |
| RB-012 | 15 | performance | DEFERRED | HIGH | standard_parallel=all / threads_per_mpi_process 性能债 |
| RB-013 | 17+18+19 | mechanics QA | DEFERRED | HIGH | contact warnings QA / PBC large-deformation / quasi-static validity |
| RB-014 | 20 | reliability | DEFERRED | HIGH | solve timeout / child process tree / resume & reconciliation |
| RB-015 | 8+9 | M4 contract | ACCEPTED | HIGH | M4 extraction contract：step time ≠ strain；partial ODB 末点可能是 termination artifact |
| RB-016 | 16 | performance evidence | NO_ACTION | LOW | cpus=8 + solver 在本机反而更慢（结论已记录） |
| RB-017 | 21 | repo policy | NO_ACTION (CURRENT) | HIGH | attempt 不覆盖原则保持不变 |
| RB-018 | 22 | scope | CURRENT | MEDIUM | temporary local batch runner ≠ production batch framework |
| RB-019 | 23 | mesh | DEFERRED | MEDIUM | ref30_01/ref30_22 mesh 失败原因未解释（INVESTIGATION PENDING） |
| RB-020 | 24 | solve | DEFERRED | MEDIUM/HIGH | difficult solve cases 02/03/04 尚未归因（INVESTIGATION PENDING） |
| RB-021 | 25 | config identity | DEFERRED | LOW/MEDIUM | model/scaffold/build identity 分层与 runtime 信息混入的长期债 |
| RB-022 | 26 | material | CURRENT LIMITATION | HIGH | demo_surrogate 不是 production material，曲线不可作真实材料解释 |

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

### RB-008 — numerics config 混合 physical numerics 与 runtime/orchestration 参数

- 日期：2026-09-16；来源：外部 review（checkpoint 22e1a59）
- 优先级：MEDIUM；状态：**DEFERRED**；类别：config schema
- 问题：`config/numerics.example.json` 同时包含两类职责——
  - 物理/求解步数值：`initial_increment_s`、`minimum_increment_s`、`maximum_increment_s`、`maximum_increments`；
  - runtime / orchestration：`cpus_per_job`、`maximum_concurrent_solves`、`max_attempts_including_base`、`solver_wall_limit_s`、stagnation 等。
  M3 已经有独立的 solve_runtime policy（`config/solve_runtime.*.json`），配置职责重复；runtime 字段还可能污染 `model_key`/`scaffold_key` identity。
- 当前决定：DEFERRED。未来拆分为 physical numerics vs runtime/resources/reliability 两类 schema；本轮不改 schema（影响 builder 契约与已验证案例身份键）。
- 下一步：M4/M5 config 设计时统一处理；与 RB-021（identity 分层）联动。
- 相关文件：`config/numerics.example.json`、`pipeline/physical_builder.py`、`config/solve_runtime.example.json`。

### RB-009 — .gitattributes `* -text` 作用范围过宽

- 日期：2026-09-16；来源：外部 review
- 优先级：LOW/MEDIUM；状态：**DEFERRED**；类别：repo policy
- 问题：`.gitattributes` 当前 `* -text`（全仓库禁用换行转换，最初为保护 vendor/historical byte identity），但普通 Python/Markdown 也因此关闭 text normalization，容易产生 CRLF/line-ending noise。长期应只对真正要求 byte-exact 的对象（vendor/、legacy evidence、特定 binary-like files）使用 `-text`，普通源码/docs 用正常 `text` + LF。
- 当前决定：DEFERRED。改动可能产生大规模 line-ending diff，必须单独阶段处理，不顺手修改；vendor 冻结期间不动。
- 下一步：单独的仓库整理阶段评估。
- 相关文件：`.gitattributes`。

### RB-010 — 30 validation equations 位于 git-ignored reference

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查 + 外部 review
- 优先级：MEDIUM；状态：**DEFERRED**；类别：data / reproducibility
- 问题：30 曲面验证实验的方程清单在 `reference/selected_30_diverse_cases_report.md`（git-ignored 本地证据）；公开仓库记录了 28/30 mesh PASS 等结论，但其他用户无法完整复现实验所用方程集。
- 当前决定：DEFERRED。以后考虑新增 tracked 的 `examples/validation_30_surfaces.json`，只含 `case_id`、`surface_expression`、`equation_sha256`；不提交论文 PDF 或原始 dataset。`reference/` 保持只读不动。
- 下一步：用户确认后设计 tracked manifest。
- 相关文件：`reference/selected_30_diverse_cases_report.md`（本地）、`docs/EXPERIMENT_30_SURFACES_20260915.md`。

### RB-011 — curve_qa TARGETS 硬编码到 0.30

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查 + 外部 review
- 优先级：HIGH（for M4/M5）；状态：**DEFERRED（TO M4/M5）**；类别：pipeline
- 问题：`pipeline/curve_qa.py` 的 11 点 TARGETS 最终到 `0.300`（按历史手工 30% 目标标定），因此不能直接用于 20% validation case 或任意 compression target。
- 当前决定：DEFERRED TO M4/M5。未来 target/sampling 必须 config-driven 并禁止外推；现在不改。
- 下一步：M4/M5 设计 curve-QA policy 时处理。
- 相关文件：`pipeline/curve_qa.py`、`config/quality.example.json`。

### RB-012 — standard_parallel=all / threads_per_mpi_process 性能债

- 日期：2026-09-16；来源：既有登记（2026-09-16 复盘时正式化）
- 优先级：HIGH；状态：**DEFERRED**；类别：performance
- 问题与方案：本机 `standard_parallel=all` → General Contact preprocessing → threads-per-domain ERROR（稳定 workaround：`standard_parallel=solver`）；后果是 element operations 并行能力受限，CPU 利用率与 batch throughput 可能受影响。后续优先实验 `cpus=8, threads_per_mpi_process=8, standard_parallel=all`（先 Data Check），候选矩阵：`8/automatic/all`、`8/8/all`、`4/4/all`、`8/4/all`、`8/2/all`、`8/1/all`。
- 当前决定：DEFERRED，本轮不实际运行任何实验。
- 下一步：按登记的矩阵先 Data Check 后 solve；详细证据见 `docs/TROUBLESHOOTING.md`（本文不重复完整历史）。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/HANDOFF_CURRENT.md`。

### RB-013 — mechanics QA 缺口：contact warnings / PBC large-deformation / quasi-static validity

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查 + 外部 review（对应原 review items 17/18/19，合并登记）
- 优先级：HIGH（for scientific use）；状态：**DEFERRED（TO M4+ mechanics QA）**；类别：mechanics QA
- 问题（三个子项）：
  1. **M2/M3 warnings 未做 mechanics QA**：General Contact double-sided warning、STRAINFREE adjustment、secondary-node opposite-side warnings（M2 共 10 条）、zero-moment warnings（M3 solve 7 条）。均未被证明无害，也不能为"结果干净"直接过滤。
  2. **PBC large-deformation correctness 未科学验证**：PBC keyword/algebraic contract 已实现并静态验证，但大变形全过程物理合理性未做场量 residual QA。
  3. **quasi-static validity 未证明**：Dynamic Implicit + Smooth Step 不自动等于 quasi-static；不能因 Solve 完成就标 quasi-static valid。
- 当前决定：DEFERRED。未来必须结合 contact field、PBC residual、energy balance（ALLKE/ALLIE/ALLAE）、deformation、stress-strain response、curve oscillation 做系统 mechanics QA；无提取证据禁止白名单任何 warning。
- 下一步：M4 ODB extraction 后的 mechanics/contact QA 阶段。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/HANDOFF_CURRENT.md`、`work/fig1_datacheck_m2_final_001`、`work/fig1_solve_m3_20pct_003`（本地证据）。

### RB-014 — solve timeout / child process tree / crash reconciliation

- 日期：2026-09-16；来源：既有登记
- 优先级：HIGH；状态：**DEFERRED（TO M7）**；类别：reliability
- 问题：`TimeoutExpired` 时 structured report 可能不完整；launcher 被 kill 但 standard.exe 等子进程可能残留；interrupted attempt 需要人工 reconciliation。未来需要 watchdog、kill-tree、resume、process adoption、bounded retry，集中在 M7。30曲面实验临时 runner 的教训（double-reserve 等）也属这一层。
- 证据：`docs/TROUBLESHOOTING.md` "Timeout / child process tree 限制" 与 "30曲面临时 runner double-reserve bug"。
- 当前决定：DEFERRED TO M7 可靠性里程碑。
- 下一步：M7 设计 watchdog/kill-tree/resume/reconciliation。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/IMPLEMENTATION_PLAN.md`（阶段 E/F）。

### RB-015 — M4 extraction contract：step time ≠ strain；partial ODB 末点可能是 termination artifact

- 日期：2026-09-16；来源：外部 review（依据 5-case ad-hoc diagnostic 实测，见 RB-005）
- 优先级：HIGH（for future M4）；状态：**ACCEPTED**（作为 M4 extraction/QA 的明确 contract，尚未实现）；类别：M4 contract
- 问题（两条 contract）：
  1. 对 Smooth Step，**step time ≠ engineering strain**。正式横坐标必须来自 `strain = -U3 / L`（本模型 L=10mm），不能以 `step_time × target_strain` 替代。
  2. partial / failed ODB 的最后 history datum 可能是 **termination artifact**（ref30_03 实测：final RF3≈0，与前一点 −12.57N 矛盾）。partial history 可用于诊断，但不能自动作为完整科学曲线。
- 当前决定：ACCEPTED。未来 M4 extraction/QA 实现时必须强制执行以下规则（本轮不施工）：
  - 保留 solver completion status 与 partial/complete provenance；
  - partial/failed history 与 complete result 严格区分；
  - 不把最后一个 datum 自动视为真实最终力学状态；
  - 不自动外推；failed curve 不进入 dataset。
- 下一步：M4 设计与实现时转化为代码 contract + regression test。
- 相关文件：`docs/EXPERIMENT_30_SURFACES_20260915.md`（ad-hoc diagnostic 章节）、`work/diagnostic_stress_strain_5cases_20260916/`（本地证据）。

### RB-016 — cpus=8 + solver 在本机反而更慢（runtime evidence）

- 日期：2026-09-16；来源：外部 review；实测早已入档
- 优先级：LOW（runtime evidence）；状态：**NO_ACTION**（结论已记录于 `docs/TROUBLESHOOTING.md` "8-CPU solver 实验"）；类别：performance evidence
- 实测：同一 accepted deck 单变量实验（`work/fig1_solve_cpu8_validation_001`）：4 CPU + solver ≈ 993s（16m33s）；8 CPU + solver ≈ 1971s（32m51s）。当前 workstation preferred：`cpus=4, standard_parallel=solver`。
- 当前决定：NO_ACTION——无需代码改动；登记为证据。未来性能优化以 wall time / throughput 为准，**不用任务管理器 CPU utilization 作为判据**，也不假设"CPU 更多一定更快"。性能优化方向见 RB-012。
- 相关文件：`docs/TROUBLESHOOTING.md`、`work/fig1_solve_cpu8_validation_001`（本地证据）。

### RB-017 — attempt 不覆盖原则必须继续保持

- 日期：2026-09-16；来源：外部 review
- 优先级：HIGH；状态：**NO_ACTION（CURRENT 政策，正确设计，不做任何修改）**；类别：repo policy
- 问题：这不是缺陷，而是确认。正式 pipeline 现状：existing attempt directory → `OUTPUT_EXISTS` → refuse overwrite（有测试锁定）。昨晚 local batch runner 的 resume collision **不能**成为放宽该原则的理由。
- 当前决定：原则保持。未来 resume 应"创建新 attempt + provenance/reconciliation"，而不是覆盖旧证据。
- 下一步：无（M7 resume 设计时遵守此原则，见 RB-014）。
- 相关文件：`pipeline/common.py`（`reserve_directory`）、`tests/test_core.py`（OUTPUT_EXISTS 测试）、`README.md`（attempt 与结果目录）。

### RB-018 — temporary local batch runner ≠ production batch framework

- 日期：2026-09-16；来源：Pre-M4 cleanup 审计 + 外部 review
- 优先级：MEDIUM；状态：**CURRENT**（事实记录，非待办）；类别：scope
- 问题：30曲面实验使用的 `work/night_batch_30surfaces_20260915/run_batch.py` 只是 local experiment runner（不在正式 production pipeline 内）。它暴露 double reserve、BOM 解析、resume collision 等问题，均不能自动归因于正式 pipeline（2026-09-16 已审计确认正式代码无同类缺陷：`reserve_directory` 每 stage 单次调用、`read_json` 用 `utf-8-sig`、OUTPUT_EXISTS 有测试）。
- 当前决定：CURRENT。正式 batch scheduler/watchdog/recovery 属 M7/M8，不因实验 runner 的存在而提前实现。
- 下一步：M7/M8 设计时把实验 runner 的教训作为输入。
- 相关文件：`work/night_batch_30surfaces_20260915/`（本地证据）、`docs/TROUBLESHOOTING.md`（30曲面 runner 条目）、`docs/EXPERIMENT_30_SURFACES_20260915.md`。

### RB-019 — 30曲面 mesh failure 两例尚未解释

- 日期：2026-09-16；来源：30曲面实验 + 外部 review
- 优先级：MEDIUM；状态：**DEFERRED / INVESTIGATION PENDING**；类别：mesh
- 问题：ref30_01（stage05 Z-periodicity validation failure）与 ref30_22（CGAL access violation 0xC0000005）只有"mesh failed"结论；**不能**直接断言 surface invalid / mesher bug / equation wrong。
- 证据：per-case stage stdout/stderr 保留于 `work/night_batch_30surfaces_20260915/`。
- 当前决定：DEFERRED。以后单独开小轮次诊断（与批量恢复解耦）；冻结 vendor mesher 原则不变。
- 下一步：用户批准的诊断轮次。
- 相关文件：`docs/EXPERIMENT_30_SURFACES_20260915.md`、`docs/TROUBLESHOOTING.md`（30曲面 runner 条目）。

### RB-020 — difficult solve cases 02/03/04 尚未归因

- 日期：2026-09-16；来源：30曲面实验 + 外部 review
- 优先级：MEDIUM/HIGH；状态：**DEFERRED / NUMERICAL / MECHANICAL INVESTIGATION PENDING**；类别：solve
- 问题：ref30_02（stagnation，≈0.312）、ref30_03（TOO MANY ATTEMPTS，≈0.39）、ref30_04（stagnation，≈0.532）已有 partial curves 显示明显不同的响应，但尚不能判断属于：物理失稳 / contact transition / mesh issue / material issue / solver strategy。
- 证据：`docs/TROUBLESHOOTING.md` "30曲面 difficult solve cases"；partial curves 见 `work/diagnostic_stress_strain_5cases_20260916/`。
- 当前决定：DEFERRED。归因必须等 M4 field / energy / contact evidence；在此之前不修改任何物理参数、不宣称模型错误。
- 下一步：M4 extraction + mechanics QA 后系统研究。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/EXPERIMENT_30_SURFACES_20260915.md`。

### RB-021 — config identity 分层的长期技术债

- 日期：2026-09-16；来源：外部 review
- 优先级：LOW/MEDIUM；状态：**DEFERRED**；类别：config identity
- 问题：当前存在 `model_key` / `scaffold_key` / `build_key` 三层 identity，而 numerics/runtime 信息可能混入 identity（见 RB-008）。在未来 batch/cache 建立之前，需统一 physical identity / execution identity / artifact provenance identity 的边界。
- 当前决定：DEFERRED。当前不大改（会影响已验证案例的身份键）。
- 下一步：batch/cache 阶段设计时统一；与 RB-008 联动。
- 相关文件：`pipeline/physical_builder.py`（identity keys）、`config/numerics.example.json`。

### RB-022 — demo material 不是 production material

- 日期：2026-09-16；来源：外部 review
- 优先级：HIGH（for research interpretation）；状态：**CURRENT LIMITATION**；类别：material
- 问题：`config/materials/demo_surrogate.json` 只是 pipeline / mechanics interface validation 材料。任何由它产生的 stress-strain curve **不能**解释为论文材料或实验标定的真实材料结果。
- 当前决定：CURRENT LIMITATION，如实记录（README 已知限制已有相应条目）。未来科研使用前必须明确材料来源与标定。
- 下一步：正式科研数据生产前定型材料（含来源、适用范围、`allow_production_dataset` 语义）。
- 相关文件：`config/materials/demo_surrogate.json`、`README.md`（已知限制）、`docs/PROJECT_STATUS.md`。

