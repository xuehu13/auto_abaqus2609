# 实验：ref30_02–05 implicit（8CPU/all）与 explicit（8CPU, T=0.006s / 0.01s）

日期：2026-09-18。纯计算实验，不修改任何流水线代码。

**当前状态（2026-09-18 06:45Z）：已暂停。** implicit 4 例与 explicit T=0.006 4 例已完成；
T=0.01 组按用户指示暂停（ref30_02 解到 ~83% 停止，ref30_03–05 未启动）。
小结见 `SUMMARY_20260918_pause.md`，总表见 `experiment_log.csv`。

## 设计

- 对象：30 选择曲面中的第 2–5 号（`ref30_02`…`ref30_05`，与 `references/validation_30_surfaces.md`
  第 2–5 行及当年 night batch 的 `source_equation` 逐字一致；case 其余参数同 `config/cases/fig1.json`，
  即 iso_level 0.0、unit cell 10 mm、同一套 mesh/CGAL 参数）。
- 共 **12 个 run**，顺序执行（同一时刻只有一个 Abaqus 作业）：

| 组 | 数量 | 求解器 | 关键设置 |
|---|---|---|---|
| `implicit` | 4 | standard_dynamic_implicit, T=1.0s, 20% 目标 | cpus=8, standard_parallel=all（datacheck 与 solve 相同） |
| `explicit_T0.006s` | 4 | explicit_dynamic, T=0.006s | cpus=8（explicit 不传 standard_parallel），无质量缩放 |
| `explicit_T0.01s` | 4 | explicit_dynamic, T=0.01s | 同上 |

- explicit 采样沿用 smoke 基线约定：`history_time_interval_s = T/100`（约 101 点曲线），
  `field_number_interval = 10`，`mass_scaling.disabled`；其余物理参数（材料/接触/摩擦/
  20% 目标/smooth_step）与 `config/simulation.json` 完全一致。
- 超时策略：`datacheck.timeout_s=600`、`solve.timeout_s=1800`（= 30 分钟，即"算了 >30min
  就停止"的上限；流水线写正式 `SOLVE_TIMEOUT` 报告）；驱动层再有 2100 s 硬上限兜底
  （按 PID 树杀，绝不用镜像名杀）。失败或超时 → 记录后立即下一个。
  追记（2026-09-18 12:00Z）：implicit 组前 4 例原用 1500s 上限跑完；根据 explicit T=0.006
  实测（solve ≈19.3 min）把显式组与后续补跑的 solve 上限调整为 1800s。

## 运行与结果位置

```powershell
python experiments/ref30_2to5_20260918/run_all.py
```

- 每个 run 一个目录：`work/exp_ref30_2to5_20260918/<组>/<case_id>/`
  （内含 `mesh/ abaqus/ results/ status.json run.log`，与其他 attempt 一样完整保留证据）。
- 总表：`experiments/ref30_2to5_20260918/experiment_log.csv`。

## 已知背景（解读结果时注意）

- 历史上 ref30_02 / ref30_04 的 implicit solve 曾收敛停滞、ref30_03 SOLVE_FAILED（RB-020）；
  本次在 cpus=8 / all 模式下重新检验，30 分钟上限内不成功即按超时处理。
- RB-012：本机 `standard_parallel=all` 曾在 General Contact 预处理报 threads-per-domain
  ERROR（当时靠 `=solver` 绕开）。implicit 组若 datacheck 即失败，属预期中的实验观测点。
- Explicit 短 T 不满足准静态（smoke T=1e-3 时 KE/IE ≈ 1.1–1.3）；T=0.006/0.01 的 KE/IE
  会记录在 `results/summary.json`，只作诊断，不作合格判定。
- 结果claims纪律不变：Data Check 通过 ≠ 收敛 ≠ 达到目标应变；`dataset_eligible` 恒为 false。
