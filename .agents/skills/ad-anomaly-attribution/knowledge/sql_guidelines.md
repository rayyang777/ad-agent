# Animal SQL 查询规范

本文档定义 Animal 项目的 SQL 编写规范，供异动归因等任务使用。所有 SQL 必须符合 **Trino 语法**（执行引擎默认 `trino_new`）。

> **Trino 语法常见点**（与 Hive 主要差异）：
> - 日期加减：`date_add('day', n, date_col)` 或 `date_col + interval 'n' day`，不要写 Hive 风格的 `date_add(str, n)`。
> - 字符串转日期：`date(varchar)` 或 `cast(x as date)`；YYYY-MM-DD 格式可直接转。
> - 整数除法默认是整除，**比率类计算**记得 `* 1.0` 或 `cast(... as double)` 强制浮点。
> - `nullif(a, 0)` 用于规避除零；与 Hive 一致。

> **规则 ID 约定**：`C` 前缀（Correctness）= 数据正确性约束，违反会导致结果错误；`U` 前缀（Usage）= 使用边界约束。生成 SQL 时建议在 `where` 中以 `-- C1` 等形式标注引用的规则。

---

## 一、决策入口

### 1.1 选表决策树

```
用户问题
  ├─ 看趋势 / 总览（cost、ROI、留存率随时间或广告维度切片）
  │     └─→ 汇总表（第二章）
  │
  └─ 归因 / 下钻（按用户分群、关联付费 / 活跃 / 闯关明细）
        └─→ 基础表（第三章），先定人群再算指标
```

### 1.2 基础表 vs 汇总表 关键差异

| 维度 | 基础表 | 汇总表 |
|---|---|---|
| 粒度 | 用户级明细 | 广告维度预聚合 |
| 用户 ID | 有 | 无 |
| `ds` 字段含义 | 事件发生日期，纯 `YYYY-MM-DD` | 快照产出日期，**必须 = 昨天**（C1） |
| `ds` 是否分区键 | 是（与 `appid` 共同分区） | 是（**唯一**分区键，`appid` 非分区键） |
| 时间维度过滤 | 用 `ds` 范围 | 用 `install_date` 范围（**必须 substr**，C2） |
| 维度字段处理 | 按真实值过滤 | A 类 = `'all'`，B 类按真实值（C3） |
| 跨表 join | 按 `udid`/`user_id`/`uid` 关联 | **禁止**与基础表 join（U1） |
| 金额口径 | 毛收入，需 join 维表换算净收入 | **已是净收入**，禁止再换算（U2） |

---

## 二、汇总表使用规约

### 2.1 表清单

| 表名 | 用途 |
|---|---|
| `dm_ad.app_et_ad_callback_event_da` | 关键行为汇总：cost / ecpm / cpi / cvr 等前端指标，N 日留存数 / N 日净收入 / N 日付费率等活跃指标 |

### 2.2 强制约束

#### **C1 — `ds` 必须 `= '昨天'`，禁止范围**

汇总表每日产出全量快照，每个 `ds` 都是当日产出的历史累计快照。

- ✅ `ds = '2026-05-07'`（昨天）
- ❌ `ds between '2026-04-01' and '2026-05-07'` → 多份快照叠加，指标数倍虚高
- ❌ 不写 `ds` 过滤 → 全表扫描 + 全部快照叠加

时间维度的拉取请通过 `install_date` 控制（见 C2），**不要**动 `ds`。

#### **C2 — `install_date` 必须 `substr(install_date, 1, 10)`**

`install_date` 存储格式带时间后缀（`YYYY-MM-DD HH:mm:ss`，例 `2026-04-23 00:00:00`）。

- ✅ `where substr(install_date, 1, 10) between '2026-04-01' and '2026-05-07'`
- ✅ `select substr(install_date, 1, 10) as install_date`
- ✅ `group by substr(install_date, 1, 10)`
- ❌ `where install_date between '...' and '...'` → 字符串比较有边界风险，且口径不清
- ❌ `group by install_date` → 按带时间字符串分组，结果含 `00:00:00` 后缀

凡 `install_date` 出现的位置（`select` / `where` / `group by` / `order by` / `join`）**全部**必须 substr。

#### **C3 — 维度字段必须分两类处理（with cube）**

汇总表用 `with cube` 生成所有维度组合（n 个维度 → 2^n 种组合）。维度分两类，处理方式不同：

**A 类 — 进入 cube（12 个），同时存在「真实值行」和「`'all'` 汇总行」**

```
data_tag_type、data_tag、account_mode、native_ad、bid_type、directed_type、
supplier_name、category、media_account_id、media_ad_cn_name、delivery_mode、
media_inventory_cn_name
```

| 用法 | 写法 |
|---|---|
| 要分析（**一个或多个** A 类） | 取真实值 / 进 `group by`（不写 `= 'all'`，否则只剩汇总行） |
| 不分析 | **必须** `where xxx = 'all'`，把 roll-up 行筛掉 |
| 不分析也不 `= 'all'` | ❌ 真实值行和 `'all'` 行同时被求和，结果数倍重复 |

> `with cube` 生成所有维度组合，**多维度同时分析合法**——cube 里有"维度 X 真实值 + 维度 Y 真实值 + 其余 = 'all'"的行。

> ⚠️ **早期数据特殊约束**：`install_date` 早于约 90 天前的行，`native_ad` 和 `directed_type` 在底层未展开，**始终为 `'all'`**，无法按真实值下钻。如需分析这两个维度的早期 install_date 数据，会得不到结果——分析窗口需限制在近 90 天。

**B 类 — 不在 cube（2 个，作为复合主键的一部分），只有真实值行，没有 `'all'` 行**

```
media_cn_name、report_type
```

| 用法 | 写法 |
|---|---|
| 要分析 | 取真实值 / 进 `group by` |
| 按值过滤 | `report_type = 'ad'`、`media_cn_name = '腾讯广告'` |
| 不限定 | 自动 `sum()` 跨所有真实值（拿全平台合计） |
| 写 `= 'all'` | ❌ 过滤出空结果集（B 类没有 `'all'` 行） |

> 广告投放分析默认加 `report_type = 'ad'`（只看广告量）。
> 维度字段已保证非空，**无需** `coalesce` 兜底。

#### **U1 — 禁止与基础表 join**

汇总表已聚合到广告维度，不可再与 `bi.animal_uid_ray_2026`、`dw_dp.dwd_dp_payment_success_basic_di`、`dw_dp.dwd_dp_login_user_active_mid_v2_di`、`bi.animal_stage_ray_2026` 等基础表 join（粒度不匹配，结果不可解释）。需用户级下钻时，切到第三章基础表流程重写。

#### **U2 — 金额字段已是净收入，禁止再换算**

`pay_cny_day{N}` 等付费/收入字段已经过 `dm_ad.dim_et_custom_pay_da` 维表换算为净收入：

- ❌ 再 join `dim_et_custom_pay_da`
- ❌ 与基础表的 `pay_amount_cny`（毛收入）相加

### 2.3 字段说明

**表**：`dm_ad.app_et_ad_callback_event_da`

| 字段 | 类型 | 含义 | 约束 / 备注 |
|---|---|---|---|
| `ds` | string | 快照更新日期（**唯一分区键**） | **C1**：必须 `= '昨天'` |
| `install_date` | string | 用户新增日期，`YYYY-MM-DD HH:mm:ss` | **C2**：必须 `substr(install_date, 1, 10)` |
| `appid` | string | app 名称（**非**分区键） | 建议过滤，例 `'animal_h5cn_prod'` |
| `media_cn_name` | string | 广告平台，例 `腾讯广告`、`巨量引擎` | **C3 / B 类**：禁 `= 'all'` |
| `report_type` | string | 用户来源类型，`ad` / `organic` | **C3 / B 类**：禁 `= 'all'`，广告分析默认 `= 'ad'` |
| `data_tag_type` | string | 投放类型 | **C3 / A 类** |
| `data_tag` | string | H5关键行为标签 | **C3 / A 类** |
| `account_mode` | string | 投放模式 | **C3 / A 类** |
| `native_ad` | string | 广告形态 | **C3 / A 类** |
| `bid_type` | string | 出价方式 | **C3 / A 类** |
| `directed_type` | string | 定向方式 | **C3 / A 类** |
| `supplier_name` | string | 投放分类，例 `付费_智投` | **C3 / A 类** |
| `category` | string | 优化师 | **C3 / A 类** |
| `media_account_id` | string | 广告账户 | **C3 / A 类** |
| `media_ad_cn_name` | string | H5用户来源平台，例 `wechatgame`、`douyin_game` | **C3 / A 类** |
| `delivery_mode` | string | 投放端口，例 `ios`、`android+ios` | **C3 / A 类** |
| `media_inventory_cn_name` | string | 子平台，例 `微信公众号与小程序` | **C3 / A 类** |
| `new_udid` | bigint | 新增设备数 | — |
| `back_udid` | bigint | 回流设备数 | — |
| `new_udid_day{N}` | bigint | 新增设备 N 日留存数；`N ∈ {2,3,7,14,30,60,90,180}` | — |
| `pay_cny_day{N}` | double | （新增 + 回流）累积 N 日净内购收入（元）；`N ∈ {1,2,3,7,14,30,60,90,180}` | **U2**：已是净收入 |
| `new_udid_pay_num_day{N}` | bigint | 新增设备累积 N 日内购付费设备数；`N ∈ {1,2,3,7,14,30,60,90,180}` | — |
| `cost_cny` | double | 广告成本（元） | — |
| `online_min` | double | 新增设备首日在线时长（分钟） | — |
| `impression` | bigint | 媒体曝光 | — |
| `click` | bigint | 媒体点击 | — |

### 2.4 标准 SQL 模板

按广告平台查看 2026-04-01 ~ 2026-05-07 的新增和次留率趋势（昨天为 2026-05-07）：

```sql
select
    substr(install_date, 1, 10)     as install_date,                          -- C2
    media_cn_name,                                                            -- C3 / B 类
    sum(new_udid)                   as new_users,
    sum(new_udid_day2)              as day2_retained,
    sum(new_udid_day2) * 1.0 / nullif(sum(new_udid), 0) as day2_retention_rate
from dm_ad.app_et_ad_callback_event_da
where ds = '2026-05-07'                                                       -- C1：昨天
  and substr(install_date, 1, 10) between '2026-04-01' and '2026-05-07'       -- C2
  and appid = 'animal_h5cn_prod'
  and report_type             = 'ad'                                          -- C3 / B 类（广告量）
  -- C3 / A 类：不分析的维度全部 = 'all'
  and data_tag_type           = 'all'
  and data_tag                = 'all'
  and account_mode            = 'all'
  and native_ad               = 'all'
  and bid_type                = 'all'
  and directed_type           = 'all'
  and supplier_name           = 'all'
  and category                = 'all'
  and media_account_id        = 'all'
  and media_ad_cn_name        = 'all'
  and delivery_mode           = 'all'
  and media_inventory_cn_name = 'all'
group by substr(install_date, 1, 10), media_cn_name
order by substr(install_date, 1, 10), media_cn_name;
```

### 2.5 反例速查

| ❌ 错误写法 | 失败现象 | ✅ 正确写法 | 违反 |
|---|---|---|---|
| `where ds between '2026-04-01' and '2026-05-07'` | 多份快照叠加，指标数倍虚高 | `where ds = '2026-05-07'`；时间用 `install_date` | C1 |
| 不写 `ds` 过滤 | 全表扫 + 所有快照叠加 | `ds = '昨天'` | C1 |
| `where install_date between '...' and '...'` | 边界含糊，输出含 `00:00:00` 后缀 | `where substr(install_date, 1, 10) between ...` | C2 |
| `group by install_date` | 按带时间字符串分组，粒度错误 | `group by substr(install_date, 1, 10)` | C2 |
| A 类维度既不限定也不 `group by` | 真实值行 + `'all'` 行同时求和，重复数倍 | 不分析的 A 类维度全部 `= 'all'` | C3 |
| `where media_cn_name = 'all'` | 结果空（B 类无 `'all'` 行） | 按真实值过滤或进 `group by` | C3 |
| `where report_type = 'all'` | 结果空 | `= 'ad'` 或不限定 | C3 |
| 汇总表 `join` 用户表/付费表/活跃表 | 粒度不匹配，结果不可解释 | 切换基础表，按 3.1 流程重写 | U1 |
| `pay_cny_day7` 再 join `dim_et_custom_pay_da` | 净收入二次换算 | 直接用 `pay_cny_day7` | U2 |
| `pay_cny_day7 + pay_amount_cny` | 净收入 + 毛收入混合 | 选一边的口径 | U2 |

---

## 三、基础表使用规约

### 3.1 工作流：先定人群，再算指标

基础表 = 用户级明细，无任何预聚合。**必须**先在用户表圈定人群（CTE / 子查询），再去关联付费 / 活跃 / 闯关表算指标，**不要**把人群筛选条件直接写进指标计算 SQL。

```
Step 1：用户表 圈定人群（CTE）
  bi.animal_uid_ray_2026
  按 ds / appid / report_type / new_equip / user_type / media_cn_name / ... 筛选
        ↓
Step 2：明细表 算指标
  付费表 → ROI / 付费率 / 净收入
  活跃表 → 留存 / DAU
  闯关表 → 闯关率 / 难度
```

> **分区强制规则**：所有基础表的 `where` 必须**同时**限定 `ds`（建议范围条件）与 `appid`，禁止全表扫描。
> **用户 ID 对应关系**：用户表 `udid` ≡ 付费表 `user_id` ≡ 活跃 / 闯关表 `uid`。

### 3.2 表清单与字段

#### 3.2.1 用户表 — `bi.animal_uid_ray_2026`

用户维度信息，用于圈定查询人群。**分区键**：`ds`、`appid`。

| 字段 | 类型 | 含义 | 示例 / 枚举值 |
|---|---|---|---|
| `ds` | string | 新增日期（分区键，纯 `YYYY-MM-DD`） | `2026-05-04` |
| `appid` | string | app 名称（分区键） | `animal_h5cn_prod` |
| `udid` | string | 用户 ID | — |
| `report_type` | string | 用户来源 | `ad`（广告量）、`organic`（自然量） |
| `new_equip` | string | 新老设备 | `1` 新设备、`0` 老设备 |
| `user_type` | string | 新老用户 | `new`、`back` |
| `platform` | string | H5用户来源平台 | `wechatgame`、`douyin_game` |
| `media_cn_name` | string | 广告平台 | `腾讯广告`、`巨量引擎` |
| `data_tag` | string | H5关键行为标签 | `注册首日付费ROI` |
| `target_os` | string | 投放端口 | `ios`、`android+ios` |
| `media_inventory_cn_name` | string | 子平台 | `微信公众号与小程序` |
| `supplier_name` | string | 投放分类 | `付费_智投` 等 |
| `account_id` | string | 广告账户 | — |
| `optimizer_user` | string | 优化师 | — |

#### 3.2.2 付费表 — `dw_dp.dwd_dp_payment_success_basic_di`

付费明细，用于 ROI / 净收入等收入类指标。**分区键**：`ds`、`appid`。

| 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `ds` | string | 付费日期（分区键） | `2026-05-04` |
| `appid` | string | app 名称（分区键） | `animal_h5cn_prod` |
| `user_id` | string | 用户 ID（= 用户表 `udid`） | — |
| `pay_amount_cny` | double | 付费金额（**毛收入**，元） | `10` |
| `pay_type` | string | 支付来源 | — |
| `platform` | string | 支付平台 | — |

**强制规则 — 必须按"净收入"口径计算**：join `dm_ad.dim_et_custom_pay_da` 维表换算：

```sql
select
    a.ds,
    a.user_id,
    a.pay_amount_cny * coalesce(dim.rate, 1) as pay_custom    -- 净收入
from dw_dp.dwd_dp_payment_success_basic_di a
left join dm_ad.dim_et_custom_pay_da dim
    on  a.appid           = dim.appid
    and lower(a.pay_type) = lower(dim.pay_type)               -- 必须 lower
    and lower(a.platform) = lower(dim.platform)               -- 必须 lower
    and a.ds between dim.start_date and dim.stop_date         -- 维表生效区间
where a.ds >= '2026-01-01'
  and a.appid = 'animal_h5cn_prod'
```

要点：
- `pay_type` / `platform` join 时**必须** `lower()` 后再比较。
- `a.ds between dim.start_date and dim.stop_date` 是维表生效区间，**不可**省略。
- `coalesce(dim.rate, 1)` 兜底未匹配维表的情况。

#### 3.2.3 活跃表 — `dw_dp.dwd_dp_login_user_active_mid_v2_di`

活跃明细，用于留存 / DAU。**分区键**：`ds`、`appid`。

| 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `ds` | string | 活跃日期（分区键） | `2026-05-04` |
| `appid` | string | app 名称（分区键） | `animal_h5cn_prod` |
| `uid` | string | 用户 ID（= 用户表 `udid`） | — |

**强制规则**：必须按 `ds`、`appid`、`uid` 去重（如 `select distinct ...`），否则数据重复。

#### 3.2.4 闯关表 — `bi.animal_stage_ray_2026`

每日闯关汇总，用于闯关率 / 闯关难度。**分区键**：`ds`、`appid`。

| 字段 | 类型 | 含义 | 示例 |
|---|---|---|---|
| `ds` | string | 闯关日期（分区键） | `2026-05-04` |
| `appid` | string | app 名称（分区键） | `animal_h5cn_prod` |
| `uid` | string | 用户 ID（= 用户表 `udid`） | — |
| `stage_times` | int | 当日闯关总次数 | `10` |
| `stage_true_times` | int | 当日过关总次数 | `4` |

### 3.3 标准 SQL 模板

计算 2026-05-01 ~ 2026-05-04 期间，腾讯广告新增设备的次留率：

```sql
-- Step 1：圈定用户范围
with target_users as (
    select udid, ds as install_date            -- 基础表 ds 是纯 YYYY-MM-DD，无需 substr
    from bi.animal_uid_ray_2026
    where ds between '2026-05-01' and '2026-05-04'
      and appid         = 'animal_h5cn_prod'
      and report_type   = 'ad'
      and new_equip     = '1'
      and media_cn_name = '腾讯广告'
),
-- Step 2：在用户范围基础上计算指标（次日留存）
day2_active as (
    select distinct uid, ds                    -- 活跃表必须去重
    from dw_dp.dwd_dp_login_user_active_mid_v2_di
    where ds between '2026-05-02' and '2026-05-05'
      and appid = 'animal_h5cn_prod'
)
select
    u.install_date,
    count(distinct u.udid)                                       as new_users,
    count(distinct case when d.uid is not null then u.udid end)  as day2_retained,
    count(distinct case when d.uid is not null then u.udid end) * 1.0
        / count(distinct u.udid)                                 as day2_retention_rate
from target_users u
left join day2_active d
    on  u.udid = d.uid
    and date_add('day', 1, date(u.install_date)) = date(d.ds)   -- Trino 风格的日期加减
group by u.install_date
order by u.install_date;
```

> 各指标的业务定义、口径与推荐取数方式见 `metric_definitions.md`。
