# Animal SQL 查询规范

本文档定义通用查询流程、SQL 结构和当前 Animal 数据模型下的业务规则。文中的 SQL 片段仅展示结构，表名、字段名、日期和筛选值必须根据实际目标表替换后执行。

## 1. 执行流程

生成 SQL 前按以下顺序执行：

1. 识别指标、维度、过滤值、日期范围和时间粒度。
2. 从 `dimensions.md` 将用户说法转换为标准业务维度；`版位`识别为`子平台`，但不在此步骤确定物理字段。
3. 从 `metrics.md` 确认指标公式、默认人群和成熟条件。
4. 从 `tables.md` 确认候选表的指标能力、粒度、分区和该表自己的维度字段映射。不能把一张表的字段映射套用到另一张表。
5. 按本文件“表路由”选择能同时满足指标、维度和口径的目标表。
6. 按本文件“分区和过滤”生成完整过滤条件，再按“聚合和跨表合并”生成查询结构。
7. 校验成熟度、空值、粒度和结果口径后返回结果。

## 2. 表路由

### 2.1 产品端优先级

- APP端（`animal_androidcncm_prod`、`animal_ioscn_prod`、`animal_ohoscn_prod`）未指定关键行为时，优先使用每日汇总表。
- H5端（`animal_h5cn_prod`）无论是否指定关键行为维度，优先使用关键行为汇总表 `dm_ad.app_et_ad_callback_event_da`。
- 目标汇总表不支持指标或指定维度时，可选择另一张支持完整口径的汇总表或用户级明细表。
- 用户指定`行为标签`、关键行为专属`投放分类`或`投放类型=关键行为`时，必须使用关键行为汇总表或能还原同一口径的明细表，并保留关键行为过滤条件。
- 未指定关键行为的普通 APP 查询不能因为关键行为表能一次返回多个指标，就改用关键行为表。

### 2.2 按维度选择候选表

| 用户指定内容 | 表选择规则 |
|---|---|
| `行为标签`或关键行为专属`投放分类` | 只能使用关键行为汇总表，除非表目录明确说明其他表具有完全一致的口径。 |
| `投放类型=关键行为` | 使用关键行为汇总表，并保留关键行为类型过滤。 |
| 仅指定通用维度，如展现类型、广告平台、来源平台、投放账户、日期 | APP端优先每日汇总表；H5端优先关键行为汇总表；目标表不支持时再选择其他汇总表或明细表。 |

### 2.3 当前项目的关键行为表

`dm_ad.app_et_ad_callback_event_da`是全量快照表，必须使用`ds=昨天`并限制目标`appid`；业务日期通过`substr(install_date, 1, 10)`筛选。其`pay_cny_day{N}`字段已经是净收入，不再关联内购分成比例表；该汇总表也不与用户归因、付费、活跃或闯关明细直接关联。

## 3. 分区和日期条件

- 有分区的事实表必须限制完整分区键 `ds` 和 `appid`；无分区表不添加 `ds` 条件。
- `全量快照`表固定使用 `ds=昨天`，业务日期另用 `install_date` 等字段筛选。
- `日增量明细`表按事件日期范围限制 `ds`；用户归因表的 `ds` 是用户新增日期。
- 用户新增日期字段按目标表结构使用 `substr(install_date, 1, 10)` 等表达式筛选。
- 未指定产品时不能省略 `appid`；无法从问题确定产品时先询问。
- 内购分成比例表 `dm_ad.dim_et_custom_pay_da` 无分区键，不添加 `ds`；如有 `appid`，按目标产品过滤。

## 4. 维度和展现类型过滤

- 先在 `dimensions.md` 确定标准业务维度，再从已选目标表的字段映射确定物理字段；不能根据字段名猜测业务含义。
- 未分析的投放细分维度必须使用该表对应的 `all` 值；正在分析的维度使用真实值并加入 `GROUP BY`。
- `media_cn_name` 和 `report_type` 使用真实值，不使用 `all`。
- 用户说“广告量”时使用 `report_type='ad'`；说“测试量”或“广告测试”时使用 `report_type='adtest'`。
- `organic`表示自然量。`deeplink`、`deeplink-测试`、`deeplink-直拉`、`mkt` 等值只有用户明确指定或业务规则明确说明时才使用，不能自动并入广告量。
- 正式查询前确认目标表昨天分区实际存在目标展现类型和维度值。

## 5. 聚合和跨表合并

- 日级可加总字段先按目标日期和分析维度 `SUM`，再计算比率或人均指标；不能直接平均行级比率。
- `back_equip_total` 使用 `try_cast(... AS bigint)` 后再求和。
- `{N}`是字段模式，必须替换为目标表中实际存在的周期字段，例如 `new_udid_day7`。
- 每日汇总表中不同指标来自不同物理表时，各表先按相同日期、产品和分析维度聚合，转换为统一列结构后使用 `UNION ALL`，最后汇总。不能用内连接，否则一张表缺日期或无数据会过滤其他指标。
- 同一个指标不得同时从每日汇总表和关键行为汇总表取数后 `UNION` 或 `UNION ALL`；需要对照时分别返回。
- APP端广告成本是当前项目的特殊口径：成本与媒体表的媒体折后成本、新增设备表的固定成本分别聚合后相加；H5端只使用成本与媒体表，不加固定成本。两张表不得多对多 `JOIN`。
- 查询新增和回流整体收入时，分别从新增表和回流表取数，再按完全一致的日期、粒度和维度合并；不得只取新增表后称为整体收入。
- 汇总表不与用户归因、付费、活跃或闯关明细直接关联。

## 6. 用户级明细关联

- 用户归因、付费、活跃和闯关明细表均需限制 `ds` 与 `appid`。归因表按新增日期限制 `ds`，行为明细表按事件日期限制 `ds`。
- 先在 `bi.animal_uid_ray_2026` 圈定并去重用户，再关联明细表。用户 ID 默认关系为：归因表 `udid` = 付费表 `user_id` = 活跃表 `uid` = 闯关表 `uid`。
- 游戏通服时，归因表 `appid`表示买入端；付费、活跃和闯关明细默认使用四端产品范围。只有用户明确指定行为发生端时，才限制明细表为单个 `appid`。
- 付费设备数和付费率按去重后的 `user_id` 统计，不能按订单行数统计；存在一对多关系时先在用户或订单粒度去重。
- 活跃日使用活跃表 `ds`；付费事件日使用 `paytime` 截取日期；留存日按新增日期与活跃日期的差计算。
- 用户明确说`新用户`、`老用户`或`回流用户`时，只限制 `user_type`，不限制 `new_equip`。只说`新增`、`新增设备`或`回流设备`时，只限制 `new_equip`，不限制 `user_type`。两类条件不能互相替代。
- 只分析新增设备时，用户归因表使用 `report_type='ad' AND new_equip='1'`；分析新增和回流整体时，不限制 `new_equip`。
- 用户级净收入使用付费明细`a LEFT JOIN dm_ad.dim_et_custom_pay_da dim`，按 `appid`、`LOWER(pay_type)`、`LOWER(platform)` 和生效日期区间匹配；净收入为 `a.pay_amount_cny * COALESCE(dim.rate, 1)`。必须使用左连接，未匹配分成比例时按1计算。

## 7. 指标成熟度和空结果回查

- N日指标对应新增后的第 `N-1` 天。以查询时点的昨天为数据截止日，新增日期到昨天的日期差小于 `N-1` 天时，该新增日期的 N 日分子和对应分母都必须排除。
- 未成熟指标不计算、不填 0，也不能只排除分子而保留分母。
- 汇总表结果为空、指标无记录或分区未更新时，依次检查 `ds`、`appid`、展现类型、维度过滤和成熟条件，再按路由规则尝试其他汇总表或用户级明细表。所有支持同一口径的表都无数据时，才能说明指标暂无数据。
- 确认没有发生收入或成本时，空值可以按 0 参与汇总；字段缺失、口径不适用或分母无效时必须返回空值，不能强行填 0。

## 8. 引擎、安全和结果控制

- 默认引擎为 `trino_new`；只有 SQL 复杂度确实需要或执行日志明确显示能力问题时，才使用 `tez_new` 或 `spark_on_ack`，并同步适配 SQL 方言。
- 只生成单条只读查询，不生成写入、删除或修改语句。
- 比率、ROI、LTV、CPI和人均指标使用 `nullif` 防止除零，并显式进行浮点计算。
- 查询条件必须覆盖产品、日期和必要的展现类型条件。
- 返回前检查日期、产品、展现类型、维度、粒度、成熟度和跨表合并逻辑，确认没有因 `JOIN`、`UNION` 或多层聚合造成重复或数据丢失。

## 9. 核心 SQL 示例

### 9.1 分区条件

```sql
-- 全量快照表：ds固定为昨天，业务日期另用业务字段筛选
WHERE ds = '${snapshot_date}'
  AND appid = '${target_appid}'
  AND substr(install_date, 1, 10) BETWEEN '${start_date}' AND '${end_date}'

-- 日增量明细表：ds按事件日期范围限制
WHERE ds BETWEEN '${event_start_date}' AND '${event_end_date}'
  AND appid IN ('${appid_1}', '${appid_2}')
```

### 9.2 维度过滤和聚合

```sql
SELECT media_cn_name, SUM(metric_value) AS metric_value
FROM target_table
WHERE track_id = 'all'
  AND media_inventory_cn_name = 'all'
  AND media_cn_name = '${media}'
GROUP BY media_cn_name;
```

### 9.3 不同表提供不同指标

```sql
WITH metric_a AS (
    SELECT dt, SUM(metric_a) AS metric_a, 0.0 AS metric_b
    FROM table_a
    GROUP BY dt
), metric_b AS (
    SELECT dt, 0.0 AS metric_a, SUM(metric_b) AS metric_b
    FROM table_b
    GROUP BY dt
)
SELECT dt, SUM(metric_a) AS metric_a, SUM(metric_b) AS metric_b
FROM (SELECT * FROM metric_a UNION ALL SELECT * FROM metric_b) s
GROUP BY dt;
```

### 9.4 N日成熟日期

```sql
-- N日对应新增后的第N-1天
WHERE date_diff(
          'day',
          CAST(substr(install_date, 1, 10) AS DATE),
          DATE '${data_end_date}'
      ) >= ${N_MINUS_1}
```

### 9.5 用户级净内购收入

```sql
SELECT a.user_id,
       a.pay_amount_cny * COALESCE(dim.rate, 1) AS pay_custom
FROM payment_detail a
LEFT JOIN dm_ad.dim_et_custom_pay_da dim
  ON a.appid = dim.appid
 AND LOWER(a.pay_type) = LOWER(dim.pay_type)
 AND LOWER(a.platform) = LOWER(dim.platform)
 AND a.ds BETWEEN dim.start_date AND dim.stop_date;
```

### 9.6 通服用户关联

```sql
WITH attributed AS (
    SELECT DISTINCT udid
    FROM bi.animal_uid_ray_2026
    WHERE ds BETWEEN '${install_start_date}' AND '${install_end_date}'
      AND appid = '${attribution_appid}'
)
SELECT COUNT(DISTINCT p.user_id) AS pay_users
FROM attributed u
JOIN payment_detail p
  ON u.udid = p.user_id
WHERE p.ds BETWEEN '${event_start_date}' AND '${event_end_date}'
  AND p.appid IN ('${app_appid}', '${h5_appid}');
```
