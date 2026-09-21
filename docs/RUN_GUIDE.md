# RUN_GUIDE —— 普通使用者运行手册

这是"怎么跑"的手册，不是开发文档。参数含义在 `production.json` 内的注释里都已写清，
本手册只讲结构和最常见操作。

## 最常用工作流

1. 打开 **`config/experiments/production.json`**
2. 修改：材料 / 网格 / 壳厚度 / 接触 / 压缩量 / 求解器（Standard 或 Explicit）/
   step time / CPU / timeout 等
3. 准备 **`cases.jsonl`**（每行一个曲面）：
   `{"case_id": "case_00001", "surface_expression": "2.3*cos(X)*sin(Z)-0.6"}`
4. 执行：
   ```powershell
   pixi run cli run-experiment --config config/experiments/production.json
   ```
5. 查看结果：`work/<experiment_id>/` 目录
   - `<case_id>/results/summary.json` —— 每个 case 的最终数字
   - `<case_id>/results/stress_strain.csv`、`history.csv` —— 曲线
   - `batch_summary.csv`、`failed_cases.jsonl`、`results_index.jsonl` —— 批量总表
   - `production_used.json` —— 本次实际生效的完整配置快照（可复现的证据）
   - `<case_id>/status.json`、`run.log` —— 出错时先看这两个

整个流程自动走：surface → mesh → mesh datacheck → build → physical datacheck →
solve → extract → batch summary。

## production.json 各大类管什么

| 大类 | 管什么 |
|---|---|
| `experiment` | 实验名（= 结果目录名）、cases 文件、workers、重试、force |
| `geometry` | 单胞尺寸 L、曲面等值面水平 |
| `mesh` | 网格采样/间距、CGAL 参数、容差、Mesh Data Check 临时参数 |
| `material` | 密度、弹性模量、泊松比、塑性表 |
| `shell` | 壳单元、积分点、**厚度来源（thickness_mode）** |
| `pbc` | 周期边界是否含转动自由度 |
| `platen` | 刚性压板单元/宽度/网格 |
| `contact` | 法向行为、分离、摩擦、自接触 |
| `loading` | 目标压缩应变、加载幅值曲线 |
| `solver` | 选 Standard 或 Explicit + 两套完整求解参数 |
| `output` | history 输出请求（能量 / 各 RP 的变量） |
| `runtime` | CPU、timeout、launcher、ODB 保留等机器与运行参数 |

`cases.jsonl` 里每行只需要 `case_id` 和 `surface_expression`（可选 `overrides`，
普通使用不需要）。

## 常见修改

### 切换 Standard / Explicit

`"solver"."type"` 改成 `"standard_dynamic_implicit"` 或 `"explicit_dynamic"`。
两套参数块都留在文件里，切换不用删块。Explicit 的 `time_period_s`（T）会影响
计算时长和惯性响应；不能只凭 T 或全程 `max_ke_ie_ratio` 判定准静态，
应检查加载阶段的能量曲线并做 T 收敛实验。

### 改材料

改 `material` 块：密度（tonne/mm³）、弹性模量（MPa）、泊松比、塑性表
（每行 `[真实流动应力 MPa, 等效塑性应变]`，第一行应变为 0）。

### 改壳厚度 / 相对密度（thickness_mode）

- `"thickness_mode": "relative_density"`：厚度 = `target_relative_density × L³ ÷ 曲面面积`
  （历史算法，改 `target_relative_density` 即改厚度）。
- `"thickness_mode": "fixed"`：直接用 `"thickness_mm"` 的数值作为正式壳厚度
  （必须为正数）；此时 `target_relative_density` 不参与厚度计算。
- 两种模式互斥：relative_density 模式下把 `thickness_mm` 设为非 null 会直接报错。
- 实际用到的厚度与来源记录在每个 case 的 `build_report.json`
  （`model.thickness_mm` / `model.thickness_source`）。

### 改网格

`mesh` 块：`boundary_target_spacing_mm`、CGAL 的 `cell_size_mm`/`facet_*` 控制网格粗细；
`tolerances` 一般不动。改完建议先用一两个 case 试跑。

### 改 CPU / timeout

`runtime.datacheck` / `runtime.solve` 的 `cpus`、`timeout_s`（秒，超时会终止该 case 的
整个 Abaqus 进程树并保留证据）。`runtime.abaqus.launcher` 必须是本机 Abaqus launcher
的**绝对路径**（null 会明确报错）；`cgal.executable` 填 null 则自动找
`work/*/build` 下最新的网格器。

## 调试单个 case / 单个 stage

总配置适合整批运行；调试时仍用旧 CLI（高级接口，与总配置并存）：

```powershell
pixi run cli run-case  --case config/cases/fig1.json --simulation config/simulation.json
pixi run cli mesh | mesh-datacheck | build | datacheck | solve | extract  --case ...
pixi run cli plan          # 各 stage 输入输出一览
```

## retry / resume 行为

- 结果按 case 目录判断：已完成（DONE）的 case 重跑时自动跳过。
- 上次失败的 case 默认跳过；`experiment.retry_failed=true` 会用**完全相同的配置**
  只补跑失败 stage；`max_retries` 控制自动重试次数（绝不改科学参数）。
- `force=true` 全部重算（旧结果目录改名保留，不删除）。
- 改了 production.json 里的科学参数后想全部重算：**换一个新的 experiment_id**，
  旧批次连同它的配置快照完整保留。
