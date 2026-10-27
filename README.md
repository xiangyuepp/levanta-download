# Levanta 下载

一个可安装的 Codex Skill。先生成本地 API key 填写文件，再按品牌、站点、日期和红人导出出单业绩。

输出固定七列：

| Marketplace Program | Date | Creator | Clicks | Conversions | Sales | Commission |
| --- | --- | --- | --- | --- | --- | --- |

日期为 UTC，金额统一为 USD。默认仅导出 `Conversions > 0` 的行。每行是每天/红人的业绩汇总，不是逐笔订单。

## 安装与使用

将仓库中的 `levanta-sales-export` 文件夹放进 `~/.codex/skills/`，或让 Codex 从本仓库安装该目录。

在 Codex 中输入：

> 使用 $levanta-sales-export 下载本月截至昨天的出单数据，先给我 API key 填写文件。

首次使用会生成 `accounts.local.json`，用户只需修改品牌名并填写 `api_key`。多个品牌密钥可以放在同一个文件；实际密钥只保存在使用者电脑上。示例模板：[accounts.example.json](levanta-sales-export/assets/accounts.example.json)。

## 直接运行

需要 Python 3.10 或更新版本；下载和 CSV 导出只用标准库，无需额外安装 Python 依赖。

```bash
python3 levanta-sales-export/scripts/export_sales.py --init-config ./levanta/accounts.local.json
```

填写并保存文件后，选择日期运行（下列日期仅为示例）：

```bash
python3 levanta-sales-export/scripts/export_sales.py \
  --config ./levanta/accounts.local.json \
  --start 2026-10-01 --end 2026-10-26 \
  --output ./outputs/levanta
```

默认导出所有已填写账号，`--account 品牌名` 只导出一个；`--all-activity` 包含未出单的点击数据。成功响应会缓存在本机，失败后可重跑继续；需要刷新历史归因数据时加 `--refresh`。429 和临时服务错误有有限重试，不会把部分数据当成完整附件。

输出 `sales.csv`、`sales.json` 和 `metadata.json`。CSV 可导入 Google Sheets。Excel 导出由 Codex 中可用的表格/Artifact Tool 环境执行，详见 [SKILL.md](levanta-sales-export/SKILL.md)；没有相应依赖时仍可使用 CSV。

## 验证

```bash
python3 levanta-sales-export/scripts/test_export_sales.py
```

测试使用合成数据，无需密钥。仓库不包含真实密钥、业务数据、下载缓存或依赖包。不调用合作红人通讯录和产品清单接口。
