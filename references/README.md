# References

本目录是 **curated scientific / validation references**（经过筛选、允许提交到 Git 的对外参考资料）。

用途：

- 说明项目的科学来源（论文与补充材料）
- 解释关键验证 case 来自哪里（30 曲面验证的对象）
- 帮助第一次看到本项目的研究者理解背景

本目录**不是**：

- 当前代码实现的 source of truth
- active implementation plan
- raw evidence archive
- AI task queue

## 按职责判断权威来源

`references/` **不覆盖** source code、`AGENTS.md` 或当前项目状态文档。不同问题应按职责查不同来源：

| 问题类型 | 权威来源 |
|---|---|
| 实际程序行为 / API / 数据契约 | 当前 source code + `tests/`（最终依据） |
| AI / contributor 开发规则 | `AGENTS.md` |
| 当前里程碑、验证状态与工程事实 | `docs/HANDOFF_CURRENT.md`、`docs/PROJECT_STATUS.md` |
| 项目总体介绍与使用入口 | 根目录 `README.md` |
| 科学来源与 validation case 背景 | `references/`（本目录） |

如果 `references/` 的内容与当前实现冲突：它**只作为背景资料**，**不得据此直接修改代码**；
应以 source code / `tests/` 与上述项目状态文档为准。

## `reference/` 与 `references/` 的区别

| 路径 | 性质 | 是否进 Git |
|---|---|---|
| `reference/` | 本地原始资料（论文 PDF、旧项目交接文档、聊天式探索记录、临时大文件） | **否**（`.gitignore` 中的 `/reference/`） |
| `references/` | 经过筛选、对外理解项目真正必要的精选资料 | **是** |

> 原始论文 PDF、旧项目交接文档、聊天式探索记录以及其他大文件继续保存在本地 `reference/` 中，不进入 Git 历史。`references/` 只保留对外理解项目真正必要的精选信息。

## 本目录内容

| 文件 | 角色 |
|---|---|
| `README.md` | 本文件：目录定位与权威顺序说明 |
| `PAPERS.md` | 主要科学来源（primary paper）及其被本项目使用的部分 |
| `validation_30_surfaces.md` | 30 曲面验证所使用的精选 case 列表与原始方程（= 测试对象是什么） |

## 对应的实验与证据在哪里

- **测试对象是什么** → `references/validation_30_surfaces.md`（本目录）
- **实际运行了什么、结果如何** → `docs/EXPERIMENT_30_SURFACES_20260915.md`
- **本地原始运行证据** → `work/`（git-ignored，不提交）

`references/` 内**不复制**实验结果或原始日志。
