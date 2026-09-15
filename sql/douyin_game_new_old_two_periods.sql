WITH attributed_raw AS (
    SELECT
        ds AS install_date,
        udid,
        user_type,
        stop_date,
        row_number() OVER (
            PARTITION BY ds, udid
            ORDER BY stop_date DESC
        ) AS rn
    FROM bi.animal_uid_ray_2026
    WHERE ds BETWEEN '2026-08-01' AND '2026-09-14'
      AND appid = 'animal_h5cn_prod'
      AND report_type = 'ad'
      AND platform = 'douyin_game'
      AND user_type IN ('new', 'back')
),
attributed AS (
    SELECT
        install_date,
        udid,
        user_type,
        CASE
            WHEN install_date <= '2026-08-28' THEN '2026-08-01~2026-08-28'
            ELSE '2026-08-29~2026-09-14'
        END AS short_period,
        coalesce(
            date_format(
                try_cast(substr(cast(stop_date AS varchar), 1, 10) AS date),
                '%Y-%m-%d'
            ),
            '9999-12-31'
        ) AS stop_date
    FROM attributed_raw
    WHERE rn = 1
),
payment_dedup AS (
    SELECT
        user_id,
        appid,
        ds,
        coalesce(
            date_format(
                try_cast(substr(cast(paytime AS varchar), 1, 10) AS date),
                '%Y-%m-%d'
            ),
            ds
        ) AS pay_date,
        pay_amount_cny,
        pay_type,
        platform
    FROM (
        SELECT
            p.*,
            row_number() OVER (
                PARTITION BY p.appid, p.order_id
                ORDER BY p.paytime
            ) AS rn
        FROM dw_dp.dwd_dp_payment_success_basic_di p
        WHERE p.ds BETWEEN '2026-08-01' AND '2026-09-14'
          AND p.appid IN (
              'animal_androidcncm_prod',
              'animal_ioscn_prod',
              'animal_ohoscn_prod',
              'animal_h5cn_prod'
          )
    ) x
    WHERE rn = 1
),
payment_net AS (
    SELECT
        p.user_id,
        p.pay_date,
        p.pay_amount_cny * coalesce(d.rate, 1) AS net_pay_cny
    FROM payment_dedup p
    LEFT JOIN dm_ad.dim_et_custom_pay_da d
      ON p.appid = d.appid
     AND lower(p.pay_type) = lower(d.pay_type)
     AND lower(p.platform) = lower(d.platform)
     AND p.pay_date BETWEEN d.start_date AND d.stop_date
),
cycle_pay AS (
    SELECT
        a.short_period,
        a.install_date,
        a.udid,
        a.user_type,
        max(CASE WHEN date_diff('day', cast(a.install_date AS date), cast(p.pay_date AS date)) BETWEEN 0 AND 0 THEN 1 ELSE 0 END) AS paid_d1,
        max(CASE WHEN date_diff('day', cast(a.install_date AS date), cast(p.pay_date AS date)) BETWEEN 0 AND 2 THEN 1 ELSE 0 END) AS paid_d3,
        max(CASE WHEN date_diff('day', cast(a.install_date AS date), cast(p.pay_date AS date)) BETWEEN 0 AND 6 THEN 1 ELSE 0 END) AS paid_d7,
        max(CASE WHEN p.pay_date IS NOT NULL THEN 1 ELSE 0 END) AS paid_tonow,
        sum(CASE WHEN date_diff('day', cast(a.install_date AS date), cast(p.pay_date AS date)) BETWEEN 0 AND 0 THEN p.net_pay_cny ELSE 0 END) AS revenue_d1,
        sum(CASE WHEN date_diff('day', cast(a.install_date AS date), cast(p.pay_date AS date)) BETWEEN 0 AND 2 THEN p.net_pay_cny ELSE 0 END) AS revenue_d3,
        sum(CASE WHEN date_diff('day', cast(a.install_date AS date), cast(p.pay_date AS date)) BETWEEN 0 AND 6 THEN p.net_pay_cny ELSE 0 END) AS revenue_d7,
        sum(coalesce(p.net_pay_cny, 0)) AS revenue_tonow
    FROM attributed a
    LEFT JOIN payment_net p
      ON a.udid = p.user_id
     AND p.pay_date >= a.install_date
     AND p.pay_date < a.stop_date
    GROUP BY a.short_period, a.install_date, a.udid, a.user_type
),
agg AS (
    SELECT
        short_period,
        user_type,
        count(*) AS devices,
        sum(paid_d1) AS paid_d1,
        sum(paid_tonow) AS paid_tonow,
        sum(revenue_d1) AS revenue_d1,
        sum(revenue_tonow) AS revenue_tonow,
        sum(CASE WHEN install_date <= '2026-09-12' THEN 1 ELSE 0 END) AS devices_d3,
        sum(CASE WHEN install_date <= '2026-09-12' THEN paid_d3 ELSE 0 END) AS paid_d3,
        sum(CASE WHEN install_date <= '2026-09-12' THEN revenue_d3 ELSE 0 END) AS revenue_d3,
        sum(CASE WHEN install_date <= '2026-09-08' THEN 1 ELSE 0 END) AS devices_d7,
        sum(CASE WHEN install_date <= '2026-09-08' THEN paid_d7 ELSE 0 END) AS paid_d7,
        sum(CASE WHEN install_date <= '2026-09-08' THEN revenue_d7 ELSE 0 END) AS revenue_d7
    FROM cycle_pay
    GROUP BY short_period, user_type
)
SELECT
    short_period,
    CASE user_type WHEN 'new' THEN '新用户' ELSE '老用户' END AS user_group,
    devices AS attributed_devices,
    round(100e0 * cast(paid_d1 AS double) / nullif(cast(devices AS double), 0e0), 4) AS pay_rate_d1_pct,
    round(100e0 * cast(paid_d3 AS double) / nullif(cast(devices_d3 AS double), 0e0), 4) AS pay_rate_d3_pct,
    round(100e0 * cast(paid_d7 AS double) / nullif(cast(devices_d7 AS double), 0e0), 4) AS pay_rate_d7_pct,
    round(100e0 * cast(paid_tonow AS double) / nullif(cast(devices AS double), 0e0), 4) AS pay_rate_tonow_pct,
    round(cast(revenue_d1 AS double) / nullif(cast(devices AS double), 0e0), 4) AS inapp_ltv_d1,
    round(cast(revenue_d3 AS double) / nullif(cast(devices_d3 AS double), 0e0), 4) AS inapp_ltv_d3,
    round(cast(revenue_d7 AS double) / nullif(cast(devices_d7 AS double), 0e0), 4) AS inapp_ltv_d7,
    round(cast(revenue_tonow AS double) / nullif(cast(devices AS double), 0e0), 4) AS inapp_ltv_tonow,
    round(
        100e0 * cast(revenue_d1 AS double)
        / nullif(sum(cast(revenue_d1 AS double)) OVER (PARTITION BY short_period), 0e0),
        4
    ) AS d1_roi_contribution_pct
FROM agg
ORDER BY short_period, user_group;
