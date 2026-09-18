> **[SCOPE NOTE 2026-09-18]** 条目中引用的旧架构（identity v2 / staging planner /
> 三层 schema / 旧 CLI / 旧配置文件）已被单目录流水线取代；本文件按"状态只演进、
> 条目永不删除"的规则继续维护（状态更新与引用重写）。当前架构以 `README.md`、
> `AGENTS.md`、`docs/HANDOFF_CURRENT.md` 为准。

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
> Reconciliation 登记：2026-09-16（来源：DeepSeek independent review + ChatGPT secondary review；新增 RB-023..RB-030，并就地更新 RB-003 / RB-013 / RB-014 / RB-015 / RB-019 / RB-021。本轮**只登记与文档维护**，未施工任何新技术建议；`D1..D8` 表示该轮 review 的条目编号）。
> Reconciliation 施工：2026-09-18（来源：用户委托的第三方只读审查〔GitHub 公开版〕，经逐条复核确认后由用户授权施工）。缺陷修复：extract 重跑覆盖 `raw_history.json`、`history.csv` 列名对齐 canonical schema、curve_qa `strain_targets` 配置化（RB-011）、curve QA 接入 run_case extract 阶段、extract 阶段补 deck SHA 链；`*Energy Output`/`*Node Output` 频率继承在 `pipeline/build.py` 文档化。状态更新：RB-008 / RB-011 / RB-021 / RB-024 / RB-025 / RB-027 / RB-028 / RB-030 → **RESOLVED**；RB-023 标注**仍活跃**；RB-019 增加新流水线复现线索；全部失效的 Related Files 重写到现行模块名。测试：`pixi run test` → core 165 OK + boundary 5 OK（证据 `work/pixi_tests_hnxdxmd3`）。

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
| RB-008 | 4 | config schema | RESOLVED | MEDIUM | numerics config 混合 physical numerics 与 runtime/orchestration 参数（2026-09-17 重构：simulation.json / runtime.json 职责分离） |
| RB-009 | 12 | repo | DEFERRED | LOW/MEDIUM | .gitattributes `* -text` 作用于全仓库 |
| RB-010 | 13 | data/reproducibility | RESOLVED | MEDIUM | 30 validation equations 已作为 tracked `references/validation_30_surfaces.md` 发布 |
| RB-011 | 14 | pipeline | RESOLVED | HIGH (M4/M5) | curve_qa TARGETS 硬编码到 0.30（2026-09-18：`strain_targets` 进 QA policy） |
| RB-012 | 15 | performance | DEFERRED | HIGH | standard_parallel=all / threads_per_mpi_process 性能债 |
| RB-013 | 17+18+19 | mechanics QA | DEFERRED | HIGH | contact warnings QA / PBC large-deformation / quasi-static validity |
| RB-014 | 20 | reliability | DEFERRED | HIGH | solve timeout / child process tree / resume & reconciliation |
| RB-015 | 8+9 | M4 contract | ACCEPTED | HIGH | M4 extraction contract：step time ≠ strain；partial ODB 末点可能是 termination artifact |
| RB-016 | 16 | performance evidence | NO_ACTION | LOW | cpus=8 + solver 在本机反而更慢（结论已记录） |
| RB-017 | 21 | repo policy | NO_ACTION (CURRENT) | HIGH | attempt 不覆盖原则保持不变 |
| RB-018 | 22 | scope | CURRENT | MEDIUM | temporary local batch runner ≠ production batch framework |
| RB-019 | 23 | mesh | DEFERRED | MEDIUM | ref30_01/ref30_22 mesh 失败原因未解释（INVESTIGATION PENDING；2026-09-18：新流水线可稳定复现同曲面失败，见 RB-019 追加） |
| RB-020 | 24 | solve | DEFERRED | MEDIUM/HIGH | difficult solve cases 02/03/04 尚未归因（INVESTIGATION PENDING） |
| RB-021 | 25 | config identity | RESOLVED | LOW/MEDIUM | model/scaffold/build identity 分层与 runtime 信息混入的长期债（2026-09-17 重构：三层 key 已删除，身份 = 配置内容 digest） |
| RB-022 | 26 | material | CURRENT LIMITATION | HIGH | demo_surrogate 不是 production material，曲线不可作真实材料解释 |
| RB-023 | D1 | M4 extraction / ODB history | ACCEPTED（仍活跃） | HIGH | ODB 内重复整体能量 history key 必须由 extraction 显式消歧（当前默认配置仍产生重复；worker 仅用已文档化的 plain-key 启发式） |
| RB-024 | D2 | M4 data contract | RESOLVED | HIGH | M4 必须先冻结 "RAW → normalization → QA" 的 versioned canonical extraction schema（2026-09-17/18：extract.py canonical 三件套 + curve QA 闭环；schema version 载体未单独实现） |
| RB-025 | D3 | M4 provenance / PBC QA | RESOLVED | MEDIUM | M4 需要 extraction context（2026-09-17 重构：staging 废除，`ingredients/pbc_map.json` 与 deck 同目录且 SHA 进 build_report） |
| RB-026 | D5 | storage / batch reliability | DEFERRED (M7/M8) | MEDIUM/HIGH | 大批量前必须先定义 artifact retention / storage policy |
| RB-027 | D4 | pipeline robustness | RESOLVED | LOW/MEDIUM | M2 completion marker 来源（stdout vs .dat）与大小写策略不一致（2026-09-17 重构：log+dat+stdout 合并小写判定，按 solver 区分 token） |
| RB-028 | D6 | maintainability | RESOLVED | LOW | include 清单与诊断解析逻辑多处重复（2026-09-17 重构：`INCLUDE_ORDER` 与 `parse_diagnostics` 均为单一真值） |
| RB-029 | D8 | repo policy | DEFERRED | LOW | 仓库尚无 License |
| RB-030 | D7 | reproducibility | RESOLVED | MEDIUM | 公开仓库缺 baseline fingerprints（2026-09-17：tracked `tests/fixtures/fig1_20pct_regression/deck_sha256.json`，ODB SHA 语义边界已在文件内声明） |

## 条目详情

### RB-001 — Fig.1 20% validation profile 缺少 tracked 可复现配置

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：HIGH；状态：**RESOLVED**（本轮）；类别：config / reproducibility
- 问题：`config/physics.example.json` 的 `target_compression_strain=0.30`（prototype），而正式 M3 验证成功的是 20%；公开仓库缺少与 M3 成功案例一致的 physics profile。
- 证据：`work/m3_fig1_20pct_inputs/physics.json`（M3 正式使用，SHA256 `9340898e6705049390e5e0005314240a2e2f4720d185a97c1102ed938523601e`）；`work/fig1_solve_m3_20pct_003/solve_report.json`。
- 当前决定：新增 tracked 文件 `config/physics.fig1_20pct_validation.json`，与本地 M3 physics **逐字段一致（byte-identical）**；`physics.example.json`（30%）保留不动，README 明确区分两者。
- 下一步：无需进一步动作；30% target solve 验证属后续里程碑。
- 相关文件：`config/physics.fig1_20pct_validation.json`、`config/physics.example.json`、`README.md`。
- Re-reconciliation（2026-09-18）：上列两个 `physics.*.json` 已在重构中删除；20% validation profile 现即 `config/simulation.json`（`loading.target_compression_strain = 0.2`），deck 指纹见 `tests/fixtures/fig1_20pct_regression/deck_sha256.json`。相关文件已重写为：`config/simulation.json`、`README.md`。

### RB-002 — environment.local.json 损坏静默 fallback；release 要求未强制

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：HIGH；状态：**RESOLVED**（本轮）；类别：environment / release gate
- 问题：① `pipeline/physical_datacheck.py::resolve_launcher` 中，environment.local.json 存在但 JSON 损坏时被 `except: configured=None` 静默吞掉并继续到 PATH 找 launcher（可能命中另一套 Abaqus）；schema 错误同样被忽略。② `abaqus_release_required="2026"` 只在 report 里记录，运行前不比对。
- 证据：`pipeline/physical_datacheck.py` 原 `resolve_launcher`/`query_release` 实现。
- 当前决定：新增 `load_environment_config`（损坏/非法 schema → `CONFIG_INVALID`，不 fallback）与 `enforce_release_gate`（required release 与 launcher 报告 release 不一致或无法确定 → `ABAQUS_RELEASE_MISMATCH`；gate 位于 `reserve_directory` 之前，不产生 partial attempt）；datacheck 与 solve 均接入；report 记录 `release_gate`。回归测试：malformed env 不 fallback、2026/2025 → fail、2026/2026 → pass、unknown → fail、gate 前 no attempt。
- 下一步：无需进一步动作；launcher 系统不大重构。
- 相关文件：`pipeline/physical_datacheck.py`、`pipeline/physical_solve.py`、`tests/test_core.py`。
- Re-reconciliation（2026-09-18）：`load_environment_config` / `enforce_release_gate` / `resolve_launcher` / `query_release` 现集中在 `pipeline/abaqus.py`（datacheck 与 solve 共用）；`tests/test_core.py` 已拆分为按模块的 `tests/test_*.py`。相关文件已重写为：`pipeline/abaqus.py`、`tests/test_abaqus.py`。

### RB-003 — HANDOFF / ROADMAP / IMPLEMENTATION_PLAN 旧状态文字

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：MEDIUM；状态：**RESOLVED**（本轮）；类别：docs consistency
- 问题：① `docs/HANDOFF_CURRENT.md` 测试数量写 `115/115`（当前实际 142/142 core + 8/8 boundary）；② `docs/PROJECT_ROADMAP.md` 第 9 节标题仍写"当前唯一主目标：M3"；③ `docs/IMPLEMENTATION_PLAN.md` 开头的 2026-09-13 历史性描述（"下列求解/Data Check……本次没有启动"）无 HISTORICAL 标注。
- 证据：上述文件对应行。
- 当前决定：测试数量更新为当前真实结果；ROADMAP 第 9 节目标改为 M4；IMPLEMENTATION_PLAN 旧描述加 `[HISTORICAL / SUPERSEDED]` 标注（历史文字保留不删除）。HANDOFF 基准 SHA 改为 "last reviewed checkpoint" 表述，避免每个 docs commit 立即过期。
- 下一步：文档状态描述以后随 checkpoint 更新。
- 相关文件：`docs/HANDOFF_CURRENT.md`、`docs/PROJECT_ROADMAP.md`、`docs/IMPLEMENTATION_PLAN.md`。
- 追加记录（2026-09-16 maintenance checkpoint，follow-up）：RB-003 的"更新为当前真实值"**再次漂移**——`3d99f8a` 之后 `tests/test_core.py` 的 test method 数由 142 增至 151，而 `docs/PROJECT_STATUS.md` / `docs/HANDOFF_CURRENT.md` 仍写 142/142。本轮按真实执行结果（`pixi run test` → core `Ran 151 tests ... OK` + boundary `Ran 8 tests ... OK`）把 **CURRENT 表述改为 checkpoint-bound 表述**；per-milestone 历史数量（115 / 138）**保留不改**，仅加 `[HISTORICAL]` 标注。
- 长期决定（沿用并强化）：**测试数量必须与"某次验证 checkpoint"绑定，不允许把一个旧数量长期当作当前真值**；文档应记录命令（`pixi run test`）与证据目录，而不是写死数字。
- 状态：**保持 RESOLVED**（本次为同一问题的 follow-up maintenance，不新开条目）。
- Re-reconciliation follow-up（2026-09-18）：第三方审查实测 README 又写死"147 个 unittest"（当前实际 core 150 + boundary 5，模块拆分后旧 `tests/test_core.py` 的 151/8 也已失效）。本轮把 README 测试行改为"命令 + 证据目录（`work/pixi_tests_*`）"表述，不再写死数字——沿用上面的长期决定。

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
- Re-reconciliation（2026-09-18）：zero-byte required artifacts 检查现在 `pipeline/abaqus.py`（datacheck 与 solve 共用 artifact 判定）；相关文件已重写为：`pipeline/abaqus.py`、`tests/test_abaqus.py`。

### RB-007 — STAGES 中 SOLVE 描述宣称 watchdog

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查
- 优先级：LOW；状态：**RESOLVED**（本轮）；类别：pipeline/docs wording
- 问题：`pipeline/mesher_adapter.py` STAGES 的 SOLVE 描述为 "Dynamic implicit solve with resource limits and watchdog"，而 production watchdog 属 M7、尚未实现；`pixi run plan` 会误导读者。
- 证据：`pipeline/mesher_adapter.py` STAGES 定义。
- 当前决定：描述改为 "Dynamic implicit solve with resource limits; production watchdog/recovery is deferred to M7"。只改措辞，不实现 watchdog。
- 下一步：无需进一步动作。
- 相关文件：`pipeline/mesher_adapter.py`。
- Re-reconciliation（2026-09-18）：`pipeline/mesher_adapter.py` 已删除；现行 stage 清单与 `pixi run plan` 文本在 `pipeline/run_case.py`（`STAGES`）与 `run.py`，solve 描述不再宣称 watchdog。相关文件已重写为：`pipeline/run_case.py`、`run.py`。

### RB-008 — numerics config 混合 physical numerics 与 runtime/orchestration 参数

- 日期：2026-09-16；来源：外部 review（checkpoint 22e1a59）
- 优先级：MEDIUM；状态：**RESOLVED**（2026-09-17 重构）；类别：config schema
- 问题：`config/numerics.example.json` 同时包含两类职责——
  - 物理/求解步数值：`initial_increment_s`、`minimum_increment_s`、`maximum_increment_s`、`maximum_increments`；
  - runtime / orchestration：`cpus_per_job`、`maximum_concurrent_solves`、`max_attempts_including_base`、`solver_wall_limit_s`、stagnation 等。
  M3 已经有独立的 solve_runtime policy（`config/solve_runtime.*.json`），配置职责重复；runtime 字段还可能污染 `model_key`/`scaffold_key` identity。
- 当前决定：DEFERRED。未来拆分为 physical numerics vs runtime/resources/reliability 两类 schema；本轮不改 schema（影响 builder 契约与已验证案例身份键）。
- 下一步：M4/M5 config 设计时统一处理；与 RB-021（identity 分层）联动。
- 相关文件：`config/numerics.example.json`、`pipeline/physical_builder.py`、`config/solve_runtime.example.json`。
- 解决记录（2026-09-18 re-reconciliation）：2026-09-17 重构后配置收敛为 `config/simulation.json`（纯物理/数值/输出参数，进入 deck 与 case 身份摘要）与 `config/runtime.json`（机器/runtime 参数：launcher、cpus、timeout、`results.keep_odb`，**不进** case 身份）；`numerics.*.json` / `solve_runtime.*.json` 已删除。物理与 runtime 参数不再可能混入同一 identity。相关文件已重写为：`config/simulation.json`、`config/runtime.json`、`pipeline/build.py`、`pipeline/run_case.py`。

### RB-009 — .gitattributes `* -text` 作用范围过宽

- 日期：2026-09-16；来源：外部 review
- 优先级：LOW/MEDIUM；状态：**DEFERRED**；类别：repo policy
- 问题：`.gitattributes` 当前 `* -text`（全仓库禁用换行转换，最初为保护 vendor/historical byte identity），但普通 Python/Markdown 也因此关闭 text normalization，容易产生 CRLF/line-ending noise。长期应只对真正要求 byte-exact 的对象（vendor/、legacy evidence、特定 binary-like files）使用 `-text`，普通源码/docs 用正常 `text` + LF。
- 当前决定：DEFERRED。改动可能产生大规模 line-ending diff，必须单独阶段处理，不顺手修改；vendor 冻结期间不动。
- 下一步：单独的仓库整理阶段评估。
- 相关文件：`.gitattributes`。

### RB-010 — 30 validation equations 位于 git-ignored reference

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查 + 外部 review
- 优先级：MEDIUM；状态：**RESOLVED**（2026-09-16 references publication maintenance）；类别：data / reproducibility
- 问题：30 曲面验证实验的方程清单在 `reference/selected_30_diverse_cases_report.md`（git-ignored 本地证据）；公开仓库记录了 28/30 mesh PASS 等结论，但其他用户无法完整复现实验所用方程集。
- 当前决定：DEFERRED。以后考虑新增 tracked 的 `examples/validation_30_surfaces.json`，只含 `case_id`、`surface_expression`、`equation_sha256`；不提交论文 PDF 或原始 dataset。`reference/` 保持只读不动。
- 下一步：用户确认后设计 tracked manifest。
- **解决记录（2026-09-16 maintenance）**：30 个验证方程已作为 tracked 文档 **`references/validation_30_surfaces.md`** 进入仓库（同时新增 `references/README.md`、`references/PAPERS.md`）。内容取自本地 `reference/selected_30_diverse_cases_report.md`（SHA256 `d42e9461…d889b`，与该实验 `batch_source_manifest.json` 记录的 `source_sha256` 相同），并已核对 30 条方程**顺序与文本完全一致**（30/30）、metadata 列逐字一致。`reference/` 仍为 git-ignored 本地原始资料，未移动、未删除、未提交。原计划的 `examples/*.json` 形式由该 Markdown tracked reference 取代。
- 解决摘要：**Resolved in this references publication maintenance**（30 validation equations 现已在 tracked repository 中可读，无需访问本地 `reference/`）。
- 相关文件：`references/validation_30_surfaces.md`、`references/README.md`、`reference/selected_30_diverse_cases_report.md`（本地）、`docs/EXPERIMENT_30_SURFACES_20260915.md`。

### RB-011 — curve_qa TARGETS 硬编码到 0.30

- 日期：2026-09-16；来源：Pre-M4 cleanup 审查 + 外部 review
- 优先级：HIGH（for M4/M5）；状态：**RESOLVED**（2026-09-18）；类别：pipeline
- 问题：`pipeline/curve_qa.py` 的 11 点 TARGETS 最终到 `0.300`（按历史手工 30% 目标标定），因此不能直接用于 20% validation case 或任意 compression target。
- 当前决定：DEFERRED TO M4/M5。未来 target/sampling 必须 config-driven 并禁止外推；现在不改。
- 下一步：M4/M5 设计 curve-QA policy 时处理。
- 相关文件：`pipeline/curve_qa.py`、`config/quality.example.json`。
- 解决记录（2026-09-18）：模块级 `TARGETS` 常量删除；QA policy 新增必填 `strain_targets`（校验：≥2 个有限数、严格递增，非法值 `CONFIG_INVALID`）；`config/quality.example.json` 保留论文 11 点为示例并在 `note` 中声明 20% 曲线对它会**按设计**判 `TARGET_RANGE_NOT_REACHED`；QA 输出键改为 `strain_targets` / `stress_at_targets_MPa`。回归测试：`tests/test_curve_qa.py`。相关文件不变并追加：`tests/test_curve_qa.py`。

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
- 追加（2026-09-16 DeepSeek review，M4-0 前置，仅登记）：
  - 在决定"是否需要新的 mechanics-QA outputs profile + 新 solve"之前，必须先做一个 **M4-0 ODB Capability Inventory**（只读现有 Fig.1 complete M3 ODB）：列出 steps / frames / frame step times / `fieldOutputs` keys / `historyRegions` / `historyOutputs`（含 repeated keys）/ `nodeSets` / `elementSets` / 接触相关输出。
  - **History region ≠ Field Output**：上一轮 review **没有**做完整 `fieldOutputs` inventory，因此"现有 ODB 一定不足、必须重新 Solve"属于**未经证实的推断**，不得据此授权新 solve。
  - 明确（本轮不施工）：**DO NOT** modify existing M3 baseline output profile；**DO NOT** assume a new solve is already authorized。只有 inventory 证明现有证据不足后，才讨论新 profile + 新 attempt。
- 相关文件：`docs/TROUBLESHOOTING.md`、`docs/HANDOFF_CURRENT.md`、`work/fig1_datacheck_m2_final_001`、`work/fig1_solve_m3_20pct_003`（本地证据）。

### RB-014 — solve timeout / child process tree / crash reconciliation

- 日期：2026-09-16；来源：既有登记
- 优先级：HIGH；状态：**DEFERRED（TO M7）**；类别：reliability
- 问题：`TimeoutExpired` 时 structured report 可能不完整；launcher 被 kill 但 standard.exe 等子进程可能残留；interrupted attempt 需要人工 reconciliation。未来需要 watchdog、kill-tree、resume、process adoption、bounded retry，集中在 M7。30曲面实验临时 runner 的教训（double-reserve 等）也属这一层。
- 证据：`docs/TROUBLESHOOTING.md` "Timeout / child process tree 限制" 与 "30曲面临时 runner double-reserve bug"。
- 当前决定：DEFERRED TO M7 可靠性里程碑。
- 下一步：M7 设计 watchdog/kill-tree/resume/reconciliation。
- 追加（2026-09-16 DeepSeek review，仅登记）：**future batch controller 必须解析 structured JSON/report status**（`solve_report.json` / `datacheck_report.json`），**不得仅依赖 process return code**。当前 CLI 语义（0 = clean、3 = non-clean/needs review、2 = invocation/config failure）是合理的人类 CLI policy，**本轮不修改 `run.py`**。
- 追加 Next Action（M7 实现时）：为 `DATACHECK_TIMEOUT` 与 `SOLVE_TIMEOUT` 补充 regression tests（本轮不新增测试；当前测试套件未覆盖超时路径）。
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
- 追加（2026-09-16 DeepSeek review）：上述 contract 在当前 worker 输出层**没有 provenance carrier**——`abaqus_worker/export_history.py` 的 raw result 不携带 solve completion status、ODB SHA256、ODB size、`solve_report` identity、complete/partial provenance。因此"partial/failed curve 不能当完整科学结果"目前只存在于文档，未落到任何机器可读载体。
- 补充决定（本轮不施工）：未来 M4 extraction report 必须绑定 **source solve status / completion evidence / ODB SHA256 / ODB size / source solve report + build identity / extraction schema version**。职责边界：**Abaqus Python worker = read-only raw ODB extraction only**；**Pixi/controller = provenance + solve completion + normalization + QA orchestration**。worker 不得自行判断 dataset accepted / mechanics pass / scientific validity。
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
- Re-reconciliation（2026-09-18）：OUTPUT_EXISTS 测试现在 `tests/test_regression.py`；stage 目录替换语义为 `pipeline/run_case.py::set_aside`（改名保留，永不删除）。相关文件已重写为：`pipeline/common.py`、`pipeline/run_case.py`、`tests/test_regression.py`。

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
- 追加线索（2026-09-16 DeepSeek review；**仅为 observed evidence / investigation hint，不是 root cause**）：
  - `ref30_01`：`work/nb30_ref30_01_mesh/engine/cases/ref30_01/shell/ref30_01_shell_report.json` 显示失败**只在 Z**：`low_nodes=307 / high_nodes=306`、`bijective=false`、`symmetric_matches=306`、`max_mismatch≈0.0311`；X/Y 两者均 `bijective=true`（mismatch ≈8.9e-16）；CGAL 阶段本身为 `STATUS: PASS`（clipping=0，unplaceable facets 文件仅表头）。
  - `ref30_22`：`work/nb30_ref30_22_mesh/ref30_22_mesh_CGAL.stdout.txt` 停在 `Generating feature-protected periodic mesh...` 之后即中断（stderr 仅一条无关的 `SSL_CERT_DIR` 警告），输出目录为空；`batch_status.json` 记录 0xC0000005。
  - 上述只是现象定位，**不得**据此写成 mesher bug / surface invalid / 方程错误。
- 当前决定：DEFERRED。以后单独开小轮次诊断（与批量恢复解耦）；冻结 vendor mesher 原则不变。
- 下一步：用户批准的诊断轮次。
- 相关文件：`docs/EXPERIMENT_30_SURFACES_20260915.md`、`docs/TROUBLESHOOTING.md`（30曲面 runner 条目）。
- 追加线索（2026-09-18，仍仅为 observed evidence / investigation hint，不是 root cause）：新单目录流水线**稳定复现**同曲面失败——`work/r3_smoke/batch_001/` 中 `diverse_01` 在冻结 vendor 阶段 05 判 PBC 配对非双射（历史 `ref30_01` 对同一曲面同样 `STEP 05 STATUS: FAIL`），batch 正确记为 `MESH_STAGE_FAILED` 并继续；见 README「真实验证状态」。相比 30 曲面临时 runner，这是干净得多的诊断入口（无 staging、无 double-reserve 历史包袱）。诊断仍需用户批准的专门轮次。相关文件追加：`README.md`。

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
- 优先级：LOW/MEDIUM；状态：**RESOLVED**（2026-09-17 重构）；类别：config identity
- 问题：当前存在 `model_key` / `scaffold_key` / `build_key` 三层 identity，而 numerics/runtime 信息可能混入 identity（见 RB-008）。在未来 batch/cache 建立之前，需统一 physical identity / execution identity / artifact provenance identity 的边界。
- 当前决定：DEFERRED。当前不大改（会影响已验证案例的身份键）。
- 下一步：batch/cache 阶段设计时统一；与 RB-008 联动。
- 相关文件：`pipeline/physical_builder.py`（identity keys）、`config/numerics.example.json`。
- 追加（2026-09-16 DeepSeek review）：除"三层 identity 分层"外，还存在**对字节/格式过敏**的问题——`scaffold_key` 含 numerics **raw file SHA**（仅重排/重新格式化该 JSON，identity 即改变，而渲染出的 deck 完全不变），并且 `model_key` 把人类可读元数据（`profile_id`、`note`、`validated_to_target`）计入物理身份；`mesh_request_key` 把 `pixi.lock` / CGAL exe 哈希计入"网格身份"（保守但会阻止合法复用）。
- 明确分类需求（长期）：**physical identity / execution identity / artifact provenance identity** 三者必须分开，physical identity 只允许来自语义规范化。
- 本轮不改（这些 key 已属历史证据的一部分）；状态继续 **DEFERRED**。
- 解决记录（2026-09-18 re-reconciliation）：2026-09-17 重构删除了三层 key 与全部 key 分层——case 身份 = `digest(case)`（内容摘要，与文件字节无关）、simulation 身份 = `digest(simulation)`；同一 case 以文件或 batch 内存记录提供时身份相同（实测 `run-case --case <batch>/fig1/case_used.json` 全部 skip）。`physical_builder.py` / `numerics.example.json` 已不存在。相关文件已重写为：`pipeline/run_case.py`（`_invalidated` / resume 逻辑）。

### RB-022 — demo material 不是 production material

- 日期：2026-09-16；来源：外部 review
- 优先级：HIGH（for research interpretation）；状态：**CURRENT LIMITATION**；类别：material
- 问题：`config/materials/demo_surrogate.json` 只是 pipeline / mechanics interface validation 材料。任何由它产生的 stress-strain curve **不能**解释为论文材料或实验标定的真实材料结果。
- 当前决定：CURRENT LIMITATION，如实记录（README 已知限制已有相应条目）。未来科研使用前必须明确材料来源与标定。
- 下一步：正式科研数据生产前定型材料（含来源、适用范围、`allow_production_dataset` 语义）。
- 相关文件：`config/materials/demo_surrogate.json`、`README.md`（已知限制）、`docs/PROJECT_STATUS.md`。
- Re-reconciliation（2026-09-18）：`config/materials/demo_surrogate.json` 已删除；材料现内联在 `config/simulation.json` 的 `material` block（进入 case 身份摘要与 build report）。限制本身不变，由报告的 `claims.dataset_eligible=false` 与 summary `note` 承担。相关文件已重写为：`config/simulation.json`、`README.md`。

### RB-023 — M4 必须先消歧 ODB 内重复的整体能量 history key

- 日期：2026-09-16；来源：DeepSeek independent review + ChatGPT secondary review（D1，2026-09-16）
- 优先级：HIGH；状态：**ACCEPTED（仍活跃，2026-09-18 复核确认）**；类别：M4 extraction / ODB history
- **Observed Fact**：当前 accepted 输出基线（`config/outputs.example.json` / `work/fig1_solve_m3_20pct_003/blocks/outputs.inc`）**同时**包含"显式 `*Energy Output`（`frequency=1`）"与"`*Output, history, variable=PRESELECT, frequency=10`"。在已有 M3 ODB 的 history inventory（`work/diagnostic_stress_strain_5cases_20260916/fig1_regions.json`）中，同一 `Assembly Assembly-1` region 内出现重复量：`ALLKE` 与 `ALLKE (Repeated: key = Compression, 10)`、`ALLIE` / `(…, 20)`、`ALLAE` / `(…, 17)`、`ALLPD` / `(…, 13)`、`ALLWK` / `(…, 12)`、`ETOTAL` / `(…, 21)`。
- **Inference（不得当作已证实事实）**：重复来自上述两个请求同时覆盖同一组整体能量量，且两者采样频率不同（1 vs 10）。**不得**写成"没有 `Repeated` 后缀的那一条就是正确序列"——该命名不应被假设为稳定的 public API。
- **Recommendation / Decision（未来 M4 必须执行；本轮 DO NOT IMPLEMENT）**：
  1. 对同名 energy 候选做 **inventory**；
  2. 对每条记录 `exact ODB key`、`point count`、`time range`、`sampling density`；
  3. 依**明确的 extraction policy** 选定 QA 使用的序列；
  4. 在 extraction report 中记录：被选序列、选择理由、未使用的 candidate；
  5. **不允许**靠字符串后缀推断 provenance。
- 本轮：**DO NOT IMPLEMENT**（未修改 outputs、未修改 extraction、未重跑任何作业）。
- 相关文件：`config/outputs.example.json`、`abaqus_worker/export_history.py`、future M4 extraction、`work/diagnostic_stress_strain_5cases_20260916/fig1_regions.json`（本地证据）。
- Re-reconciliation（2026-09-18，第三方审查复核后**确认为仍活跃**，不是已完成项）：
  - 重复请求的**来源仍在当前默认配置里**：`config/simulation.json` 同时有 `history_frequency=1`（显式 energy/node 请求继承）与 `preselect_history_frequency=10`（PRESELECT 组），同一批整体能量量仍会以两种频率写入 ODB。
  - 频率继承机制已在 `pipeline/build.py::render_outputs` docstring 文档化（含"显式频率会改变冻结 deck 字节，必须先真实 Data Check 验证"）。
  - extraction 层现在由 `abaqus_worker/export_history.py::_series` 以 **exact → plain → loose** 偏好选 key，并把选中 key 记入 raw 文档的 `chosen_keys`。该启发式已写进 worker docstring（不再是"未记录"），但它**仍是字符串命名启发式**，不等于本条目要求的 inventory + 明确 extraction policy：5 点 Recommendation（inventory、逐条记录 point count / time range / density、policy 选定、report 记录理由、禁止后缀推断）**均未实现**。
  - `config/outputs.example.json` 已删除，现行输出请求在 `config/simulation.json` 的 `output.requests`。相关文件已重写为：`config/simulation.json`、`pipeline/build.py`、`abaqus_worker/export_history.py`、`pipeline/extract.py`。

### RB-024 — M4 需要 versioned canonical extraction schema（RAW → normalization → QA）

- 日期：2026-09-16；来源：DeepSeek independent review + ChatGPT secondary review（D2，2026-09-16）
- 优先级：HIGH；状态：**RESOLVED**（2026-09-17/18，核心闭环；schema version 载体未单独实现）；类别：M4 data contract
- **Observed Fact**：`pipeline/curve_qa.py` 要求列为 `time_s / u3_mm / rf3_N / ALLKE / ALLIE / ALLAE`；而唯一已存在的 ad-hoc 诊断 CSV（`work/diagnostic_stress_strain_5cases_20260916/*.csv`）使用另一套列名（`time / U3_mm / RF3_N / engineering_strain / engineering_stress_MPa`）**且没有 energy 列**；`curve_qa.TARGETS` 又固定到 `0.300`。因此现有 QA 入口无法消费现有真实数据（`HISTORY_MISSING`）。
- **区分**：本条目**不重复 RB-011**。RB-011 负责"TARGETS / target strain 配置化"；本条目负责"**formal extraction ↔ normalization ↔ QA 的唯一数据 schema**"。
- **Decision（架构原则；本轮 DO NOT IMPLEMENT）**：M4 开始时应先定义 **versioned canonical schema**，分层为
  `ODB → RAW extraction → Normalization / alignment → QA`
  - **RAW 层**：保留 native time axes；不插值；不外推；不丢原始 key；不隐藏 repeated history；不删除 termination artifact。
  - **Normalization 层**才产生：`time_s`、`u3_mm`、`rf3_N`、`engineering_strain`、`engineering_stress_MPa`、aligned energy / metadata。
  - **QA**：只消费 versioned canonical schema。
- 本轮：**DO NOT IMPLEMENT**（未修改 `curve_qa.py`、未写 extraction pipeline、未改 CSV 契约）。
- 相关文件：`pipeline/curve_qa.py`、`run.py`（`qa-history`）、`abaqus_worker/export_history.py`、`config/quality.example.json`。
- 解决记录（2026-09-18 re-reconciliation）：Observed Fact 中的三处断裂已全部闭合——
  - `pipeline/extract.py` 产出 canonical 三件套，`history.csv` 列名即 normalization schema：`time_s`、`u3_mm`、`rf3_N` + 实际存在的 energy 列；缺失变量不补 0，在 summary 的 `missing` 里列出；
  - RAW 层 = `results/raw_history.json`（保留 native time axes、原始 region/key、`chosen_keys`，不做删改）；
  - QA 只消费 canonical schema：`pipeline/curve_qa.py::read_history_csv` / `record_curve_qa`，并已接入 `run_case` extract 阶段（`runtime.results.curve_qa_policy` 配置时写 `results/curve_qa.json`）；`qa-history` 复用同一 reader，对流水线自身输出可直接运行（实测冒烟通过）。
  - 未尽事项：RAW→Normalization→QA 的 **schema version 载体**（versioned 声明字段）未单独实现，如未来 schema 演进需补。相关文件追加：`pipeline/run_case.py`、`tests/test_curve_qa.py`。

### RB-025 — M4 extraction context / PBC provenance

- 日期：2026-09-16；来源：DeepSeek independent review + ChatGPT secondary review（D3，2026-09-16）
- 优先级：MEDIUM；状态：**RESOLVED**（2026-09-17 重构使 context 天然可溯源）；类别：M4 provenance / PBC QA
- **Observed Fact**：M2/M3 attempt 的 staging 集合只含 deck + 9 个 include + provenance JSON（`pipeline/physical_datacheck.py` / `pipeline/physical_solve.py` 的 `_STAGED_DECK_FILES` / `_PROVENANCE_FILES`），**不含** `ingredients/pbc_map.json`、`ingredients/model_inputs.json`（实测 `work/fig1_solve_m3_20pct_003/ingredients/` 仅 `shell_mesh.inc` + `lateral_pbc.inc`）。若未来 PBC residual QA 需要 (dependent, root, shift) 映射，目前只能重新解析 1722 条 `*Equation` 文本，或回退到 build attempt / 外部 mesh bundle。
- **Decision（本轮不施工）**：未来 M4 应定义 **extraction context**，至少可追溯：`solve_report`、`model_manifest`、`pbc_map`、`model_inputs` / geometry normalization、output profile identity、ODB，以及上述对象的 **SHA256**。**不要**通过重新解析 `*Equation` 文本来恢复拓扑。
- 本轮：**不修改任何 staging 列表**（未改 `physical_datacheck.py` / `physical_solve.py`）。
- 相关文件：`pipeline/physical_datacheck.py`、`pipeline/physical_solve.py`、`pipeline/prepare_fe.py`（`pbc_map.json` 产出方）、future M4 extraction。
- 解决记录（2026-09-18 re-reconciliation）：staging 本身已在 2026-09-17 重构中废除——deck、`ingredients/pbc_map.json`、报告与 ODB 同在一个 `work/<case_id>/abaqus/` 目录，不再有"staging 集合缺项"问题；`pbc_map.json` 的 SHA256 记录在 `build_report.json` 的 `deck.provenance`，extract 经同一目录的 build_report 取模型事实（且 extract 已接 deck SHA 链）。"重新解析 `*Equation` 文本恢复拓扑"的场景不再存在。相关文件已重写为：`pipeline/build.py`、`pipeline/run_case.py`、`pipeline/extract.py`。

### RB-026 — 大批量 artifact retention / storage policy 必须先定义

- 日期：2026-09-16；来源：ChatGPT secondary review（D5，2026-09-16），基于既有 attempt 实测体积
- 优先级：MEDIUM/HIGH；状态：**DEFERRED TO M7/M8**；类别：storage / batch reliability
- **Observed Fact**：现有 attempt 中部分 Abaqus 中间文件可达约百 MB 量级（例如 `work/fig1_datacheck_m2_final_001/fig1_m2_datacheck.stt` ≈126.9 MB；ODB ≈16 MB/算例）。因此未来 20k 规模既不能"所有文件永久完整保留"，也不能"成功后把 ODB 全部删除"。
- **Decision（未来 batch 前必须定义；本轮 DO NOT IMPLEMENT / DO NOT DELETE ANYTHING）**：至少区分五类 artifact：
  - A. permanent scientific evidence
  - B. permanent standardized result
  - C. diagnostically valuable failure artifact
  - D. reproducible intermediate artifact
  - E. solver scratch / disposable temporary artifact
  不同结局（`FAILED` / `QA_FAIL` / `SUCCESS + QA_PASS`）可采用不同 retention policy。任何自动删除必须：**policy-driven、post-QA、留下 manifest/hash/provenance**，且**不得删除唯一科学证据**。
- 本轮：**未删除、未移动、未归档任何 `work/` 文件**。
- 相关文件：`docs/IMPLEMENTATION_PLAN.md`（阶段 G 放量条件）、`docs/TROUBLESHOOTING.md`（attempt 保存政策）、`work/`（本地证据）。

### RB-027 — M2 completion marker 来源（stdout vs .dat）与大小写策略不一致

- 日期：2026-09-16；来源：DeepSeek independent review + ChatGPT secondary review（D4，2026-09-16）
- 优先级：LOW/MEDIUM；状态：**RESOLVED**（2026-09-17 重构）；类别：pipeline robustness / runtime portability
- **Observed Fact**：`pipeline/physical_datacheck.py` 的 `datacheck_complete_evidence` 只在 `log_text + dat_text`（已小写化）中查找 marker，**不解析 stdout capture**；而 `docs/TROUBLESHOOTING.md` 明确记载"Abaqus 2026 datacheck interactive 不写 `.log`，stdout 承担 log 角色"。`pipeline/physical_solve.py` 对 `.sta` 的 marker 检查则是**区分大小写**的精确匹配。当前真实 baseline 正常：`work/fig1_datacheck_m2_final_001/fig1_m2_datacheck.dat` 第 465 行确实含 `ANALYSIS DATACHECK COMPLETE`（2026-09-16 只读核对）。
- **Inference**：潜在风险是**跨版本/跨运行模式的 false negative**（marker 只出现在 stdout 时会被判 `DATACHECK_FAILED`），**不是 false PASS**；现有 mock 测试把 marker 写进 `.dat`，无法发现该差异。
- **Recommendation**：M7 或 M4 顺带处理（改为"`.dat` 或 stdout capture 命中"并统一大小写策略）。**本轮不改代码、不加测试。**
- 相关文件：`pipeline/physical_datacheck.py`、`pipeline/physical_solve.py`、`tests/test_core.py`、`docs/TROUBLESHOOTING.md`。
- 解决记录（2026-09-18 re-reconciliation）：重构后的 `pipeline/abaqus.py`（约 577-585 行）把 log、`.dat` 与 stdout capture **合并小写后**统一查找完成标记，并按 solver 区分 token（Standard：`analysis datacheck complete`；Explicit：`the analysis has completed successfully`，2026 版实测）； Recommendations 的两条（stdout 纳入 + 统一大小写）均已实现。相关文件已重写为：`pipeline/abaqus.py`、`tests/test_abaqus.py`、`docs/TROUBLESHOOTING.md`。

### RB-028 — include 清单与诊断解析逻辑多处重复（单一真值缺位）

- 日期：2026-09-16；来源：DeepSeek independent review（D6，2026-09-16）
- 优先级：LOW；状态：**RESOLVED**（2026-09-17 重构）；类别：maintainability / duplicated source of truth
- **Observed Fact**：同一 include 顺序/清单在 `pipeline/physical_builder.py`（`_STATIC_INCLUDE_ORDER`）、`pipeline/physical_datacheck.py`、`pipeline/physical_solve.py`（各一份 `_STAGED_DECK_FILES`）中出现三处；诊断扫描/策略解析逻辑在 datacheck 与 solve 两模块间复制（`_scan_diagnostic_file`、`_resolve_execution_policy` 等）。
- **Inference**：未来新增 block 时需改多处；若 staging 清单漏项，失败发生在真实 Abaqus 启动之后（fail-safe，但反馈环变长）；解析逻辑分叉可能导致两个 stage 对同一段 Abaqus 文本给出不同结论。
- **Recommendation**：M4/M5 阶段在**有真实回归**的前提下收敛为单一真值并上移公共解析函数。**本轮不重构。**
- 相关文件：`pipeline/physical_builder.py`、`pipeline/physical_datacheck.py`、`pipeline/physical_solve.py`、`pipeline/diagnostics.py`。
- 解决记录（2026-09-18 re-reconciliation）：重构后两个"单一真值"均成立——include 顺序只有 `pipeline/build.py::INCLUDE_ORDER` 一处定义（`pipeline/abaqus.py` 直接 import 使用）；诊断解析只有 `pipeline/abaqus.py::parse_diagnostics` 一个实现（datacheck / solve / mesh datacheck 三处调用），不再有分叉风险。相关文件已重写为：`pipeline/build.py`、`pipeline/abaqus.py`。

### RB-029 — 仓库尚无 License

- 日期：2026-09-16；来源：DeepSeek independent review + ChatGPT secondary review（D8，2026-09-16）
- 优先级：LOW；状态：**DEFERRED**；类别：repo policy / public repository
- **Observed Fact**：仓库无 `LICENSE` 文件，`README.md` 末尾如实写"仓库许可尚未选定"。
- **Recommendation**：由用户决定 license 类型；属于公开科研平台/数据集来源的可用性问题，不阻塞任何里程碑。**本轮不添加 LICENSE。**
- 相关文件：`README.md`、仓库根（无 `LICENSE`）。

### RB-030 — 公开仓库缺 baseline fingerprints（并明确 ODB SHA 的语义边界）

- 日期：2026-09-16；来源：DeepSeek independent review + ChatGPT secondary review（D7，2026-09-16）
- 优先级：MEDIUM；状态：**RESOLVED**（2026-09-17）；类别：reproducibility / public repository
- **Observed Fact**：tracked `docs/LOCAL_EVIDENCE.json` 已记录 Fig.1 clean bundle 的**输入**指纹（`fig1_shell.npz` `ef919779…`、report `047268c9…`，与 M3 manifest 的 `mesh_source_hashes` 一致）；tracked `config/physics.fig1_20pct_validation.json` 与 M3 实配逐字节相同（`9340898E…`）。但**没有任何 tracked 文件**记录 M3 accepted 产物的身份：`model_key` / `scaffold_key` / `build_key` / `physical.inp` SHA / expected completion status（`git grep` 无命中，仅存在于 git-ignored `work/`）。
- **Recommendation（未来 tracked，可含 `model_key`、`build_key`、`physical.inp` SHA、相关 config SHA、mesh source hashes、Abaqus release、target strain、expected completion status）**：
  - **重要边界**：ODB SHA 只能表示"这个具体 artifact 的身份"，**不得**把"别人重算出的 ODB SHA 必须一样"当作科学复现通过标准。
- 本轮：**不创建 `BASELINE_FINGERPRINTS` 文件**（只登记意见）。
- 相关文件：`docs/LOCAL_EVIDENCE.json`、`README.md`、`docs/PROJECT_STATUS.md`、`work/fig1_solve_m3_20pct_003/`（本地证据）。
- 解决记录（2026-09-18 re-reconciliation）：tracked **`tests/fixtures/fig1_20pct_regression/deck_sha256.json`** 记录 Fig.1 20% case 的 10 个 deck 文件 SHA256、mesh source hashes（npz/pairs 逐字节、report 走契约校验）、config 指向与来源 attempt；`tests/test_regression.py` 用 tracked config 重建 deck 后逐字节比对。文件内明确声明 "Artifact identity only: NOT a claim that Abaqus acceptance or the solution is reproducible"，与本条目的 ODB SHA 语义边界一致。相关文件已重写为：`tests/fixtures/fig1_20pct_regression/deck_sha256.json`、`tests/test_regression.py`。

