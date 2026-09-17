# HANDOFF_CURRENT

本文件是当前状态的**唯一真值摘要**（2026-09-17，第 3 轮：批量运行打通）。
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

## 7. 不要做的事

不要重新引入 IdentityV2、staging planner、artifact role 框架、schema 迁移层、failure taxonomy、
plugin/backend 体系、DAG engine、数据库、worker daemon；不要在 retry 里改科学参数；
不要用 `taskkill /IM standard.exe` 之类的方式清理 Abaqus（并发时会误杀其他 case）。
