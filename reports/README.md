# 本地回归执行报告目录

本目录保存 `~/codespace/magicTest` 在本机执行回归产生的运行日志、截图与 `results.json` / `report.json`（除本文件外，目录下全部内容由 `.gitignore` 忽略，统一不提交 Git）。

- 每次执行全量平台回归（`platform-standard` 或 `platform-abnormal` 且未指定 `--cases` 子集）前，`regression/run_standard.py` 会自动清理此前历史运行记录。
- 如需手动切换空轮次，运行 `python3 -B ~/codespace/magicTest/tools/start_acceptance_round.py YYYY-MM-DD-name`。
