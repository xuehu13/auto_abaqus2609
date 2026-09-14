# docs/legacy — v0.1 原始交付 artifacts

本目录保存 v0.1 原始交付包（DiffuMeta_Automation_v0.1）中已不作为活动入口的文件，字节保持原样：

- `PACKAGE_SHA256_v0.1.json`：v0.1 交付包完整性清单。其中相对路径仅描述当时的
  `DiffuMeta_Automation_v0.1/DiffuMeta_Automation_v0.1` 包内布局，不代表本仓库当前结构；
  没有任何活动代码引用或校验它，仅作为历史证据保留。
- `requirements_v0.1.txt`：v0.1 时代的 pip 依赖说明。当前唯一依赖真值是根目录
  `pixi.toml + pixi.lock`；请勿使用 `pip install -r` 安装本项目。

两文件原名为 `PACKAGE_SHA256.json`、`requirements.txt`，2026-09-14 仓库结构重构时移入本目录并加 `_v0.1` 后缀，内容未改动。
