# DiffuMeta Automation

Abaqus 周期性多孔表面网格自动化与压缩仿真数据流水线：把冻结的 `periodic_surface_mesher v1.0` 网格模块和手工 Abaqus 物理模型接成可管理的批量系统。当前 v0.1 提供隔离网格准备、FE 输入片段、曲线 QA 与状态账本基础；完整物理 INP writer、调度与恢复尚未实现（见 `docs/IMPLEMENTATION_STATUS.md` 与 `docs/PROJECT_STATUS.md`）。

## 环境：Pixi 是唯一普通环境管理器

依赖只通过根目录 `pixi.toml + pixi.lock` 管理，包含 `default`（主控/测试）、`geo`（validated 网格 Python）、`cgal`（构建/运行依赖）三个环境。不使用 Anaconda、`conda activate` 或系统裸 Python 作为项目入口；`pip install -r` 已废弃（旧文件见 `docs/legacy/requirements_v0.1.txt`）。

Abaqus 始终是外部 vendor runtime：Abaqus Python、odbAccess 与求解器不属于 Pixi 环境，也不得混用两边 NumPy/PYTHONPATH/DLL。本机 launcher 只登记在被 Git 忽略的 `config/environment.local.json`（模板见 `config/environment.example.json`）。

## Quick start

```powershell
pixi install          # 重建三环境（换机复现入口）
pixi run check        # 三环境自检；不跑网格、不提交 Abaqus
pixi run test         # 运行当前自动化测试套件
pixi run cli --help   # 全部现有 CLI 命令
pixi run cli prepare-mesher --case config/cases/fig1.json --out work/<新attempt>
pixi run mesh-pre / mesh-post / mesh-check --out work/<新attempt> [--from-attempt ...]
pixi run build-cgal --check-only        # 编译工具链检查；实际构建需 --out
```

每次输出必须使用新的 `work/<attempt>` 目录，拒绝覆盖。

当前 `build-physical` 生成 partial 物理 blocks：`blocks/material_section.inc`、`blocks/rigid_platens.inc`、`blocks/boundary_conditions.inc`、`blocks/contact.inc` 与 `model_manifest.json`。仍不生成完整 `physical.inp`，也没有 Abaqus Physical Data Check，不是 production-ready。

## 目录结构

| 位置 | 职责 | Git |
|---|---|---|
| `run.py`、`pipeline/`、`abaqus_worker/`、`config/`、`tests/` | 活动源码 | tracked |
| `scripts/` | Pixi 任务包装与迁移边界测试 | tracked |
| `vendor/periodic_surface_mesher_v1.0/` | **FROZEN** 已验证网格算法（Python 00–07、CGAL C++、meshlib），禁止修改 | tracked |
| `docs/` | 设计、实施状态与历史证据 | tracked |
| `docs/legacy/` | v0.1 原始交付 artifacts（`PACKAGE_SHA256_v0.1.json`、`requirements_v0.1.txt`），仅描述旧交付包的包内相对路径，不被任何活动代码引用 | tracked |
| `pixi.toml`、`pixi.lock` | 依赖与任务唯一真值 | tracked |
| `AGENTS.md` | AI/贡献者强规则 | tracked |
| `reference/`、`baseline_test/` | 本地参考资料与验证基线（含大文件），不随仓库分发 | local-only，ignored |
| `work/`、`.pixi/`、`.vscode/` | 运行输出 / 环境缓存 / 编辑器配置 | generated / ignored |

CGAL 编译产物通过 `--cgal-build <work attempt 目录>` 显式选择，并用 SHA256 与 `pixi.lock` 哈希双重绑定，绝不回退到外部旧 exe。

## 以下为历史 v0.1 交付说明

以下旧环境激活命令、裸 Python 命令、外部旧 exe 建议及旧配置字段均已停用，仅保留交付上下文。不得作为当前 quick-start；正文中的文件格式说明可供参考。

这是可继续开发的**设计骨架与基础工具**。目标是把已有网格模块和手工 Abaqus 物理模型接成可管理的批量系统。当前不会提交真实 Abaqus 求解，也不会生成可直接求解的完整 `physical.inp`。

先读 [完整架构与实施方案](docs/Abaqus_Automation_Design_v1.0.md)。

## 1. 这次交付包含什么

- 上传的 Periodic Surface Mesher v1.0 原样放在 `vendor/`，没有修改网格算法。
- 可以建立隔离的网格工作副本和准确的命令计划。
- 可以读取真实 shell.npz/report/pairs，生成壳网格 include、独立 PBC include 和模型输入清单。
- 提供 SQLite 状态账本、停滞/日志判断、曲线与能量检查的基础模块。
- 提供 Abaqus Python 的只读 history 导出候选脚本。
- 包含 14 项关键逻辑测试；合成数据仅用于测试，不是 Fig.1 仿真结果。

未实现的完整 writer、Windows launcher/watchdog、自动恢复、完整 ODB QA 和数据集导出，详见 [实施状态](docs/IMPLEMENTATION_STATUS.md)。

## 2. 放在哪里

例如解压为：

```text
E:\Git\DiffuMeta_Automation
```

这只是代码位置；大计算结果可以放 `F:\DiffuMeta_Runs`。不要求移动你已有的网格工程。打包的 vendor 没有 exe 和真实 Fig.1 网格，继续使用你本地已经验证的 exe 与网格产物即可。

VS Code 打开该文件夹，进入已有 `diffumeta_geo` 环境。基础工具要求 Python 3.10+ 与 NumPy，不要求安装其他新软件。

```powershell
conda activate diffumeta_geo
python run.py plan
```

此命令只显示整体流程与实现状态。

## 3. 准备一个独立网格任务

复制 `config/environment.example.json` 为本机配置文件，核对里面的三个实际路径。它们是示例值，不是自动探测结果。暂时只看程序逻辑时不必改路径，因为下面命令不执行 Abaqus/CGAL。

```powershell
python run.py prepare-mesher --case config/cases/fig1.json --out work/fig1_mesh_001
```

如果已写好本机配置：

```powershell
python run.py prepare-mesher --case config/cases/fig1.json --environment config/environment.local.json --out work/fig1_mesh_002
```

输出有私有 `engine/` 和 `mesh_plan.json`。后者逐条写明要调用哪个解释器/程序、参数、工作目录及阶段通过条件。这不是“网格已生成”的报告。

再次使用同一 `--out` 会明确拒绝覆盖。换任务或重试使用新目录，原目录的文件保留。

## 4. 用本地真实网格准备 FE 输入

你需要现有网格程序生成的三个文件。把以下示例路径改成真实位置：

```powershell
python run.py prepare-fe --npz F:/your_case/shell/fig1_shell.npz --report F:/your_case/shell/fig1_shell_report.json --pairs F:/your_case/abaqus_meshcheck/fig1_periodic_pairs.csv --out work/fig1_fe_001
```

输出：

| 文件 | 用途 |
|---|---|
| `shell_mesh.inc` | 壳节点、S3R 连通，已完成 0-based 到 1-based 转换 |
| `lateral_pbc.inc` | 代表节点形式的 X/Y 周期方程 |
| `pbc_map.json` | 等价类和整数周期偏移，供审核与后处理 |
| `model_inputs.json` | 逐案厚度、面积、标签、物理配置、来源 hash 和未完成项 |

这些还缺少刚板、材料/截面、接触、分析步、载荷和输出的完整关键词装配，**不能把其中任意 include 当作完整 Abaqus 模型提交**。

默认材料是交接记录中的 surrogate，仅用于接口示例。它未被标成实验材料或生产材料。

## 5. 检查已经导出的对齐 history CSV

CSV 列必须为：

```text
time_s,u3_mm,rf3_N,ALLKE,ALLIE,ALLAE
```

如果各原始 history 的时间轴不同，应先按方案对齐，不能直接按行拼接。输入需要保留整个压缩过程，而不只是 11 个点。

```powershell
python run.py qa-history --csv F:/your_case/aligned_history.csv --height-mm 10 --area-mm2 100 --reaction-sign -1 --out work/fig1_curve_qa_001.json
```

`--reaction-sign` 必须根据该模型真实 RP 反力符号选择 +1 或 −1；不应为了让负应力消失而逐样本随意更改。

`CURVE_QA_PASS` 仅说明曲线层检查通过，`dataset_eligible` 仍为 false。最终接触/PBC/材料适用性/正常求解结局尚需独立检查。

## 6. 查看和验证基础功能

```powershell
python -m unittest discover -s tests -v
python run.py --help
```

测试不需要 Abaqus，不证明 Abaqus 可收敛。它们验证容易造成批量数据错误的基础逻辑。

当前 `status` 读取 `state.py` 创建的阶段账本：

```powershell
python run.py status --db F:/DiffuMeta_Runs/state.db
```

没有真正调度过任务时不会自动出现该状态库。v0.1 没有伪造任务成功记录。

## 7. Abaqus history worker

`abaqus_worker/export_history.py` 必须由 Abaqus 自带 Python 执行。

首先列出实际 ODB history region：

```powershell
abaqus python abaqus_worker/export_history.py --odb F:/your_case/job.odb --out F:/your_case/regions.json
```

根据该清单建立真实 region_map，再执行提取。格式见脚本文件开头。该脚本保留每个变量各自的时间轴，不擅自猜集合名或补缺变量。后续完整 writer 会自动生成这些映射，正式操作时不再手填。

这个候选脚本在当前环境只做语法验证，须在本机用真实 ODB 验证后才能接入无人值守主链。

## 8. 接下来实际开发什么

先接通完整 physical INP writer，并用真实 Fig.1 在 Abaqus 2026 做 Physical Data Check。随后完成同一个 case 的 30% 求解、ODB 提取、质量检查，再接上全队列的执行与恢复。每一步的明确验收标准已经写入完整方案，避免重复设计。
