# 实验小结（2026-09-18，暂停于 T=0.01 组）

状态：**implicit 4/4 与 explicit T=0.006 4/4 已完成；T=0.01 组按用户指示暂停**
（ref30_02 解到 ~83% step time 时停止，剩余 3 例未启动）。总表见 `experiment_log.csv`，
逐例证据在 `work/exp_ref30_2to5_20260918/<组>/<case>/`。

## 结果总表

| 组 | case | 结果 | solve 耗时 | 点数 | final_strain | max_stress (MPa) | KE/IE |
|---|---|---|---:|---:|---:|---:|---:|
| implicit (8CPU/all) | ref30_02 | SOLVE_TIMEOUT（停滞于 step time 0.312，同历史 RB-020） | 1500s 上限 | – | – | – | – |
| implicit | ref30_03 | SOLVE_FAILED（364.5s 内自行失败） | 364.5s | – | – | – | – |
| implicit | ref30_04 | SOLVE_TIMEOUT（停滞于 step time 0.532，同历史） | 1500s 上限 | – | – | – | – |
| implicit | ref30_05 | 管道记 SOLVE_TIMEOUT，但 `.sta` 显示**分析实际完成**；曲线已恢复提取¹ | ~1500s+ | 78 | **0.20000** | 0.2562 | **0.0053** |
| explicit T=0.006s (8CPU) | ref30_02 | **DONE** | 1163.0s | 101 | 0.19996 | 0.2666 | 0.992 |
| explicit T=0.006s | ref30_03 | **DONE** | 474.1s | 101 | 0.20001 | 0.1479 | 1.023 |
| explicit T=0.006s | ref30_04 | **DONE** | 430.2s | 101 | 0.19997 | 0.3828 | 0.984 |
| explicit T=0.006s | ref30_05 | **DONE** | 587.1s | 101 | 0.19976 | 0.2547 | 0.925 |
| explicit T=0.01s | ref30_02 | **用户暂停**（solve 至 ~83%，证据保留，status=RUNNING） | ~14min 停止 | – | – | – | – |
| explicit T=0.01s | ref30_03–05 | 未启动 | – | – | – | – | – |

¹ `implicit/ref30_05_recovered_from_timeout/results/`：launcher 在 1500s 被杀后 orphan
standard.exe 继续跑完（`THE ANALYSIS HAS COMPLETED SUCCESSFULLY`），用 extract 的 `--odb`
路径从该 ODB 恢复提取；attempt 目录本身未改动，管道状态仍为 SOLVE_TIMEOUT。

## 解读要点（按 claims 纪律，只陈述事实）

1. **implicit 数据检查全过**：4 例 datacheck 全部 `DATACHECK_COMPLETED_WITH_WARNINGS`
   （8CPU + standard_parallel=all 没有复现 RB-012 的 threads-per-domain 错误）。
2. **implicit solve 与历史高度一致**：ref30_02 停滞在 0.312、ref30_04 停滞在 0.532、
   ref30_03 自行失败——与当年 night batch（RB-020）的失败位置基本相同；说明停滞是
   物理/数值原因，不是旧 runner 的问题。唯一差别：ref30_05 在新管道下其实能跑完
   （当年是 partial），只是超出 25 分钟墙钟（当时上限），实际 ~27–28 min 完成。
3. **explicit T=0.006 全部收敛到 20% 目标**：final_strain 均 ≈0.200，101 点曲线；
   solve 耗时 7.2–19.4 min，case 间差异大（曲面/接触不同）。
4. **explicit 的 KE/IE ≈ 0.93–1.02**：动能与内能同量级，**明显不满足准静态**
   （论文判据 KE/IE<1%）；这些曲线是真实动力响应，不能当作准静态应力-应变曲线使用。
   对照：implicit ref30_05（跑完的那例）KE/IE = 0.53%，满足 <1%。
5. **一个流程副作用**：implicit 1500s 超时会杀 launcher 但 orphan standard.exe 继续
   占 8 线程 + license（ref30_02/ref30_04 两个 orphan 已手工按 PID 清理；RB-014 的
   kill-tree 缺口在真实实验中复现）。

## 未完成 / 待用户决定

- T=0.01 组：ref30_02 已停（83%，如继续会本能跑完，估 ~17 min 总时长）；ref30_03–05 未跑。
  实测 T=0.01 比 T=0.006 慢约 1.4×（非 1.67× 线性外推），4 例预计都能在 30 min 内完成。
- 若要继续：`python experiments/ref30_2to5_20260918/run_all.py` 会从 ref30_02 T=0.01
  重跑（RUNNING 会被当作上次已死、从 solve 续起，mesh/datacheck 复用）。
