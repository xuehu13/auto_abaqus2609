# 本机环境检查

> **PUBLIC NOTE**: The paths, drive letters, hardware specifications and
> software versions below describe the ORIGINAL DEVELOPMENT WORKSTATION at
> the time of the check. They are recorded as engineering evidence and are
> NOT a required directory layout for other users; configure your own paths
> in `config/*.local.json` instead.
>
> LEGACY NOTICE（2026-09-14 加注）：本文写于 Conda→Pixi 迁移之前。第 3、8 节中的 `F:\Anaconda` 解释器命令已停用，仅为当时实测记录；当前唯一活动入口是工作区根的 `pixi run <task>`（见根目录 README 的 Pixi quick-start）。正文内容保持原样未改动。
>
> [SUPERSEDED 范围补充 2026-09-16]：除第 3、8 节外，**第 1 节的代码根目录行**（历史双层 `DiffuMeta_Automation_v0.1\DiffuMeta_Automation_v0.1\`，已于 2026-09-14 移除）与**第 5 节的 Conda PATH 调用**同样只用于历史复现。当前代码根 = 仓库根 `F:\auto_abaqus`；当前唯一入口是 `pixi run <task>`。正文依然保持原样未改动。

检查日期：2026-09-13（Asia/Shanghai）。这是本机实测记录，原 `VERIFICATION.md` 记载的 2026-09-12 Linux 测试仍保留为历史记录。

结论：普通 Python 基础开发、真实网格读取、CGAL 程序启动、Abaqus 2026 启动及只读 ODB 提取可用。本次没有提交新 Data Check、完整求解或批次；不能据此宣称求解器生产运行和并发资源已验收。

## 1. 实际目录

| 用途 | 已查证路径 |
|---|---|
| VS Code 工作区 / 本地 Git 根目录 | `F:\auto_abaqus` |
| 代码根目录 | `F:\auto_abaqus\DiffuMeta_Automation_v0.1\DiffuMeta_Automation_v0.1` **[SUPERSEDED：该双层目录已于 2026-09-14 移除；当前代码根 = 仓库根 `F:\auto_abaqus`]** |
| 工作区参考资料 | `F:\auto_abaqus\reference` |
| 工作区已有网格基准 | `F:\auto_abaqus\baseline_test`，不是 `baseline` |
| 外部已验证网格工程 | `F:\DiffuMeta_Abaqus\periodic_surface_mesher_clean` |
| 外部手工 CAE/JNL | `F:\DiffuMeta_Abaqus\DiffuMeta_onecell0912.cae/.jnl` |
| 外部手工作业文件 | `E:\ABAQUS\2026temp\Abaqus_Work\Fig1_Compression.*` |
| 本次检查产物 | 代码根目录下 `work/takeover_20260913_01/` |

没有移动或修改上述旧工程、原始资料和 baseline。当前手工作业的 INP/ODB/dat/msg/sta/log 已复制到 `work/takeover_20260913_01/physical_snapshot/`，避免后续同名旧作业更新后失去本次证据。此目录不进 Git。

## 2. Windows 和硬件

| 项目 | 实测 |
|---|---|
| 系统 | Windows 11 家庭版中文版，64 位，10.0.26200 / Build 26200 |
| 逻辑处理器 | 20；不能等同于可并发运行 20 个 Abaqus 作业 |
| 物理内存 | 33,960,349,696 bytes，约 31.63 GiB |
| F 盘剩余空间 | 检查时约 350.0 GB（326.0 GiB） |
| E 盘剩余空间 | 检查时约 74.7 GB（69.6 GiB） |
| Git | 2.51.0.windows.1；`F:\Git\Git\cmd\git.exe` |

容量是时点值，未来调度必须重新检查。论文硬件的 96 GB 内存不是本机内存；论文 Table S6 耗时也不是本机性能保证。尚未做求解并发、内存峰值、许可证容量或长期磁盘增长测试。

## 3. 普通 Python / Conda

> [SUPERSEDED] 本节为 Conda→Pixi 迁移前的实测记录；其中的 `F:\Anaconda` 解释器与 `python` 绝对路径调用均已停用，仅用于历史复现。当前依赖真值是 `pixi.toml + pixi.lock`，入口为 `pixi run <task>`。

Conda 24.11.3 位于 `F:\Anaconda`。当前终端直接写 `python` 默认找到 `F:\Anaconda\python.exe`（Python 3.12.7），并不自动等于几何环境。因此开发命令优先写解释器绝对路径。

| 组件 | `F:\Anaconda\envs\diffumeta_geo\python.exe` 实测版本 |
|---|---|
| Python | 3.10.21，64 位 |
| NumPy | 2.2.6 |
| SciPy | 1.15.3 |
| scikit-image | 0.25.2 |
| SymPy | 1.14.0 |
| SQLite | 3.53.2 |

这些依赖成功导入，NumPy 满足当前 `requirements.txt` 的 `>=1.24,<3`。旧网格 `environment_geo.yml` 写 NumPy 1.26，但 `REFERENCE_RESULTS.md` 的实测版本就是 2.2.6；本次与后者一致，没有降级或重建环境。

已确认存在 `diffumeta_geo`、`diffumeta_cgal` 等 Conda 环境；没有修改任何现有环境。Conda 首次只读查询因沙箱的进程通信权限失败，批准重试后获得环境清单。这不是 Conda 环境损坏。

## 4. Abaqus 与独立 Python

真实启动命令：

```powershell
& 'E:\ABAQUS\2026\Commands\abaqus.bat' information=release
```

实测退出码 0，输出 Abaqus 2026，build `2025_09_23-22.43.03 RELr428 206049`。该 bat 转发至同目录 `abq2026.bat`，再调用安装内的 `SMALauncher.exe`。

| 项目 | 实测 |
|---|---|
| Abaqus Python 可执行程序 | `E:\ABAQUS\2026\EstProducts\win_b64\code\bin\SMAPython.exe` |
| Python | 3.10.5，64 位 |
| 自带 NumPy | 1.22.4 |
| `odbAccess` | 由 Abaqus Python 成功导入 |
| 真实 ODB | 成功只读打开工作区 meshcheck ODB 和外部 Fig1_Compression ODB |
| 现有 `abaqus_worker/export_history.py` | 真实 ODB 的 region 清单、指定 history 导出均成功；原始时间轴保留 |

Abaqus 自带 NumPy 1.22.4 不满足普通主控 requirements，是正常的两层运行环境差异，不应升级 Abaqus 内的 NumPy。普通 Python 负责 JSON/CSV/NPZ，Abaqus Python 负责 ODB，中间以文件交换。

当前环境检查只证明命令和只读提取可调用；既有日志显示 2026-09-12 曾正常运行求解，但本次未验证“今天新作业能否获得求解许可证”。没有启动 CAE GUI 或新 solver。

接管临时 ODB 探针开发时发现：脚本发生 SyntaxError/JSON 类型错误时，Abaqus bat 仍可能返回 0。临时探针修正后已读出真实数据。后续执行器必须同时验证预期输出、结构化成功报告和日志，不能只看退出码；这不是现有 history worker 的测试失败。

## 5. CGAL

> [SUPERSEDED] 本节中的 `F:\Anaconda\envs\diffumeta_cgal\Library\bin` PATH 调用与 Conda 包元数据是迁移前记录，仅用于历史复现；当前 CGAL 由 Pixi `cgal` 环境提供（`pixi run build-cgal`）。

实际程序：

```text
F:\DiffuMeta_Abaqus\periodic_surface_mesher_clean\cgal_mesher\build\periodic_surface_mesher.exe
```

在子进程环境的 PATH 前添加 `F:\Anaconda\envs\diffumeta_cgal\Library\bin` 后，无参数调用成功进入程序并打印 Usage；退出码 1 与源码 `argc < 4` 的用法分支一致。这是“可加载、可执行”检查，没有运行网格生成。没有改系统或终端全局 PATH。

实测 CLI：

```text
periodic_surface_mesher.exe <cgal_case.txt> <feature_file> <output_prefix> [facet_size_override_mm]
```

Conda 元数据：`cgal-cpp 6.0.1 hc4f255e_1`。已有 CMakeCache 显示 Release / Ninja / MSVC，CGAL_DIR 指向此 Conda 环境。外部 clean 工程所有 Python/C++/hpp 源文件与 vendor 对应文件一致；exe 已记录 SHA256，但本次未重新编译，不能用源文件相同代替二进制构建可追溯性证明。后续真实网格回归仍需登记 exe、DLL 环境与输出指纹。

`config/environment.example.json` 的 CGAL 和 Abaqus 路径在本机不能直接沿用。本次另建被 Git 忽略的 `config/environment.local.json`，只登记查证路径与检查范围，不修改示例文件，也不把环境标成生产已验收。

## 6. 已执行检查及真实结果

| 检查 | 结果 | 限制 |
|---|---|---|
| 原有 unittest 14 项 | 获得权限后原样重跑，14/14 OK，0.245 s，退出码 0 | 逻辑测试，非求解验证 |
| 首次沙箱测试 | 11 项 OK，3 项临时目录/SQLite 访问错误 | 不隐去首次失败；批准重跑后无逻辑失败 |
| `run.py plan` / `--help` | 退出码 0，确无 solve/batch 入口 | plan 中阶段是设计，不是实际运行 |
| pipeline/worker/tests/run.py AST 语法检查 | PASS | 不等同于功能完整 |
| 真实 shell NPZ/report/CSV → prepare-fe | 成功生成独立输入片段和 manifest | `FE_INPUTS_PREPARED_ONLY`，无完整 physical.inp |
| vendor 与原 zip | 32 个文件全部逐字节相同 | 没有修改网格算法 |
| 私有网格副本 Step00 | 表达式/梯度有限，`PYTHON ENVIRONMENT STATUS: PASS` | 只做环境检查，没有运行01–07或CGAL划分 |
| Abaqus release / ODB 读取 | 成功 | 未提交新 Data Check/求解 |
| CGAL 无参数启动 | Usage，预期退出 1 | 未重新生成网格 |

测试日志及 JSON 在 `work/takeover_20260913_01/`；长期结论与文件指纹另记 `LOCAL_EVIDENCE.json` 和 `PROJECT_STATUS.md`。PowerShell 把 unittest 写到 stderr 的正常文字显示为 `NativeCommandError` 的包装行；真正判定依据为 unittest `OK` 和 Python 退出码 0。

## 7. PDF 阅读工具

已使用本机 Git 附带 `F:\Git\Git\mingw64\bin\pdftotext.exe` 提取文字。其公式字符有缺损，因此又在经批准的项目目录 `work/takeover_20260913_01/pdf_tools/` 安装 PyMuPDF 1.28.2，仅通过检查脚本临时加入 `sys.path` 使用；没有改现有 Conda 环境。首次沙箱安装失败，批准联网重试后成功。

已提取 5 份 PDF 的逐页文本，并渲染关键页检查公式、表格和历史截图。具体阅读范围见 PROJECT_STATUS；提取完整文本不等于人工逐页精读全部截图。缺少全系统 Poppler 渲染命令不再阻碍本次核查。

## 8. 用户可以怎样复查

> [SUPERSEDED] 下面的命令使用**已删除的历史双层代码目录**与 `F:\Anaconda` 解释器，**当前不可执行**，保留仅作历史复现。当前等价命令（在仓库根执行）：`pixi run plan`、`pixi run test`、`pixi run cli-help`。

打开 VS Code 的“终端 → 新建终端”，使用 PowerShell，依次执行：

```powershell
Set-Location 'F:\auto_abaqus\DiffuMeta_Automation_v0.1\DiffuMeta_Automation_v0.1'
& 'F:\Anaconda\envs\diffumeta_geo\python.exe' run.py plan
& 'F:\Anaconda\envs\diffumeta_geo\python.exe' -m unittest discover -s tests -v
```

第一条切换到真正的代码目录；第二条只显示已实现/待实现功能；第三条只运行基础测试。前面的 `&` 是 PowerShell 的程序调用符。看到 `Ran 14 tests ... OK` 才是测试通过，不是 Abaqus 算完。

查看本地版本状态：

```powershell
git -C F:\auto_abaqus status --short --branch
git -C F:\auto_abaqus log -1 --oneline
```

本地 Git 不等于云备份。被忽略的原始资料、基准和 ODB 仍需另外备份；本次没有上传任何远程仓库。

本次采用工作区根 `.gitattributes` 保留文件原始字节，避免 Windows checkout 自动换行转换破坏 vendor/包清单校验值。未修改全局 Git 配置。
