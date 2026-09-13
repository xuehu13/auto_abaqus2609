# DiffuMeta 工作区规则

- 用中文沟通，说明操作目的、实际结果和下一步，面向有工程力学背景的 Python/Codex 新用户。
- 代码根目录是 `DiffuMeta_Automation_v0.1/DiffuMeta_Automation_v0.1/`；从这里执行 `run.py` 和测试。工作区顶层是本地 Git 根目录。
- 先读代码根目录的 `docs/PROJECT_STATUS.md`、`docs/LOCAL_ENVIRONMENT.md` 和 `docs/IMPLEMENTATION_PLAN.md`；旧设计/交接是历史证据，不覆盖新查证结果。
- 冻结 `vendor/periodic_surface_mesher_v1.0`。优先在 `pipeline/` 和 `abaqus_worker/` 外层增加接口，不重写网格算法。必要核心修改必须说明原因并做完整回归。
- `reference/`、`baseline_test/`、外部旧工程及既有结果只读。新结果使用唯一的 `work/`、`runs/` attempt 目录，拒绝覆盖；保留输入指纹和失败证据。
- 普通 Python 使用已验证的 `diffumeta_geo`；ODB 仅由兼容的 Abaqus Python 以只读方式打开。不得往普通 Python 安装 odbAccess，不混用两边 NumPy。
- 不改系统 PATH、系统设置或现有 Conda 环境；依赖缺失先说明并采用项目级方案。本机配置和计算结果不得提交 Git，不添加远程或上传。
- 分开记录“代码已实现”“逻辑测试通过”“真实 Abaqus 验证通过”。Data Check、正常作业结束、目标应变达到、科学质量验收分别判定。
- 压缩模式保留 X/Y 周期及自由宏观横向伸缩，不擅加 Z-PBC。材料、接触、厚度、加载等物理参数不得在自动重试中偷偷改变。
- 发现文档、源码、INP、ODB 不一致时列出来源和差异。未知警告或缺失检查进入待复核，不生成虚假 PASS，不外推未达到的 30% 应力。
- 当前接管任务只允许环境检查、已有轻量测试和文档整理，不启动完整求解或批量任务；后续按用户新授权及阶段验收执行。
- 基础测试：在代码根目录运行 `& F:\Anaconda\envs\diffumeta_geo\python.exe -m unittest discover -s tests -v`。权限错误要与代码缺陷分开记录，不为通过检查降低测试要求。
