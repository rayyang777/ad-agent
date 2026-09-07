# Animal 广告投放业务指标定义

> 本文档定义 Animal 广告投放（买量）异动归因任务中常见的监控指标。
> SQL 写法 / 表结构 / 强制约束请见 `sql_guidelines.md`。

---

## 一、通用术语与口径

### 1.1 用户身份

| 概念 | 字段 | 取值 | 说明 |
|---|---|---|---|
| 用户ID | `udid`（用户表）/ `user_id`（付费表）/ `uid`（活跃·闯关表） | — | - |
| 用户来源 | `report_type` | `ad`（广告量）/ `organic`（自然量） | 广告投放分析默认只看 `ad` |
| 新老设备 | `new_equip` | `1` 新设备 / `0` 老设备 | 「新增」口径用此字段 |
| 新老用户 | `user_type` | `new` 新用户 / `back` 回流 | 「回流」口径用此字段 |

> **用户归因**：用户在哪个端被广告买进，后续在任意端的活跃 / 付费都归到首次买进的端。
> **多端 appid**：APP 端 `animal_androidcncm_prod` / `animal_ioscn_prod` / `animal_ohoscn_prod`；H5 端 `animal_h5cn_prod`（含微小、抖小）。

### 1.2 时间口径

Animal 的 day 编号**从 1 起算**：**首日 = D1**（新增当日），次日 = D2，第 N 日 = DN。

| 概念 | 解释 |
|---|---|
| D1 / 首日 | 用户首次进入的日期；汇总表 `install_date`（带时间后缀，必须 substr）/ 基础表用户表 `ds` |
| DN | 第 N 日，对应 `install_date + (N-1)` 天 |
| N 日累积 | D1 ~ DN 共 **N 个自然日**（含首日） |

> 汇总表 `*_day{N}` 字段口径**混合**，不要一律当成累积：
> - **累积口径**（D1 ~ DN 共 N 个自然日）：`pay_cny_day{N}`、`new_udid_pay_num_day{N}`。例 `pay_cny_day7` = D1~D7 累计净内购。
> - **时点口径**（仅第 N 日）：`new_udid_day{N}` = 第 N 日仍活跃的新增设备数（用于留存率，非累积）。例 `new_udid_day2` = 次日留存设备数。

### 1.3 收入口径

- **毛收入**：付费表 `pay_amount_cny`（用户支付的原始金额）
- **净收入**：毛收入 × `dim_et_custom_pay_da.rate`（扣除渠道分成）

ROI / 付费金额相关指标默认按净收入口径：汇总表 `pay_cny_day{N}` 已是净收入；基础表必须按 `sql_guidelines.md` 3.2.2 的写法 join 维表换算。

### 1.4 「新增 + 回流」与「新增」

汇总表的字段口径**不一致**，使用时务必对齐：

| 字段 | 口径 |
|---|---|
| `new_udid` / `new_udid_day{N}` / `new_udid_pay_num_day{N}` | 仅**新增设备** |
| `back_udid` | 仅**回流设备** |
| `pay_cny_day{N}` | **新增 + 回流**累积净内购 |
| `cost_cny` | 广告成本（对应新增 + 回流整体投入）|

⚠️ N 日 ROI 的分子是「新增 + 回流」、分母是 cost；N 日付费率分子分母都仅「新增」。不要混。

### 1.5 数据成熟度（N 日指标必读）

⚠️ N 日指标只在 `install_date` 满 N 日的行上才有完整数据。

- **成熟条件**：`install_date <= ds - (N-1) 天`（ds = 昨天）
- **两条铁律**：
  1. `install_date` 上限取成熟截止日，未成熟行排除。
  2. 分子分母必须在**同一个** `install_date` 范围内累加，否则比率被稀释。

**例**：ds = 2026-05-07 算「上个月 D30 ROI」：D30 成熟截止 = 2026-04-08，上个月（04-01 ~ 04-30）实际可用仅 **04-01 ~ 04-08（8 天）**。分子分母都限制在这 8 天，报告中务必注明实际范围。

---

## 二、核心指标

> 默认走汇总表 `dm_ad.app_et_ad_callback_event_da`。**所有 N 日指标受 1.5 数据成熟度约束**（分子分母必须同一成熟范围）。
> 用户级下钻切到基础表，模板见 `sql_guidelines.md` 3.3。

| 指标 | 类型 | 业务含义 | 适用 N | 汇总表公式 | 口径要点 |
|---|---|---|---|---|---|
| **广告整体** | 基础量 | 广告新增 + 广告回流的设备总量 | - | `sum(new_udid + back_udid)` | 包含新增和回流 |
| **广告新增** | 基础量 | 广告买量带来的新增设备 | - | `sum(new_udid)` | 仅「新增」 |
| **CPI** | 比率 | 广告买量成本 | - | `sum(cost_cny) / nullif(sum(new_udid), 0)` | - |
| **ecpm** | 比率 | 广告千次曝光成本 | - | `sum(cost_cny) / nullif(sum(impression), 0) * 1000` | - |
| **CTR** | 比率 | 广告点击率 | - | `sum(click) / nullif(sum(impression), 0)` | - |
| **CVR** | 比率 | 点击转化率 | - | `sum(new_udid) / nullif(sum(click), 0)` | - |
| **CTR*CVR** | 比率 | 综合率 | - | `sum(new_udid) / nullif(sum(impression), 0)` | - |
| **人均在线时长** | 比率 | 广告新增首日人均在线时长 | - | `sum(online_min) / nullif(sum(new_udid), 0)` | - |
| **回流占新增比例** | 比率 | 回流占比 | - | `sum(back_udid) / nullif(sum(new_udid), 0)` | - |
| **N 日付费金额** | 基础量 | N 日累积净内购收入 | 1, 2, 3, 7, 14, 30, 60, 90, 180 | `sum(pay_cny_day{N})` | 「新增 + 回流」合计；已是净收入 |
| **DN 留存率** | 比率 | 新增设备在第 N 日仍活跃的比例（D2 = 次留） | 2, 3, 7, 14, 30, 60, 90, 180 | `sum(new_udid_day{N}) / nullif(sum(new_udid), 0)` | 分子分母均仅「新增」 |
| **整体内购N 日净ROI** | 比率 | N 日累积净内购 / 广告成本 | 1, 2, 3, 7, 14, 30, 60, 90, 180 | `sum(pay_cny_day{N}) / nullif(sum(cost_cny), 0)` | 分子是「新增 + 回流」净收入；分母是整体成本 |
| **M日-N日 ROI 翻倍系数** | 比率 | 长线 / 短期累积净收入的增长倍数 | M, N 业务自定义（**N > M**） | `sum(pay_cny_day{N}) / nullif(sum(pay_cny_day{M}), 0)` | M、N 都需各自成熟；常用 1日-3日、3日-7日、1日-7日 |
| **N 日付费率** | 比率 | 新增设备 N 日内付费比例 | 1, 2, 3, 7, 14, 30, 60, 90, 180 | `sum(new_udid_pay_num_day{N}) / nullif(sum(new_udid), 0)` | 分子分母均仅「新增」（与 ROI 不同） |
| **LTV** | 比率 | N 日累积人均净内购（生命周期价值） | 1, 2, 3, 7, 14, 30, 60, 90, 180 | `sum(pay_cny_day{N}) / nullif(sum(new_udid + back_udid), 0)` | **累积**口径；分子分母均含「新增 + 回流」 |
| **ARPU** | 比率 | 第 N 日**当日**人均净内购（非累积） | 1, 2, 3, 7, 14, 30, 60, 90, 180 | **—（仅基础表）** | **当日**口径，**只走基础表算**。算法：① 圈新增设备人群（`bi.animal_uid_ray_2026` 限 `report_type='ad' and new_equip='1'`）→ ② 分子 = join 付费表，限付费日期 = `install_date + (N-1)` 天，按净收入口径累加 → ③ 分母 = join 活跃表，限活跃日期 = `install_date + (N-1)` 天，`count(distinct uid)`。详见 `sql_guidelines.md` 3.3 |
| **ARPPU** | 比率 | 第 N 日**当日**付费用户人均付费（非累积） | 1, 2, 3, 7, 14, 30, 60, 90, 180 | **—（仅基础表）** | **当日**口径，**只走基础表算**。算法：① 圈新增设备人群（`bi.animal_uid_ray_2026` 限 `report_type='ad' and new_equip='1'`）→ ② 分子 = join 付费表，限付费日期 = `install_date + (N-1)` 天，按净收入口径累加 → ③ 分母 = 同条件下 `count(distinct user_id)`（当日有付费的设备数）。详见 `sql_guidelines.md` 3.3 |

---

## 三、下钻分析

异动归因 Step 2 有两类下钻：**用户级**（切到基础表）拆人群行为，**维度级**（仍在汇总表）切广告投放维度。

### 3.1 用户级下钻：人群口径与流程

**先限新设备（针对仅含「新增」口径的指标）**

用户级分析中，**付费率 / 在线时长 / ARPU / ARPPU** 等指标本身就是「新增设备」口径（汇总表分母仅 `new_udid` / `new_udid_day{N}`），基础表复算时必须先在「广告新增」（`report_type = 'ad' and new_equip = '1'`）人群内统计，否则会被老设备稀释，与汇总表 / 业务定义不一致。

**进一步拆新老用户对比（仅收入类异动）**

分析 ROI / 翻倍系数 / LTV 下跌时，**付费率 / ARPU / ARPPU** 在新设备人群内按 `user_type` 拆分新老用户（`new` 全新用户 vs `back` 回流老用户）对比，判断异动主要由哪一类驱动。

> ROI / 翻倍系数 / LTV 因 `cost_cny` 在媒体维度（或分母为新增 + 回流整体），无法按 `user_type` 拆分。

**汇总表 ↔ 基础表 口径映射**

汇总表的指标本质都从基础表聚合而来。用户级下钻按下表条件在基础表复算，结果应与汇总表一致：

| 汇总表字段 | 基础表口径（`bi.animal_uid_ray_2026` 限 `report_type = 'ad'`） |
|---|---|
| `new_udid` / `back_udid` | `new_equip = '1'` / `'0'` 的 udid 数 |
| `new_udid + back_udid` | 全部 udid 数（不限 `new_equip`） |
| `new_udid_day{N}` | 新设备人群 join 活跃表，第 N 日活跃 udid 数 |
| `new_udid_pay_num_day{N}` | 新设备人群 join 付费表，前 N 日付费 udid 数 |
| `pay_cny_day{N}` | 全部 udid（新 + 回）join 付费表，前 N 日累积净收入 |
| `cost_cny` | 基础表无；只能从汇总表取，**不可在用户级拆分** |

> 流程模板见 `sql_guidelines.md` 3.3；用户表 `udid` ≡ 付费表 `user_id` ≡ 活跃 / 闯关表 `uid`。

**不做用户级下钻的维度**：以下维度只在汇总表存在，用户表 schema 没有对应字段，**禁止尝试在基础表对其进行用户级拆分**——只能在 Step 1 汇总表层面分析：

- `account_mode`（投放模式）
- `bid_type`（出价方式）
- `data_tag_type`（投放类型）
- `native_ad`（广告形态）
- `directed_type`（定向方式）

### 3.2 维度下钻：广告投放维度

在汇总表层面按以下维度切片，定位异动发生在哪类流量结构。优先级越高越先尝试：

| 优先级 | 维度 | 字段 | 用途 |
|---|---|---|---|
| 1 | 广告平台 | `media_cn_name` | 腾讯 / 巨量等平台贡献 |
| 1 | 用户来源 | `report_type` | 广告量 vs 自然量 |
| 2 | 关键行为标签 | `data_tag` | 投放优化目标 |
| 2 | 投放模式 | `account_mode` | 手动投放 / 自投 |
| 3 | 出价方式 | `bid_type` | 不同出价策略的回收差异 |
| 3 | 投放分类 | `supplier_name` | 例 `付费_智投` |
| 3 | 优化师 | `category` | 个人 / 团队归因 |
| 4 | 广告账户 | `media_account_id` | 单账户级别问题 |
| 4 | 来源平台 | `media_ad_cn_name` | `wechatgame` / `douyin_game` 等子平台 |
| 4 | 投放端口 | `delivery_mode` | `ios` / `android+ios` |

### 3.3 维度值参考字典（用于由值反查维度）

用户提问中的具体值（如「付费智投」、「腾讯广告」、「wechatgame」）通常**不带维度名**，需先判定值属于哪个维度。下表列出已知/常见取值，便于快速反查；标注「需 SQL 实查」的维度取值多 / 持续新增，无法穷举。

| 维度字段 | 含义 | 已知 / 常见取值 |
|---|---|---|
| `media_cn_name` | 广告平台 | `腾讯广告`、`巨量引擎` |
| `report_type` | 用户来源 | `ad`（广告量）、`organic`（自然量） |
| `account_mode` | 投放模式 | `自动投放`、`手动投放` |
| `media_ad_cn_name` | 用户来源平台 | `wechatgame`（微小）、`douyin_game`（抖小）等 |
| `delivery_mode` | 投放端口 | `ios`、`android+ios` 等 |
| `media_inventory_cn_name` | 子平台 | `微信公众号与小程序` 等 |
| `supplier_name` | 投放分类 | `付费_智投` 等（需 SQL 实查完整列表） |
| `data_tag` | 关键行为标签 | `注册首日付费ROI`、`沉默唤起-首日付费ROI` 等（需 SQL 实查） |
| `data_tag_type` | 投放类型 | 需 SQL 实查 |
| `bid_type` | 出价方式 | 需 SQL 实查 |
| `directed_type` | 定向方式 | 需 SQL 实查 |
| `category` | 优化师 | 需 SQL 实查 |
| `media_account_id` | 广告账户 | 需 SQL 实查 |

> 当用户提问中的值不在已知列表里、或同一字面值可能命中多个维度（如「智投」可能匹配 `account_mode` 也可能匹配 `supplier_name`），按 `SKILL.md`「前置：维度归属判定」流程实查。

**用户常见缩写 / 简称映射**：用户提问通常用简称，需先映射到完整值再去字段里匹配：

| 用户用语 | 完整值 | 所属维度 |
|---|---|---|
| 腾讯 | `腾讯广告` | `media_cn_name` |
| 巨量 | `巨量引擎` | `media_cn_name` |
| 微小 | `wechatgame` | `media_ad_cn_name` |
| 抖小 | `douyin_game` | `media_ad_cn_name` |
| 沉默唤起 | `沉默唤起-首日付费ROI` | `data_tag` |
| 首日注册ROI | `注册首日付费ROI` | `data_tag` |

> 不在表里的缩写遇到歧义时，按「前置：维度归属判定」流程用 `like '%关键词%'` 实查匹配；新发现的稳定缩写可补充进此表。
