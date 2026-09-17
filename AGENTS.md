# auto_abaqus 工作区规则

## 项目性质

这是一个**科研自用脚本**，不是一个软件产品、框架或平台。目标只有一条流水线：

```
曲面 → 自动网格 → Abaqus 建模 → Data Check → Solve → 结果提取 → 批量运行
```

因此：

- **简单优先于抽象**。100 行直接代码能清楚完成的事，不要写成一个框架。
- **不写产品级兼容层**：不维护 schema v1/v2 双轨、不为旧报告写迁移器、不做未知字段分类框架。
  格式变了就手工迁移一次。
- **不做防御性架构**：没有第二个用户、没有下一个运行时、没有未知调用方。校验只保留
  "明显非法值必须报错"这一层。
- 新增抽象前先自问：它对"自动网格 + Abaqus 计算"有没有直接作用？没有就删。
- 核心业务代码保持 5～8 个模块；净删除优先于净新增。

## 常用命令（在工作区根运行）

- `pixi run test` / `pixi run check` / `pixi run plan` / `pixi run cli-help`
- `pixi run cli run-case --case config/cases/<case>.json --simulation config/simulation.json`
  （整个单 case，可续跑；`--force` 重跑全部）
- `pixi run cli run-batch --cases config/cases.jsonl --case-defaults config/case_defaults.json
  --simulation config/simulation.json [--work-root work/batch_001] [--workers 1]
  [--retry-failed] [--max-retries 0] [--force]`（批量；本质是逐个调用 `run_case()`）
- `pixi run cli summarize-batch --work-root work/batch_001`（从各 case 目录重建总表）
- 单 stage 调试：`pixi run cli mesh | mesh-datacheck | build | datacheck | solve | extract
  --case config/cases/<case>.json [--simulation config/simulation.json]`
- 低层 vendor 调试：`pixi run mesh-env|mesh-pre|mesh-post|mesh-check`、`pixi run build-cgal`

## 单 case 布局与求解器选择

- 一个 case 一个目录：`work/<case_id>/{mesh,abaqus,results,status.json,run.log}`；
  Data Check 与 Solve 就在 `abaqus/` 里跑，**不做 staging、不复制 deck**。
- 被替换的 stage 目录改名为 `*.previous_<时间戳>` 保留证据，不删除。
- 续跑依据 `status.json` 里的 stage 状态 + 两个 config **内容** SHA256（case 配置变 → 全部重跑；
  simulation 变 → build 起重跑）。残留 `RUNNING` 一律当作"上次进程已死"：结果齐全就是 DONE，
  否则从缺的 stage 继续；不查 PID、不做 heartbeat。
- 求解器由 `simulation.json` 的 `solver.type` 选择（`standard_dynamic_implicit` /
  `explicit_dynamic`），两个参数 block 各自独立；renderer 用直接的
  `if solver == ... elif ... else raise`，不建 backend/plugin/interface 层。

## 批量（batch）

- Batch 只做三件事：读 `cases.jsonl` + `case_defaults.json`（一层合并）、选哪些 case 要跑、
  把每个 case 的 `status.json`/`summary.json` 汇总成 `batch_summary.csv` / `results_index.jsonl`
  / `failed_cases.jsonl`。**不重写 stage、不认识 solver、不建数据库**。
- 一个 worker 跑完一个 case 的完整流程；默认 `workers=1`，由用户自己提高，永不按核数自动并发。
- 共享的 batch 文件只由主进程写；worker 把结果交回主进程。
- 单个 case 失败只记录并继续；只有全局错误（输入文件、重复 case_id、defaults 非法、launcher 不可用）
  才停止 batch。
- retry 必须用**完全相同**的输入，只补跑失败的 stage。

## 硬约束

- **冻结 `vendor/periodic_surface_mesher_v1.0`**：不修改、不重写网格算法。第一方代码只做
  配置转换、契约校验、PBC 生成和"调用 vendor + CGAL"。
- **历史结果只读**：`reference/`、`baseline_test/`、已有 `work/` attempt 永不覆盖、永不修改。
  新结果一律用新的唯一 `work/<attempt>` 目录；失败也保留证据。
- **科学参数不得在自动重试中偷偷改变**：材料、接触、厚度、加载、网格等参数一旦确定，
  retry 必须用同一套输入；发现不一致要显式报错。
- **Abaqus 是外部独立运行时**：不使用 Pixi 的 Python/DLL 环境启动它；ODB 只由兼容的
  `abaqus python` 只读打开。不自动启动长时间 solve —— solve 只在用户显式调用时运行，
  且 `run-case` 会跑 solve，长算例前要先确认。
- **不 push**（除非用户明确要求）；不添加远程、不上传本机配置或计算结果。
- 依赖只通过 `pixi.toml` + `pixi.lock` 管理；`default`(py3.11) 跑主控/测试，`geo`(py3.10.21)
  跑冻结网格，`cgal` 管构建。不使用 Anaconda Python / conda 命令。
- 不在代码里写死科研变量：element type、E/ν、密度、plastic 表、相对密度、摩擦、slip tolerance、
  压缩应变、step 时间/增量、输出频率、mass scaling、CPU、超时都应来自 config。
  内部名字（NSET/ELSET/RP 名、block 文件名、step 名）保持代码常量。
- **不猜 Abaqus 语法**：新关键字先用真实 Data Check 验证再写进 renderer
  （例：`*Contact Exclusions` 空数据行会被 2026 版拒绝；Explicit 的完成标记与 Standard 不同）。

## 记录方式

- 分开记录"代码已实现""逻辑测试通过""真实 Abaqus 验证通过"。Data Check 通过 ≠ 收敛 ≠
  达到目标应变 ≠ 科学质量合格。
- 不确定或未验证的结论标注为待复核，不生成虚假 PASS。
- 文档只需维护 `README.md`、`AGENTS.md`、`docs/HANDOFF_CURRENT.md`；其余 docs 标记为
  SUPERSEDED/LEGACY 后不再同步。

## 语言

面向人的说明默认中文；技术名称、代码、配置键、状态枚举保持英文。
