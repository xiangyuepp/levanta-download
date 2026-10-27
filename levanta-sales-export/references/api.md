# Levanta Seller API v2

Base: `https://app.levanta.io/api/seller/v2`

认证：`Authorization: Bearer <api_key>`。密钥来自 Levanta 的 Settings → API。

- `GET /brands`：`marketplace=all`，`limit=100`，返回 `brands` 和 `cursor`。品牌字段含 `id`、`name`、`marketplace`。
- `GET /reports/performance/date`：`start`、`end` 为 UTC ISO 时间；支持 `brandIds`、`marketplaces`、`currency=USD`，返回 `rows: [{date, metrics}]`。
- `GET /reports/performance/creator`：同样的时间、品牌和站点筛选，另有 `limit`、`cursor`，返回 `rows: [{creator: {id,name} | null, metrics}]`。必须按天请求，才可获得日期与红人的交叉明细。
- 分页直到 `cursor` 为 null。分页游标重复或响应字段缺失视为错误。
- 销售额与佣金来自 `metrics.sales`、`metrics.commission` 的十进制字符串；Clicks 与 Conversions 来自对应数值字段。
- 报表查询时间为起日 `00:00:00.000Z` 到止日 `23:59:59.999Z`。脚本将日期查询分为不超过 31 天的窗口。
- 401/403 提示检查密钥和权限。429 与部分 5xx 可以有限重试并尊重 Retry-After；重试耗尽即停止，不交付部分数据冒充完整结果。
- 本流程不调用 `/creators/active` 或 `/products`。不需要合作红人邮箱、通讯录和产品清单。

官方资料：

- [Seller v2 文档](https://api-docs.levanta.io/v2/seller)
- [OpenAPI 定义](https://app.levanta.io/api/seller/v2/openapi.json)
- [认证](https://api-docs.levanta.io/authentication)

若字段或权限与这里不同，以当前官方定义和实际接口响应为准，不猜测替代数据。
