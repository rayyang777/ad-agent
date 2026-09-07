---
name: ad-dau
description: 当用户分析广告投放（买量）对开心消消乐（Animal）DAU 的影响时使用，覆盖 H5整体、抖小、微小、安卓、鸿蒙、iOS，支持指定端口与“过去两周”“过去一个月”等时间窗口，并生成交互 HTML 报告后上传获取链接。
---

# Animal 广告买量对 DAU 影响分析

本 Skill 负责端口与日期解析、业务分析、指标计算、洞察撰写和报告数据组织。项目级 `ad_agent` MCP 提供查询、渲染、上传三类原子接口：

- `ad_query`：执行一条只读 SQL，支持指定查询引擎，返回 CSV。
- `ad_render_report`：使用本 Skill 的固定模板和 Schema，把结构化报告数据渲染为 HTML，不上传。
- `ad_upload_report`：上传已经渲染的 HTML 文件，返回 URL。

全流程自主执行，不因端口选择、日期范围、SQL、报告格式或上传向用户征询确认。用户未明示时按本文默认值继续；出现未覆盖的二选一或多选时采用最常规、最保守的方案，并在完成后说明采用的默认值。只有遇到 SQL 鉴权失败、上传失败等无法继续的错误时才报告。

直接根据 `ad_query` 返回的 CSV 完成计算与洞察，组装紧凑的 `report_data` 对象。不得临时生成 HTML、CSS、JavaScript 或报告生成脚本；依次调用渲染与上传工具。

---

## 一、确定端口与日期范围

### 1.1 端口映射与顺序

每个 `section` 必须渲染为一个独立模块，严格 1:1。模块顺序等于用户提及端口的顺序；用户未指定端口时使用固定顺序 `H5,douyin_game,wechatgame,android,harmony,ios`。展开完成后按 section 去重，重复项只保留第一次出现的位置。

H5 作为独立端口出现时，在用户提到 H5 的位置按 `H5 → douyin_game → wechatgame` 展开。例如“安卓+H5”对应 `android,H5,douyin_game,wechatgame`。

| 用户措辞 | 加入的 section | 标题标签 |
|---|---|---|
| H5 独立端口，如“H5”“H5+X”“H5 报告” | `H5`,`douyin_game`,`wechatgame` | `H5` |
| H5整体（按模块名明确提出） | `H5` | `H5整体` |
| 抖小，或“H5的/下抖小” | `douyin_game` | `抖小` |
| 微小，或“H5的/下微小” | `wechatgame` | `微小` |
| 安卓 / 鸿蒙 / iOS | `android` / `harmony` / `ios` | `安卓` / `鸿蒙` / `iOS` |
| 只说 Animal / 开心消消乐，未指定端口 | 全 6 个 | `全端` |

判断“H5”是独立端口还是限定语：

- “H5”“H5+安卓”“H5 报告”均为独立端口，展开 3 个模块，标题标签为 `H5`。
- “H5的抖小”“H5下的微小”中 H5 是限定语，只取后面的子端口。
- “H5的抖小+安卓”对应 `douyin_game,android`。
- `section='H5'` 是源表预聚合的 H5 整体指标，与抖小、微小平行独立，绝不能把三者相加得到 H5。

示例：

| 用户消息 | section 顺序 | 标题后缀 |
|---|---|---|
| “Animal 广告对 DAU 影响” | `H5,douyin_game,wechatgame,android,harmony,ios` | `全端` |
| “H5 的广告” | `H5,douyin_game,wechatgame` | `H5` |
| “H5整体” | `H5` | `H5整体` |
| “H5的抖小” | `douyin_game` | `抖小` |
| “H5下的抖小和微小” | `douyin_game,wechatgame` | `抖小/微小` |
| “H5+安卓” | `H5,douyin_game,wechatgame,android` | `H5/安卓` |
| “安卓+H5” | `android,H5,douyin_game,wechatgame` | `安卓/H5` |
| “H5的抖小+安卓” | `douyin_game,android` | `抖小/安卓` |
| “鸿蒙,安卓,iOS,微小和抖小” | `harmony,android,ios,wechatgame,douyin_game` | `鸿蒙/安卓/iOS/微小/抖小` |

### 1.2 日期范围

查询窗口为 `[START_DATE, END_DATE]` 闭区间，共 N 天：

- `TODAY` 为今天。
- `END_DATE = YESTERDAY = TODAY - 1`，当日数据未完整，固定截止昨天。
- `START_DATE = END_DATE - (N - 1)`，注意不是减 N。

| 用户措辞 | N |
|---|---:|
| 缺省 / 过去一个月 / 过去 30 或 31 天 | 31 |
| 过去两周 / 过去 14 天 | 14 |
| 过去一周 / 过去 7 天 | 7 |
| 过去 X 天 | X |
| 过去 X 周 | X × 7 |
| 过去 / 近 X 个月 | X × 31 |
| 过去 / 近半年 / 过去 6 个月 | 180 |
| 过去 / 近一年 / 过去 12 个月 | 365 |

例：`TODAY=2026-05-14`，用户说“过去两周”，则 `END_DATE=2026-05-13`、`START_DATE=2026-04-30`，首尾共 14 天。

### 1.3 标题与文件名

- 报告标题：`Animal 广告买量对 DAU 影响分析 - <后缀>`。后缀按标题标签用 `/` 拼接；全端直接写 `全端`。
- 上传文件名由 `ad_upload_report` 根据报告标题和日期自动生成：`<REPORT_TITLE> - <TODAY>.html`。标题中的 `/` 自动替换为 `、`，不要传 `upload_name` 覆盖。
- 调用 `ad_render_report` 时，`local_name` 使用 `ad-dau-report.html`。本地路径由 MCP 管理，不自行创建缓存目录。

---

## 二、查询数据

通过 `ad_query` 执行以下 SQL。按确定的 section 替换 `<SECTIONS>`，字符串必须正确加引号：

```sql
select *
from bi.animal_cost_dau_analyze_di
where ds >= '<START_DATE>' and ds <= '<END_DATE>'
  and section in (<SECTIONS>)
order by ds, section, u_type
```

表字段：

| 列名 | 类型 | 说明 |
|---|---|---|
| `u_type` | string | `ad` / `organic` |
| `dau` | double | 活跃 DAU |
| `total_revenue` | double | 当日净收入（元） |
| `arpu` | double | 当日活跃净 ARPU |
| `new_users` | bigint | 广告新增或自然新增 |
| `cost_cny` | double | 当日广告投放成本；仅广告行有值，自然行固定为 0 |
| `ds` | string | `YYYY-MM-DD` |
| `section` | string | `H5` / `douyin_game` / `wechatgame` / `android` / `harmony` / `ios` |

查询与解析规则：

- 默认使用 `trino_new`，`wait=300`，`fetch_rows=1000`，`max_chars=200000`，`output_name=ad-dau.csv`。
- 仅在 `trino_new` 不适合复杂 SQL 或执行失败时改用 `tez_new`，并确保 SQL 写法符合对应引擎语法。
- CSV 必须按 header 列名解析，不能依赖列顺序。
- `NULL`、空字符串、不可解析数值和缺失的 ad / organic 行按 0 处理。
- 如果返回 `truncated=true`，禁止根据不完整 CSV 分析。先把 `max_chars` 提到 200000；仍不完整时按 section 或日期拆成多条等价查询，分别解析后再合并。
- 某个 section 完全无数据时，在报告模块中明确写“查询范围内无有效数据”，不得借用其他 section 数据补齐。

---

## 三、逐端口计算与分析

### 3.1 数据隔离与基础序列

每个 section 只使用自身行计算，禁止跨 section 聚合。对每个日期分别读取 `u_type='ad'` 和 `u_type='organic'`，构建：

- `ad_dau`、`organic_dau`，以及 `total_dau = ad_dau + organic_dau`。
- `ad_share = ad_dau / total_dau × 100%`；总 DAU 为 0 时占比记 0。
- `ad_arpu`、`organic_arpu`，直接使用源字段 `arpu`。
- `ad_new`、`organic_new`，使用源字段 `new_users`。
- `ad_cost`，只使用广告行 `cost_cny`。

计算过程使用原始浮点值；前后半段均值在计算素材中保留 4 位，百分比变化保留 2 位。最终展示严格按以下精度：

- KPI：总 DAU 四舍五入为整数并加千分位；广告占比保留 1 位并加 `%`；两项 ARPU 保留 2 位。
- 洞察卡与趋势段落：人数、新增、日均消耗和累计消耗四舍五入为整数并加千分位；ARPU 保留 2 位；占比均值、占比差值和百分比变化保留 2 位。
- 变化百分点统一使用 `pp`，百分比变化统一使用 `%`；显示结果为 `-0.00` 时改为 `0.00`。

### 3.2 实际数据范围

所有卡片、段落和图表必须按各自指标组合计算实际数据范围，不得用请求窗口冒充有效范围：

1. 先取该 section 在 CSV 中实际出现过的 `ds`，去重后升序排列为日期点序列；查询窗口内没有返回记录的自然日不得自动补 0。
2. 在某个指标组合中，只要任一指标在某个日期点非空且非 0，该日期点就有效。
3. 从最早有效日期点到最晚有效日期点的索引区间为该组合的 `real_range`；区间内部已有的 0 值日期点保留。实际天数等于该索引区间包含的日期点数量，不按首尾自然日之差计算。
4. 若实际范围与请求窗口不同，卡片正文、趋势段落和相关图表必须展示实际起止日期。
5. 一个模块内不同指标组合可以有不同实际范围，不得强行对齐。

| 内容 | 用于确定实际范围的指标 |
|---|---|
| 最新日概况 / 总 DAU 段落 / 图 1 | `ad_dau`,`organic_dau` |
| 广告占比卡片 / 图 2 | `ad_share` |
| 净 ARPU 卡片 | `ad_arpu`,`organic_arpu` |
| 新增与消耗卡片 / 新增消耗段落 | `ad_new`,`organic_new`,`ad_cost` |
| 广告与自然 DAU、占比段落 | `ad_dau`,`organic_dau`,`ad_share` |
| 图 3 | `ad_new`,`organic_new` |
| 图 4 | `total_dau`,`ad_cost` |
| 图 5 | `ad_share`,`ad_cost` |

### 3.3 两套比较窗口

广告占比卡片使用“近 N 个日期点 vs 前 N 个日期点”，报告文案仍显示“近 N 日 vs 前 N 日”：

- 实际天数至少 14 天时，N=7。
- 实际天数为 4-13 天时，`N=floor(实际天数/2)`。
- 实际天数少于 4 天时，只给当前范围均值，不做前后比较。
- 近 N 日从 `real_end` 向前取 N 个日期点，前 N 日取其紧邻的前 N 个日期点。展示两个窗口的首尾日期、两个均值和差值，差值单位为 `pp`。

趋势段落使用“前半段 vs 后半段”：

- 每段按自己指标组合的 `real_range` 日期点序列切分。
- 偶数天均分；奇数天后半段多一天。
- 比较前后半段日均。百分比变化为 `(后半段均值 - 前半段均值) / 前半段均值 × 100%`。
- 前半段均值为 0 时不得伪造百分比，改为描述绝对变化；不足 2 天时只描述当前水平。

### 3.4 固定四张洞察卡

每个模块必须恰好 4 张，按以下顺序和色彩语义呈现：

| # | 标题 | 色彩 | 时间口径 | 必须包含 |
|---|---|---|---|---|
| 1 | DAU 概况 | 蓝 | 只要昨日在该 section 中存在任一 CSV 行，即使指标值全为 0，也使用昨日；昨日没有任何行时回退到 DAU 实际范围最后一个日期点；若 DAU 全程无有效值，则回退到该 section 最后一个返回日期点。发生回退必须明确标注 | 总 DAU、广告 DAU、自然 DAU、广告占比 |
| 2 | 广告占比趋势 | 紫 | 近 N 日 vs 前 N 日 | 两段均值、实际窗口、差值 pp；不足 4 天仅当前均值 |
| 3 | 净 ARPU 对比 | 琥珀 | ARPU 实际范围最后最多 7 天 | 广告净 ARPU 与自然净 ARPU 均值、实际窗口 |
| 4 | 新增与消耗 | 绿 | 三项指标并集的完整实际范围 | 日均广告新增、日均自然新增、日均广告消耗、累计消耗、实际范围 |

### 3.5 固定趋势标签与段落

每个模块从以下 11 个标签中选择最符合事实的一项。不得为了套标签歪曲数据：

| 标签 | 适用场景 |
|---|---|
| `双轮驱动·协同增长` | 总 DAU↑ + 广告 DAU↑ + 自然 DAU↑ |
| `逆向对冲·有效` | 自然 DAU↓ + 广告 DAU↑，总 DAU↑ |
| `逆向对冲·待改善` | 自然 DAU↓ + 广告 DAU↑，总 DAU仍↓ |
| `买量拉动·依赖上升` | 总 DAU↑ + 广告 DAU↑，自然 DAU持平或下降且广告占比明显抬升 |
| `买量低效·DAU滞涨` | 广告 DAU大幅上升但总 DAU持平或仅微涨，自然 DAU基本持平 |
| `DAU下滑·投放未跟` | 总 DAU↓，广告 DAU基本持平 |
| `投放收缩·DAU承压` | 广告 DAU↓ + 总 DAU↓ |
| `自然回暖·买量减弱` | 自然 DAU↑ + 广告 DAU↓，总 DAU稳定或上升 |
| `自然驱动·投放稳定` | 自然 DAU↑ + 广告 DAU基本持平 + 总 DAU↑ |
| `全面下行·需提振` | 总 DAU、广告 DAU、自然 DAU均下降 |
| `趋势平稳` | 三者均无明显方向或幅度，通常环比绝对值小于 5% |

趋势分析必须恰好 4 段，段首保留 `1.` 到 `4.`，不能合并或省略。第 1-3 段以 `N. (YYYY-MM-DD~YYYY-MM-DD)` 开头，括号中填写该段指标组合的实际范围：

1. 总 DAU：基于总 DAU 实际范围，写前后半段日均、方向和幅度。
2. 广告与自然 DAU、广告占比：写三者前后半段变化；占比变化用 pp。
3. 新增与消耗：写广告新增、自然新增、广告消耗的前后半段方向和幅度。
4. 综合判断：自然量下降时判断广告新增/消耗是否反向对冲；否则说明趋势是否一致。各项可引用自己的实际范围，不得强行对齐。

只能陈述数据直接支持的变化、同步或不同步关系。推测原因必须以 `[推测]` 开头，不得把相关性写成因果。每个模块最后提供一条具体投放建议，建议正文不得超过 50 个汉字（含标点，优先控制在 40 字内）；页面展示时由报告加粗“投放建议”前缀，建议正文不重复该前缀。

---

## 四、生成结构化报告

将完整 CSV 与上述计算整理为 `report_data`，直接作为 `ad_render_report` 的对象参数，不自行落盘。调用参数固定为：

```text
template_id = "ad-dau-v1"
local_name = "ad-dau-report.html"
report_data = <下述结构化对象>
```

模板、固定样式、图表初始化和 tooltip 已固化在 `assets/report_template.html`，输入约束由 `assets/report_schema.json` 强制校验。`report_data` 只承载报告元信息、计算结果、图表逐日数据和业务洞察，不包含 HTML 标签或 ECharts 配置。

### 4.0 report_data 结构

```json
{
  "metadata": {
    "title": "Animal 广告买量对 DAU 影响分析 - 抖小",
    "data_start": "2026-08-01",
    "data_end": "2026-08-31",
    "generated_date": "2026-09-01"
  },
  "caliber": [
    {"ports": "抖小", "rule": "用户历史有广告量来源记录（report_type='ad'）；自然量为排除广告量"},
    {"ports": "全部端口", "rule": "总 DAU = 广告 DAU + 自然 DAU；广告占比 = 广告 DAU / 总 DAU；广告消耗为媒体折后成本"}
  ],
  "sections": [
    {
      "id": "douyin_game",
      "label": "抖小",
      "nav_level": 0,
      "status": "ok",
      "kpi_date": "2026-08-31",
      "kpi_fallback_note": "",
      "kpis": [
        {"title": "总 DAU", "value": "100,000", "detail": "广告 40,000 / 自然 60,000"},
        {"title": "广告占比", "value": "40.0%", "detail": "广告 DAU / 总 DAU"},
        {"title": "广告净 ARPU", "value": "0.30", "detail": "元 / 活跃用户"},
        {"title": "自然净 ARPU", "value": "0.20", "detail": "元 / 活跃用户"}
      ],
      "daily": [
        {"date": "2026-08-31", "ad_dau": 40000, "organic_dau": 60000, "total_dau": 100000, "ad_share": 40.0, "ad_arpu": 0.3, "organic_arpu": 0.2, "ad_new": 8000, "organic_new": 12000, "ad_cost": 20000}
      ],
      "chart_ranges": {
        "dau": {"start": "2026-08-31", "end": "2026-08-31"},
        "share": {"start": "2026-08-31", "end": "2026-08-31"},
        "new_users": {"start": "2026-08-31", "end": "2026-08-31"},
        "dau_cost": {"start": "2026-08-31", "end": "2026-08-31"},
        "share_cost": {"start": "2026-08-31", "end": "2026-08-31"}
      },
      "cards": [
        {"title": "DAU 概况", "body": "..."},
        {"title": "广告占比趋势", "body": "..."},
        {"title": "净 ARPU 对比", "body": "..."},
        {"title": "新增与消耗", "body": "..."}
      ],
      "trend": {
        "tag": "趋势平稳",
        "paragraphs": ["(YYYY-MM-DD~YYYY-MM-DD) ...", "(YYYY-MM-DD~YYYY-MM-DD) ...", "(YYYY-MM-DD~YYYY-MM-DD) ...", "综合判断：..."],
        "recommendation": "保持预算稳定并持续观察新增效率。"
      }
    }
  ]
}
```

- `sections` 顺序必须等于第一章确定的顺序；`id` 不得重复。
- 同时包含 H5、抖小、微小时，抖小和微小的 `nav_level=1`，其他情况为 `0`。
- `daily` 按日期升序，每个日期一行；必须使用原始数值，不要预格式化图表数据。
- `chart_ranges` 分别填写 3.2 节定义的五组实际范围；模板据此裁剪图表两端。
- `kpis` 与 `cards` 必须保持示例中的固定标题和顺序。模板自动添加 KPI 日期、趋势段落编号与“投放建议”前缀。
- `trend.paragraphs` 不包含 `1.` 至 `4.` 编号；前三段从 `(YYYY-MM-DD~YYYY-MM-DD)` 开始。
- 无数据模块只传 `id`、`label`、`nav_level`、`status="empty"`、`empty_message="查询范围内无有效数据"`。

### 4.1 页面结构

报告从上到下必须包含：

1. 顶部标题与元信息：报告标题、数据时间范围、报告产出时间、产出用户。数据时间范围固定取完整 CSV 中所有 section 的最小 `ds` 和最大 `ds`；CSV 为空时起止均写 `YESTERDAY`。报告产出时间固定为 `TODAY`，格式 `YYYY-MM-DD`。`metadata.user` 不由 Skill 填写；`ad_render_report` 会在校验前从项目 `config.json` 的 `username` 自动注入，缺失或为空时直接返回配置错误。
2. 独立“口径说明”栏。
3. 按选定顺序排列的 section 模块；模块之间有清晰分隔。
4. 每个模块依次包含：模块标题、4 个最新日 KPI、5 张图、4 张洞察卡、趋势标签、恰好 4 段趋势分析、1 条投放建议。

多 section 报告必须增加左侧粘性目录和滚动高亮，目录顺序与模块顺序一致；同时包含 H5、抖小、微小时，抖小和微小在目录中作为 H5 后的次级视觉项，但数据模块仍彼此独立。单 section 报告不显示目录。

最新日 KPI 固定为：总 DAU、广告占比、广告净 ARPU、自然净 ARPU。标题必须带实际取数月日；昨日缺失而回退时，4 个 KPI 和 DAU 概况卡均使用并标明同一个回退日期。

### 4.2 五张交互图

固定加载 `<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>`，数据和初始化 JavaScript 直接嵌入 HTML。每张图都要有中文标题、图例、坐标轴、悬浮提示和“i”口径提示；数字轴绝对值达到 1 亿时除以 1 亿、最多保留 2 位并加“亿”，达到 1 万时除以 1 万、最多保留 2 位并加“万”，其余显示原值；悬浮提示显示完整千分位数值。图表只裁掉实际范围两端的全空/全 0 日期点，内部 0 不裁。

所有图表使用固定公共参数：`legend.top=8`、`legend.left='center'`、`grid={top:40,left:10,right:20,bottom:30,containLabel:true}`、`tooltip.trigger='axis'`。所有折线设置 `smooth=true`、`showSymbol=false`、`lineStyle.width=2.5`；除占比轴外的数值轴设置 `min=0`。

Tooltip 与坐标轴格式必须固定：

- 普通数值 tooltip：空值返回空字符串；其他值使用 `Number(value).toLocaleString('en-US')`，显示完整千分位数值，不添加“万/亿”缩写，也不强制补齐小数位。
- 百分比 tooltip：空值返回空字符串；其他值使用 `Number(value).toFixed(1) + '%'`，固定保留 1 位小数。
- 普通数值坐标轴：绝对值达到 1 亿时显示“数值÷1亿”，最多 2 位小数并加“亿”；达到 1 万时显示“数值÷1万”，最多 2 位小数并加“万”；不足 1 万显示原值。由数值转换去掉末尾无意义的 0，例如 `1.20万` 显示为 `1.2万`。
- 百分比坐标轴：使用 `{value}%`，刻度值不额外固定小数位。
- 图 1 的广告 DAU、自然 DAU均使用普通数值 tooltip；图 2 的广告占比使用百分比 tooltip；图 3 的广告新增、自然新增均使用普通数值 tooltip；图 4 的总 DAU、广告消耗均使用普通数值 tooltip；图 5 必须逐系列设置，广告占比使用百分比 tooltip，广告消耗使用普通数值 tooltip。

1. `<端口> DAU 趋势`：广告 DAU + 自然 DAU。默认堆叠柱状图，并提供“柱状图 / 趋势图”切换；趋势图使用双 Y 轴。
2. `<端口> 广告用户占 DAU 比例`：广告占比折线图，百分比 Y 轴和浅色面积。
3. `<端口> 每日新增`：广告新增 + 自然新增并列柱状图。
4. `<端口> 总DAU VS 广告消耗`：总 DAU 柱状图 + 广告消耗折线图，双 Y 轴。
5. `<端口> 广告消耗 VS 广告占比`：广告占比 + 广告消耗双折线图，双 Y 轴。

图 1 为通栏主图，固定高度 340px；图 2/3 与图 4/5 分别两列排布，每张固定高度 300px。窄屏时自动改为单列，目录收窄或移到顶部，任何文字、图例、按钮不得重叠或溢出。

### 4.3 视觉与口径

- 使用以下固定色板，不得自行替换色相、交换指标颜色或生成新的主题色。除顶部标题和 4 个 KPI 使用指定渐变外，其余大面积区域保持浅色，禁止使用深蓝、深紫或深黑背景。

| 页面元素 | 固定颜色 |
|---|---|
| 页面背景 | `#F2F6FF` |
| 主内容、图表、目录背景 | `#FFFFFF` |
| 主文字、模块标题 | `#1A2B4A` |
| 正文、洞察正文 | `#243558` |
| 图表标题 | `#374151` |
| 次要文字 | `#475569`；更弱层级使用 `#64748B` |
| 通用浅色模块背景 | `#F8FAFF` |
| 通用边框、模块分隔浅色 | `#E2EAFF` |
| 顶部标题背景 | `linear-gradient(120deg,#1557E0 0%,#3B82F6 55%,#7AB8FF 100%)`，文字 `#FFFFFF` |
| 模块标题左边线 | `#3B82F6` |
| 口径说明栏 | 背景 `#FFF8E1`，左边线 `#F59E0B`，文字 `#7C4A03` |
| “口径说明”标签 | 背景 `#FCD34D`，文字 `#7C2D12` |
| 图表切换控件 | 背景 `#F1F5FB`；选中项背景 `#FFFFFF`、文字 `#1D4ED8` |
| 信息提示图标 | 背景 `#E2EAFF`，文字 `#1D4ED8`；悬停时背景 `#1D4ED8`、文字 `#FFFFFF` |

4 个 KPI 必须使用以下渐变，文字均为 `#FFFFFF`：

| KPI | 固定背景 |
|---|---|
| 总 DAU | `linear-gradient(135deg,#1E60F0,#4F9DFF)` |
| 广告占比 | `linear-gradient(135deg,#7C3AED,#A78BFA)` |
| 广告净 ARPU | `linear-gradient(135deg,#D97706,#FCD34D)` |
| 自然净 ARPU | `linear-gradient(135deg,#059669,#34D399)` |

4 张洞察卡使用浅色标签，卡片自身背景统一为 `#F8FAFF`、边框为 `#E2EAFF`：

| 洞察卡 | 标签背景 | 标签文字 |
|---|---|---|
| DAU 概况 | `#DBEAFE` | `#1D4ED8` |
| 广告占比趋势 | `#EDE9FE` | `#6D28D9` |
| 净 ARPU 对比 | `#FEF3C7` | `#B45309` |
| 新增与消耗 | `#D1FAE5` | `#065F46` |

图表系列颜色必须固定：

| 数据系列 | 固定颜色 |
|---|---|
| 广告 DAU 趋势线 | `#1D4ED8` |
| 自然 DAU 趋势线 | `#059669` |
| 广告 DAU / 广告新增柱 | `#3B82F6` |
| 自然 DAU / 自然新增柱 | `#34D399` |
| 广告占比线 | `#D97706`，面积填充 `rgba(217,119,6,0.08)` |
| 总 DAU 柱 | `#8B5CF6`，透明度 `0.75` |
| 广告消耗线 | `#F43F5E` |

- 字体栈固定为 `-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif`。
- 无目录时页面外边距为 24px；主内容最大宽度 1320px、白色背景、圆角 16px、阴影 `0 2px 12px rgba(30,60,120,.07)`。顶部标题区内边距为 `28px 32px`，主标题字号 24px，元信息字号 13px。
- 模块左右内边距 32px；模块标题字号 18px、左边线 5px、上外边距 24px、下外边距 16px；模块分隔线高度 3px。
- 4 个 KPI 使用等宽四列，间距 14px，内边距 `18px 20px`，圆角 14px；KPI 标题字号 13px，数值字号 30px、字重 900。
- 4 张洞察卡使用 2×2 网格，间距 12px，内边距 `14px 16px`，圆角 12px；趋势分析块内边距 `16px 18px`，圆角 12px。
- 多 section 时目录桌面宽度和最小宽度均为 150px，右边框 2px；主内容区内边距 24px。窄屏响应式规则可以调整列数、目录位置和内边距，但不得修改固定色板、内容顺序或隐藏内容。
- 图表、卡片和趋势结论必须引用同一 section、同一指标口径和相同实际数据范围，不能出现图文不一致。
- 图表“i”提示必须写清公式或来源：总 DAU = 广告 DAU + 自然 DAU；广告占比 = 广告 DAU / 总 DAU；广告消耗为媒体折后成本。
- 广告用户认定口径必须显式展示：安卓为“当日为 he 包活跃用户”；H5整体、抖小、微小、鸿蒙、iOS 为“用户历史有广告量来源记录（report_type='ad'）”；自然量均为“排除广告量”。混合端口时按适用端口分组列出口径。
- 将报告标题、用户名和其他来自对话或数据的文本写入 HTML 前进行 HTML 转义；只有报告自身明确生成的 `<br>`、`<strong>` 等标记可以作为 HTML。图表数据必须使用 JSON 序列化后嵌入，不能手工拼接 JavaScript 字符串。

提交 `report_data` 前只检查业务数据与结构，不检查或修改模板代码：

1. 模块集合严格等于去重后的 section 列表，没有缺失或额外模块，顺序一致；每个模块只使用自身数据。
2. 每个有数据模块包含 4 个 KPI、完整逐日数据、5 组实际范围、4 张固定洞察卡、1 个合法趋势标签、4 段趋势和 1 条不超过 50 字且正文不重复“投放建议”的建议。
3. 昨日回退日期、卡片窗口和第 1-3 段实际范围符合本文规则；实际范围不同于请求窗口时，正文同时出现起止端点。
4. `daily` 不包含 `NaN`、`Infinity`，`total_dau` 与 `ad_share` 和基础序列一致。

`ad_render_report` 会校验 Schema。若返回校验错误，只修正错误指出的 `report_data` 字段后重试；不得改写模板、生成临时脚本或改用完整 HTML 上传。

---

## 五、上传报告

必须严格分两步：

1. 调用 `ad_render_report`，传入 `template_id=ad-dau-v1`、完整 `report_data`、`local_name=ad-dau-report.html`，保存返回的 `report_file`。
2. 调用 `ad_upload_report`，只传入 `report_file`、`title=<REPORT_TITLE>`、`today=<TODAY>`，保存返回的 URL；不要传 `upload_name`，上传文件名固定由工具生成。

渲染失败时说明 Schema 校验错误；上传失败时说明失败发生在上传阶段并返回 `report_file`。成功时向用户返回报告标题、实际查询范围、采用的端口/默认值和飞书 URL。
