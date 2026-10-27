---
name: levanta-sales-export
description: 从 Levanta Seller API 按品牌、站点、日期和红人下载出单业绩，输出固定七列 CSV 或 Excel。用于 Levanta 数据导出和多品牌密钥配置；不下载合作红人通讯录，不把汇总冒充逐笔订单。
---

# Levanta 出单数据导出

输出列按此顺序保持不变：

`Marketplace Program | Date | Creator | Clicks | Conversions | Sales | Commission`

每行是一个品牌站点、UTC 日期和红人的业绩。默认只保留 `Conversions > 0`；金额统一为 USD。`Marketplace Program` 为 `品牌 / marketplace`。Clicks 是该红人在该日的点击数，不能换成月度点击数，也不能把日期汇总与月度红人汇总拼接。

## 首次使用先给密钥文件

1. 在用户工作目录运行下列命令，生成供用户填写的文件。将 `<skill>` 替换为本技能的实际目录。

   ```bash
   python3 <skill>/scripts/export_sales.py --init-config ./levanta/accounts.local.json
   ```

2. 给用户这个文件的可点击链接；有文件编辑器时打开它。让用户填写 `api_key`，顶层名称可改为品牌名。不要让用户把密钥发进聊天。等待其填写并保存，之后继续下载。已有文件时复用，初始化命令拒绝覆盖。
3. 多个账号是在同一个 JSON 中增加成员，每个成员有一个 `api_key`。可选 `brand_ids` 数组限制某个密钥下的品牌范围。单个账号可覆盖多个站点，自动读取其品牌列表。

真实配置、缓存和业务附件应位于用户工作目录，不能放进技能目录、安装包或 GitHub。脚本不打印密钥；`.gitignore` 排除私有配置及输出。

## 下载

确认用户所需日期；已明确的日期不要重复询问。“本月截至昨天”按用户当地日期解释，并把选中的日历日期作为 UTC 报表日期。默认导出出单行，若用户要求包含未出单的点击数据，增加 `--all-activity`。

```bash
python3 <skill>/scripts/export_sales.py \
  --config ./levanta/accounts.local.json \
  --start 2026-10-01 --end 2026-10-26 \
  --output ./outputs/levanta
```

日期是示例，实际运行必须替换。`--account 品牌名` 只下载指定配置；不传时合并全部已填写账号。空密钥或无效配置导致明确错误，不悄悄跳过账号。

脚本只使用只读 GET，逐账号/品牌读取日期报表，找到出单日，再以当天起止时间读取红人报表。它处理游标分页、限速及有限重试，逐请求缓存成功响应，失败时不输出“完成”的附件。重新运行相同命令复用缓存；需要更新归因结果时加 `--refresh`。缓存可能含敏感业务数据，留在本机。不要为了加速改成并发请求。

完成后得到 `sales.csv`、供 Excel 导出使用的 `sales.json` 以及 `metadata.json`。只把用户需要的表格作为附件，元数据和缓存默认不附上。核对 metadata 中的日期、币种、行数及总计；空结果也交付只有七列表头的文件并说明无出单。

## Excel 附件

有表格技能/Artifact Tool 环境时，优先给 `.xlsx`。遵循可用的表格技能，发现其运行时和依赖，把本技能的 `scripts/export_xlsx.mjs` 复制到一个临时工作目录，再在该目录配置运行时的 `node_modules`，不要在技能包中安装或打包依赖。

```bash
node export_xlsx.mjs ./outputs/levanta/sales.json ./outputs/levanta/sales.xlsx
```

脚本使用 `@oai/artifact-tool`，输出单张七列表格，并在附件旁保存预览。按可用的表格技能执行开始标记、渲染检查和导出核验。环境无此依赖时交付 CSV，并如实说明；不要让 CSV 假冒成 XLSX。

## 数据口径与后续同步

- Amazon 是每天/红人的业绩汇总，不含订单 ID；“转化数”不能称为独立订单数。
- Date 为 UTC 日历日期。Clicks、Conversions 保持数值；Sales、Commission 为 USD 数值，两位小数。
- 脚本逐日核对红人汇总与日期报表的转化数、销售额和佣金；明显不一致时停止导出，提示刷新重试，不编造差额。
- API 数据会随归因调整；历史缓存不是永久最终结果。对更新的数据使用 `--refresh`。
- 用户要求同步 Google Sheets 时，使用届时可用的 Google Drive/Sheets 工具与技能。指定表格和范围后，按元数据中的 `(账号, brandId, marketplace, date, creatorId)` 更新，七列展示不包含这些内部 ID。单纯导出不自动创建表格或设置定时任务。
- 接口变动、权限或字段异常时，查 [接口说明](references/api.md)。
