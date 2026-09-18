# HANDOFF_CURRENT

本文件是当前状态的**唯一真值摘要**（2026-09-17，第 3 轮：批量运行打通；
2026-09-18 第 4 轮：第三方审查修复（第 8 节）+ ref30 implicit/explicit 计算实验（第 9 节））。
其余 `docs/*.md` 均已标记 SUPERSEDED，不再同步。

## 1. 现在能做什么

```powershell
# 一个 case
pixi run cli run-case --case config/cases/fig1.json --simulation config/simulation.json

# 很多 case（20,000+）
pixi run cli run-batch --cases config/cases.jsonl --case-defaults config/case_defaults.json `
    --simulation config/simulation.json --work-root work/batch_001 --workers 1
```

`mesh → mesh_datacheck → build → datacheck → solve → extract` 六个 stage 全通；
单 case 可续跑，批量 = 逐个调用 `run_case()`，产出 `batch_summary.csv` /
`results_index.jsonl` / `failed_cases.jsonl`。求解器仍由 `solver.type` 选择。

## 2. 代码规模（本轮新增）

| 文件 | 行数 | 本轮 |
|---|---|---|
| `pipeline/batch.py` | 约 430 | 新（唯一新增的生产模块） |
| `pipeline/run_case.py` | 约 300 | +100：RUNNING 恢复、config 快照、stage 秒数、keep_odb、deck SHA 链 |
| `pipeline/mesh.py` | 约 420 | +6：`load_case(document=)`、`run_mesh(case_document=)` |
| `pipeline/abaqus.py` | 约 845 | +8：`runtime.results.keep_odb` |
| `pipeline/extract.py` | 约 195 | 小改：允许重跑 extract |
| `run.py` | 约 265 | +55：`run-batch` / `summarize-batch` |
| `tests/test_batch.py` | 约 390 | 新，23 个测试 |
| `tests/test_run_case.py` | 约 330 | +11 个测试（恢复/快照/keep_odb/内容 SHA） |
| config | — | 新 `config/case_defaults.json`、`config/cases.jsonl`、`config/examples/simulation_explicit_smoke.json` |

生产代码本轮净增约 **+600 行**（batch.py 是主体），没有引入 scheduler/worker/registry/queue/database。
核心业务模块 8 个：`common, mesh, build, abaqus, extract, run_case, batch, curve_qa`。

## 3. 真实 Abaqus 验证（2026-09-17）

| 项目 | 结果 |
|---|---|
| Fig.1 Standard deck 与 fixture | **10/10 SHA 一致**（`run-case` 目录里重建也一致） |
| Fig.1 mesh data check + vendor stage 07 | PASS |
| Fig.1 Standard / Standard+self_contact=false / Explicit Data Check | 0 error（warning 数与历史同类） |
| Explicit smoke solve + extract | 真跑完，101 点曲线 |
| 历史 Standard ODB 重新提取 | 60 点曲线与旧脚本逐点一致 |
| **真实小批量 batch**（4 case, workers=1, smoke sim） | fig1 DONE 177.9s / diverse_02 DONE 261.6s / diverse_01 MESH_STAGE_FAILED / broken_expr MESH_STAGE_FAILED；失败不影响其他 case |
| batch 复跑 | `to run: 0`（DONE skip、FAILED 默认 skip）；`--retry-failed` 只重跑失败 case |
| 残留 RUNNING 恢复 | 强制改 RUNNING 后复跑 → settle 成 DONE（`recovered_from: INTERRUPTED`）且不重算 |
| `summarize-batch` | 从各 case 目录重建 3 个汇总文件 |
| `run-case` 复用 batch 的 `case_used.json` | 全部 skip（case 身份按内容 SHA 判断） |

**未验证**：Standard 20% 完整 solve、Explicit 20% 完整 solve、科学质量验收、
`workers>1` 的真实并发、2 万 case 的实际规模。

## 4. 本轮实测发现的真实问题（已修）

1. **残留 RUNNING**：`run_case` 现在把"上次已死的 RUNNING"分两类处理（结果齐全→DONE，
   否则 INTERRUPTED 续跑）；batch 还会把前者 settle 成 DONE 写回 status.json。
2. **case 身份以前按文件字节算**：同一 case 通过 `cases.jsonl`（内存文档）和
   `case_used.json`（文件）会得到不同 SHA，导致无谓重跑。现在 `case_config_sha256` /
   `simulation_config_sha256` 都是**配置内容**的 digest。
3. **stage 报告串链**：datacheck/solve 的"已完成"判定现在要求 deck SHA 与上游报告一致，
   旧 deck 的报告不会误判为完成。
4. **失败信息破坏 CSV**：`batch_summary.csv` 的 message 现在压成单行、截断 300 字符，
   完整内容留在 case 的 `status.json`。
5. **中断的 mesh engine**：重新跑 mesh 前把半成品 `engine` 改名保留（否则 vendor 拒绝启动）。
6. **extract 重跑**：`raw_history.json` 允许在同一 case 目录内覆盖（同一 case 的中间产物）。
   2026-09-18 起在代码中真正落实：`extract()` 调用 worker 前删除旧的 `raw_history.json`
   （worker 拒绝已存在的 `--out`），有回归测试锁定（见第 8 节第 1 条）。

## 5. 已知的科研事实（不要在报告里说成 pipeline bug）

- 冻结 vendor 阶段 05 会拒绝一部分曲面（例：`diverse_01`，Z 面 PBC 配对非双射）。
  历史 attempt `nb30_ref30_01_mesh` 对同一曲面也是 `STEP 05 STATUS: FAIL`，不是本轮引入。
  batch 会把它们记为 `MESH_STAGE_FAILED` 并继续。
- Explicit smoke（`time_period_s=1e-3`）的 `max_ke_ie_ratio` ≈ 1.1–1.3，**不是准静态**，
  只用于验证链路。

## 6. 待办（下一轮，若还有）

- 用真实 `workers=2` 跑一次小批量（确认 license/内存/IO 表现）。
- 批量级科学验收（接触/PBC/能量筛选）——现在只记录诊断值，不判定。
- 2 万级规模的实际验证（NTFS 目录数量、磁盘容量、ODB 保留策略）。
- ref30 实验 T=0.01 组续跑（用户暂停中，见第 9 节；ref30_02 从 solve 续起即可）。

## 7. 不要做的事

不要重新引入 IdentityV2、staging planner、artifact role 框架、schema 迁移层、failure taxonomy、
plugin/backend 体系、DAG engine、数据库、worker daemon；不要在 retry 里改科学参数；
不要用 `taskkill /IM standard.exe` 之类的方式清理 Abaqus（并发时会误杀其他 case）。

## 8. 2026-09-18 轮：第三方审查修复（第 4 轮）

来源：用户委托的第三方只读审查（GitHub 公开版），经本地逐条复核确认后施工。

1. **extract 重跑必失败的缺陷**：`extract()` 现在在调用 Abaqus worker 前删除旧的
   `raw_history.json`（worker 拒绝已存在的 `--out` 路径）。手动 `pixi run cli extract`
   重跑、extract 中断后续跑、batch `--retry-failed` 补跑都不再撞守卫。
2. **curve QA 闭环**：`history.csv` 列名改为 canonical `u3_mm` / `rf3_N`（原 `U3_mm`/`RF3_N`
   与 `curve_qa` 不匹配，`HISTORY_MISSING`）；`curve_qa` 的 11 点 TARGETS 改为 policy 必填
   `strain_targets`（`config/quality.example.json` 保留论文 11 点为示例；20% 曲线对它按设计
   报 `TARGET_RANGE_NOT_REACHED`）；`run-case` 在 extract 阶段按 `runtime.results.curve_qa_policy`
   运行 QA 并写 `results/curve_qa.json`（**默认关闭**；只记录判定，不是门槛；resume 时按当前
   policy 重算，不触发任何 stage 重跑）。QA 输出键：`strain_targets` / `stress_at_targets_MPa`。
3. **extract 阶段补 deck SHA 链**：`summary.json` 记录 `deck_root_sha256`，
   `_stage_done("extract")` 与 build_report 比对（与 datacheck/solve 同一语义）。
4. **`*Energy Output` / `*Node Output` 频率继承文档化**：`pipeline/build.py::render_outputs`
   docstring 明确继承 `history_frequency`（Standard）/ `history_time_interval_s`（Explicit）、
   调整请求顺序会改变采样频率、RB-023 的重复 key 仍会产生。**未改任何渲染字节**，
   deck 回归 fixture 仍 10/10 一致（显式频率须先真实 Data Check 验证，见 RB-023）。
5. **文档治理**：7 个 SUPERSEDED docs 的乱码横幅（63 个字面 `?`）修复；README 两份重复
   「真实验证状态」章节合并（事故记录保留）、测试数改为"命令 + 证据目录"表述；
   `docs/REVIEW_BACKLOG.md` re-reconciliation：RB-008/011/021/024/025/027/028/030 →
   RESOLVED，RB-023 标注**仍活跃**（worker 的 plain-key 启发式已文档化但不等于消歧 policy），
   RB-019 增加新流水线复现线索，30 条 Related Files 全部重写为现行模块名。

验证：`pixi run test` → **core 165 OK + boundary 5 OK**（证据 `work/pixi_tests_hnxdxmd3`）；
`qa-history` 冒烟：论文 policy 对 20% 曲线 `CURVE_QA_FAILED / TARGET_RANGE_NOT_REACHED`（按设计），
匹配目标的 policy `CURVE_QA_PASS` 并输出 `stress_at_targets_MPa`。
**未做真实 Abaqus 复验**（也无需）：本轮未改任何 deck 字节与 Abaqus 调用路径；
列名变更只影响 results CSV，历史 `work/` 结果保持只读不动。

## 9. 2026-09-18 计算实验：ref30_02–05 implicit（8CPU/all）与 explicit（8CPU, T=0.006/0.01）

用户授权的纯计算实验（不动代码）；配置/驱动/小结在 `experiments/ref30_2to5_20260918/`，
逐例证据在 `work/exp_ref30_2to5_20260918/<组>/<case>/`，完整记录见 `docs/WORK_LOG.md` 条目 002。

- **implicit 4 例**：datacheck 4/4 通过（**8CPU + standard_parallel=all 未复现 RB-012 的
  threads-per-domain 错误**）；solve 与历史同位失败——ref30_02 停滞 0.312、ref30_04 停滞
  0.532（均 1500s 上限 TIMEOUT）、ref30_03 快速 SOLVE_FAILED（364.5s）；**ref30_05 分析实际
  跑完**（~27–28 min，超出当时墙钟被记 TIMEOUT，`.sta` 完成标记 + ODB 完整），恢复提取：
  final_strain 0.20000 / max_stress 0.2562 MPa / 78 点 / **KE/IE 0.53%（满足 <1% 准静态）**，
  存于 `implicit/ref30_05_recovered_from_timeout/results/`。
- **explicit T=0.006 4 例全部 DONE**：final_strain ≈0.200、101 点曲线，solve 7.2–19.4 min；
  **KE/IE ≈ 0.93–1.02，不满足准静态**（真实动力响应，不能当准静态曲线解释）。
- **explicit T=0.01**：用户暂停中。ref30_02 解到 ~83% step time 停止（实测比 T=0.006 慢约
  1.4×，推算全程 ~17 min，可在 30 min 内完成）；ref30_03–05 未启动。续跑即重跑 driver，
  RUNNING 会被当作"上次进程已死"从 solve 续起。
- 流程实证：implicit 墙钟超时杀 launcher 后 **orphan standard.exe 存活**（占 8 线程 +
  license，已按 PID 手工清理）——RB-014 的 kill-tree 缺口在真实实验中复现。
- 时间线、逐例数字与偏差处置（solve 上限 1500s→1800s）详见 WORK_LOG 条目 002。
