# Animal 数据表目录

## 表选择总览

| 逻辑表 | 物理表 | 粒度 | `ds`读取类型 | 主要用途 |
|---|---|---|---|---|
| 成本与媒体表 | `dm_ad.app_et_ad_cost_report_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 广告成本、曝光、点击、预约 |
| 新增设备表 | `dm_ad.app_et_ad_equip_new_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备、实名新增设备、固定成本 |
| 回流设备表 | `dm_ad.app_et_ad_equip_back_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 回流设备 |
| 首日行为表 | `dm_ad.app_et_ad_firstday_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 首日在线时长、首日登录、等级行为 |
| 留存表 | `dm_ad.app_et_ad_retention_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日留存 |
| 付费设备表 | `dm_ad.app_et_ad_pay_num_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日付费设备数、截至当前付费设备数 |
| 收入表 | `dm_ad.app_et_ad_revenue_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日累计收入 |
| 回流收入表 | `dm_ad.app_et_ad_back_revenue_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 回流设备N日累计收入 |
| 净收入表 | `dm_ad.app_et_ad_custom_revenue_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日累计净收入及拆分收入 |
| 回流净收入表 | `dm_ad.app_et_ad_back_custom_revenue_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 回流设备N日累计净收入及拆分收入 |
| 内购收入表 | `dm_ad.app_et_ad_pay_amount_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日累计内购收入 |
| 回流内购收入表 | `dm_ad.app_et_ad_back_pay_amount_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 回流设备N日累计内购收入 |
| 变现收入表 | `dm_ad.app_et_ad_advmon_pay_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日累计变现收入 |
| 回流变现收入表 | `dm_ad.app_et_ad_back_advmon_pay_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 回流设备N日累计变现收入 |
| 内购次数表 | `dm_ad.app_et_ad_pay_times_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 新增设备N日累计内购次数 |
| 关键行为汇总表 | `dm_ad.app_et_ad_callback_event_da` | 展现类型 + 投放维度 + 新增日期 | 全量快照 | 关键行为、投放维度及汇总指标 |
| 用户归因表 | `bi.animal_uid_ray_2026` | 用户 | 日增量明细 | 圈定广告用户、新设备、回流用户和投放维度；`ds`为用户新增日期 |
| 付费明细表 | `dw_dp.dwd_dp_payment_success_basic_di` | 用户 + 付费事件 | 日增量明细 | 用户级付费、净收入、付费用户数 |
| 活跃明细表 | `dw_dp.dwd_dp_login_user_active_mid_v2_di` | 用户 + 活跃日期 | 日增量明细 | 用户级活跃、留存和DAU |
| 闯关明细表 | `bi.animal_stage_ray_2026` | 用户 + 闯关事件 | 日增量明细 | 闯关次数、过关次数和闯关行为 |
| 内购分成比例表 | `dm_ad.dim_et_custom_pay_da` | 支付类型 / 渠道 | 无分区 | 提供内购分成比例，用于计算净收入 |

### 分区与`ds`读取规则

除内购分成比例表外，上表中的事实表均为`ds`、`appid`双分区，查询时必须同时限制两个分区。`ds`读取类型含义如下：

| `ds`读取类型 | 含义 | 查询条件 |
|---|---|---|
| `全量快照` | 每个`ds`分区保存截至该快照日的完整历史数据 | 固定使用`ds=昨天`，日期范围再使用`install_date`等业务日期字段筛选 |
| `日增量明细` | 每个`ds`分区只保存该日产生的事件 | 按事件发生日期范围限制`ds`，事件时间字段用于更细粒度筛选 |
| `无分区` | 表不存在`ds`分区 | 不添加`ds`条件；有`appid`字段时按目标产品过滤 |

“全量快照”描述的是单个快照分区的数据覆盖范围，不表示该表只包含广告量；表中的实际展现类型仍需按用户问题和知识库规则过滤。内购分成比例表`dm_ad.dim_et_custom_pay_da`无分区，不添加`ds`条件。

## 每日汇总表

每日汇总表按展现类型、投放维度和新增日期预聚合，可覆盖广告量、自然量、测试量和直拉等展现类型，但每张表的实际支持范围可能不同。APP端未明确关键行为时优先从每日汇总表取数；H5端优先从关键行为汇总表取数；目标指标或维度不受优先表支持时，可改用其他汇总表或用户级明细表。APP端查询广告成本时，还必须从新增设备表读取固定成本，与成本与媒体表的媒体折后成本分别聚合后相加；H5端不读取固定成本。该组表的`ds读取类型`均为`全量快照`，固定使用`ds=昨天`，新增日期使用`substr(install_date, 1, 10)`筛选。完整路由规则按`sql.md`执行。

汇总表能够查询但目标指标没有数据时，不能直接返回空结果。应按`sql.md`检查查询条件，并依次尝试其他支持同一口径的汇总表和用户级明细表，避免将底层数据未更新误判为业务指标为空。

### 业务维度与物理字段

每日汇总表中的业务维度名称统一使用`dimensions.md`的规范名称，实际SQL字段如下：

| 业务维度 | 物理字段 | 使用说明 |
|---|---|---|
| `appid` | `appid` | 产品分区，必须限制目标产品 |
| `新增日期` | `install_date` | 使用`substr(install_date, 1, 10)` |
| `广告平台` | `media_cn_name` | 使用真实值或按该维度分组，不能写`= 'all'` |
| `展现类型` | `report_type` | 使用真实值或按该维度分组，不能写`= 'all'` |
| `监测链接` | `track_id` | 不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `子平台`（版位） | `media_inventory_cn_name` | 用户说`子平台`或`版位`时均映射到此字段；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `投放账户` | `media_account_id` | 不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `来源平台` | `media_ad_cn_name` | H5来源平台；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `广告创意` | `media_creative_cn_name` | 不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `广告系列` | `media_campaign_cn_name` | 不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `代理商` | `agent_cn_name` | 不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `优化师` | `optimizer_user` | 不分析时使用`= 'all'`，分析时使用真实值并分组 |

不分析的投放细分维度使用 `= 'all'`；正在分析的维度使用真实值并加入 `GROUP BY`。`media_cn_name` 和 `report_type` 按真实值过滤，不使用 `= 'all'`。

业务名称与 `report_type` 的默认对应关系为：`广告量`对应 `ad`，`测试量`或`广告测试`对应 `adtest`。`deeplink`、`deeplink-测试`、`deeplink-直拉`、`mkt` 等其他值不自动并入`广告量`，只有用户明确指定或业务规则明确说明时才使用。`organic`表示自然量。具体表是否包含目标值，必须先查询该表昨天分区的实际值，不能仅凭通用定义假设。

### 指标与字段

| 物理表 | 主要字段 | 指标能力与口径 |
|---|---|---|
| `dm_ad.app_et_ad_cost_report_da` | `discounted_cost_cny`、`cost_cny`、`impression`、`click`、`reserve` | 媒体折后成本、媒体源成本、曝光、点击、预约 |
| `dm_ad.app_et_ad_equip_new_da` | `all_new_equip_total`、`real_name_equip_total`、`stand_by_cost` | 新增设备、实名新增设备、固定成本 |
| `dm_ad.app_et_ad_equip_back_da` | `back_equip_total` | 回流设备，仅适用于广告量相关展现类型 |
| `dm_ad.app_et_ad_firstday_da` | `new_udid_online_min`、`new_udid_login_day1`~`new_udid_login_day4`、`new_udid_dd1_2`、`new_udid_dd1_10`、`new_udid_dd3_2`、`new_udid_dd3_10` | 新增设备首日在线时长、登录和等级行为 |
| `dm_ad.app_et_ad_retention_da` | `new_udid_day{N}` | 新增设备第N日留存数，N取2/3/7/14/30/60/90/180 |
| `dm_ad.app_et_ad_pay_num_da` | `new_udid_pay_num_day{N}`、`new_udid_pay_num_tonow`、`new_udid_passs_stage_pay_num_day1` | 新增设备N日累计付费设备数、截至当前付费设备数、首日过关付费设备数 |
| `dm_ad.app_et_ad_revenue_da` | `new_udid_revenue_cny_day{N}`、`new_udid_revenue_cny_tonow` | 新增设备N日累计收入及截至当前收入 |
| `dm_ad.app_et_ad_back_revenue_da` | `back_udid_revenue_cny_day{N}`、`back_udid_revenue_cny_tonow` | 回流设备N日累计收入及截至当前收入，仅适用于广告量 |
| `dm_ad.app_et_ad_custom_revenue_da` | `new_udid_revenue_cny_day{N}`、`new_udid_revenue_cny_tonow`、`new_udid_custom_revenue_cny_tonow`、`new_equip_new_user_revenue_cny_day1`、`new_equip_back_user_revenue_cny_day1` | 新增设备N日累计净收入、截至当前净收入及新老用户拆分收入 |
| `dm_ad.app_et_ad_back_custom_revenue_da` | `back_udid_revenue_cny_day{N}`、`back_udid_revenue_cny_tonow`、`back_udid_custom_revenue_cny_tonow`、`old_equip_new_user_revenue_cny_day1`、`old_equip_back_user_revenue_cny_day1` | 回流设备N日累计净收入、截至当前净收入及新老用户拆分收入，仅适用于广告量 |
| `dm_ad.app_et_ad_pay_amount_da` | `new_udid_pay_cny_day{N}`、`new_udid_pay_cny_tonow` | 新增设备N日累计内购收入及截至当前内购收入 |
| `dm_ad.app_et_ad_back_pay_amount_da` | `back_udid_pay_cny_day{N}`、`back_udid_pay_cny_tonow` | 回流设备N日累计内购收入及截至当前内购收入，仅适用于广告量 |
| `dm_ad.app_et_ad_advmon_pay_da` | `new_udid_advmon_cny_day{N}`、`new_udid_advmon_cny_tonow` | 新增设备N日累计变现收入及截至当前变现收入 |
| `dm_ad.app_et_ad_back_advmon_pay_da` | `back_udid_advmon_cny_day{N}`、`back_udid_advmon_cny_tonow` | 回流设备N日累计变现收入及截至当前变现收入，仅适用于广告量 |
| `dm_ad.app_et_ad_pay_times_da` | `new_udid_pay_times_day{N}`、`new_udid_pay_times_tonow` | 新增设备N日累计内购次数及截至当前内购次数 |

其中，`{N}`表示同类字段的N日后缀，例如 `new_udid_revenue_cny_day7`。`tonow`表示截至当前。字段是否真实存在及支持的N取值，以目标表实际结构为准。

## 关键行为汇总表

物理表：`dm_ad.app_et_ad_callback_event_da`

该表同时承载关键行为标签、投放维度和广告汇总指标，`ds`读取类型为`全量快照`，分区键为`ds`和`appid`，固定使用`ds=昨天`并同时限制目标`appid`。H5端优先使用该表；目标指标或维度不受支持时，可改用每日汇总表或用户级明细表。APP端只有出现`行为标签`、关键行为专属`投放分类`或`投放类型=关键行为`时才使用该表。

### 维度字段

| 字段 | 类型 | 含义 | 约束 / 备注 |
|---|---|---|---|
| `ds` | string | 快照更新日期 | 分区键；必须`=昨天` |
| `install_date` | string | 用户新增日期，格式`YYYY-MM-DD HH:mm:ss` | 日期筛选、分组和排序必须使用`substr(install_date, 1, 10)` |
| `appid` | string | 产品应用标识 | 分区键；必须限制目标产品 |
| `media_cn_name` | string | 广告平台，例如腾讯广告、巨量引擎 | 不分析时也不能写`= 'all'`；使用真实值或按该维度分组 |
| `report_type` | string | 展现类型 | 不分析时也不能写`= 'all'`；广告量默认`ad`，测试量默认`adtest`，自然量使用`organic` |
| `data_tag_type` | string | 投放类型 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `data_tag` | string | 行为标签 | 关键行为维度；不分析时使用`= 'all'`，分析时必须使用用户指定值并分组 |
| `account_mode` | string | 投放模式 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `native_ad` | string | 广告形态 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `bid_type` | string | 出价方式 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `directed_type` | string | 定向方式 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `supplier_name` | string | 投放分类，例如`付费_智投` | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `category` | string | 优化师 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `media_account_id` | string | 投放账户 | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `media_ad_cn_name` | string | 来源平台，例如`wechatgame`、`douyin_game` | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `media_inventory_cn_name` | string | 子平台（版位），例如`微信朋友圈`、`微信视频号` | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |
| `delivery_mode` | string | 投放端口，例如`ios`、`android+ios` | 投放细分维度；不分析时使用`= 'all'`，分析时使用真实值并分组 |

`ds`、`appid`、`install_date`、`media_cn_name`和`report_type`是基础字段；其余字段是可拆分的投放细分维度。做多维聚合时，所有未出现在`GROUP BY`中的投放细分维度都必须保留`= 'all'`条件，不能省略，否则同一人群会被多个维度切片重复累计。字段实际取值以目标分区查询结果为准。

### 指标字段

| 字段 | 含义 | 查询用途 |
|---|---|---|
| `new_udid` | 新增设备数 | 新增规模和比率分母 |
| `back_udid` | 回流设备数 | 广告整体规模；仅适用于广告量 |
| `cost_cny` | 广告成本 | CPI、ROI |
| `impression` | 媒体曝光 | eCPM、CTR |
| `click` | 媒体点击 | CTR、点击率 |
| `new_udid_day{N}` | 新增设备第N日留存数 | N日留存率 |
| `pay_cny_day{N}` | 新增和回流累计N日净收入 | N日ROI、LTV |
| `new_udid_pay_num_day{N}` | 新增设备累计N日付费设备数 | N日付费率 |

## 用户级明细表

### 用户归因表

物理表：`bi.animal_uid_ray_2026`，分区键：`ds`、`appid`；`ds`是用户新增日期分区，不是快照日期。

| 字段 | 含义 | 使用规则 |
|---|---|---|
| `udid` | 用户ID，也是用户级关联主键 | 关联付费表 `user_id`、活跃表 `uid`、闯关表 `uid` |
| `report_type` | 展现类型 | `ad`广告量、`adtest`测试量、`organic`自然量等，按用户问题过滤 |
| `new_equip` | 新老设备 | `1`新增设备、`0`老设备 |
| `user_type` | 新老用户 | `new`新用户、`back`老用户/回流用户 |
| `platform` | 来源平台 | H5来源平台，按表中实际值过滤 |
| `media_cn_name` | 广告平台 | 广告归因维度 |
| `data_tag` | 行为标签 | 关键行为筛选 |
| `track_id` | 监测链接 | 仅在用户问题指定时使用 |
| `media_inventory_cn_name` | 子平台 | 仅在用户问题指定时使用 |
| `account_id` | 投放账户 | 仅在用户问题指定时使用 |
| `campaign_name` | 广告系列 | 仅在用户问题指定时使用 |
| `ad_group_name`、`ad_group_id` | 广告组 | 仅在用户问题指定时使用 |
| `creative_name` | 广告创意 | 仅在用户问题指定时使用 |
| `target_os` | 投放端口 | 仅在用户问题指定时使用 |
| `supplier_name` | 投放分类 | 仅在用户问题指定时使用 |
| `optimizer_user` | 优化师 | 仅在用户问题指定时使用 |
| `real_name` | 实名状态 | 实名相关分析 |
| `stop_date` | 当前归因周期的结束日期，等于该设备下一次回流的 `install_date` | 关联活跃、付费、闯关等行为时必须使用右开区间：行为日期 `>= install_date` 且 `< stop_date` |
| `ds` | 用户新增日期分区 | 按用户新增日期范围限制，不固定为昨天 |
| `appid` | 归因端产品分区 | 限制为用户被买入或归因的目标端 |

### 付费明细表

物理表：`dw_dp.dwd_dp_payment_success_basic_di`，分区键：`ds`、`appid`。

| 字段 | 含义 | 使用规则 |
|---|---|---|
| `user_id` | 付费用户ID | 默认与用户归因表 `udid` 关联 |
| `udid` | 付费事件中的设备标识 | 不是默认用户关联键，除非业务明确要求按设备关联 |
| `server_time` | 付费数据采集时间 | 日级筛选和分区条件优先使用付费表 `ds`，需要精确到时分秒时使用 |
| `pay_amount_cny` | 人民币支付金额 | 毛收入基础字段 |
| `pay_amount`、`currency` | 原币支付金额和币种 | 需要原币分析时使用；人民币指标优先使用 `pay_amount_cny` |
| `pay_type`、`pay_unit`、`goods_id` | 支付类型、支付单位、商品ID | 支付类型或商品拆分 |
| `platform` | 支付平台 | 与内购分成比例表的 `platform` 匹配；匹配时两侧使用 `LOWER()` |
| `order_id` | 订单ID | 订单去重或订单级分析 |
| `role_id` | 角色ID | 角色级分析 |
| `ds` | 付费事件分区日期 | 必须限制在目标付费日期范围内 |
| `appid` | 行为发生端产品分区 | Animal 采用通服归因，默认限制四端：`animal_androidcncm_prod`、`animal_ioscn_prod`、`animal_ohoscn_prod`、`animal_h5cn_prod`；只有用户明确指定行为端时才限制单个产品 |

### 活跃明细表

物理表：`dw_dp.dwd_dp_login_user_active_mid_v2_di`，分区键：`ds`、`appid`。

| 字段 | 含义 | 使用规则 |
|---|---|---|
| `uid` | 活跃用户ID | 与用户归因表 `udid` 关联 |
| `udid` | 设备标识 | 设备级分析时使用，不替代 `uid` 做用户关联 |
| `server_time`、`client_time` | 服务端和客户端时间 | 事件时间分析；日级活跃优先按 `ds` |
| `user_level`、`role_id` | 用户等级、角色ID | 用户等级或角色分析 |
| `user_platform`、`sub_platform`、`game_version`、`network_type`、`device_model`、`os_version` | 活跃设备和环境信息 | 仅在用户问题指定时使用 |
| `is_valid_uid`、`is_valid_udid`、`is_old_user` | 用户/设备有效性和新老标识 | 需要排除无效记录或拆分新老用户时使用 |
| `ds` | 活跃日期分区 | 必须限制在目标活跃日期范围内；留存日按新增日期与目标活跃日关联 |
| `appid` | 行为发生端产品分区 | Animal 采用通服归因，默认限制四端：`animal_androidcncm_prod`、`animal_ioscn_prod`、`animal_ohoscn_prod`、`animal_h5cn_prod`；只有用户明确指定行为端时才限制单个产品 |

### 闯关明细表

物理表：`bi.animal_stage_ray_2026`，分区键：`ds`、`appid`。

| 字段 | 含义 | 使用规则 |
|---|---|---|
| `uid` | 闯关用户ID | 与用户归因表 `udid` 关联 |
| `stage_times` | 关卡行为次数 | 按用户、关卡或日期汇总 |
| `stage_true_times` | 有效关卡行为次数 | 业务指标明确要求有效次数时使用 |
| `ds` | 闯关事件日期分区 | 必须限制在目标事件日期范围内 |
| `appid` | 行为发生端产品分区 | Animal 采用通服归因，默认限制四端：`animal_androidcncm_prod`、`animal_ioscn_prod`、`animal_ohoscn_prod`、`animal_h5cn_prod`；只有用户明确指定行为端时才限制单个产品 |

### 内购分成比例表

物理表：`dm_ad.dim_et_custom_pay_da`，无分区键。

| 字段 | 含义 | 使用规则 |
|---|---|---|
| `appid` | 产品标识 | 与付费明细的 `appid` 匹配 |
| `pay_type`、`platform` | 支付类型、支付平台 | 与付费明细对应维度匹配 |
| `rate` | 内购分成比例 | 净收入使用 `a.pay_amount_cny * coalesce(dim.rate, 1)` |
| `start_date`、`stop_date` | 换算比例生效区间 | 按付费时间匹配有效区间 |
