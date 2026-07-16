-- Purpose:
--   Add truth-preferring CTM activity dedup views for the hourly activities_data
--   transfer. This fixes the 2025-06-30 stale restamp incident where replayed
--   OLD pages, including mid-call snapshots such as status='in progress' and
--   duration=NULL, received fresh load stamps and beat older completed rows.
--
-- Rollback pointers:
--   * Revert to migrations/2026-05-24-ctm-lookback-candidate.sql.
--   * Restore the BigQuery transfer config from the console backup JSON captured
--     before repointing the transfer.
--
-- Manual console step:
--   Backup transfer config 68764b5e-0000-2e52-afec-14c14ef34910 as JSON first,
--   then repoint its INSERT source from activities_combined_lookback_candidate_90d
--   to activities_combined_deduped_90d.

CREATE OR REPLACE VIEW `data-etl-to-bigquery.ctm_data.activities_combined_deduped` AS
WITH daily_raw_candidates AS (
  SELECT
    raw.*,
    TIMESTAMP(NULL) AS _candidate_loaded_at,
    0 AS _candidate_priority
  FROM `data-etl-to-bigquery.ctm_data.activities_raw_daily` AS raw

  UNION ALL

  SELECT
    lookback.* EXCEPT (
      ctm_sync_loaded_at,
      ctm_sync_run_id,
      ctm_sync_window_start,
      ctm_sync_window_end,
      ctm_sync_lookback_days
    ),
    lookback.ctm_sync_loaded_at AS _candidate_loaded_at,
    1 AS _candidate_priority
  FROM `data-etl-to-bigquery.ctm_data.activities_raw_daily_lookback` AS lookback
),
combined_candidates AS (
  SELECT
    batch.*,
    CAST(NULL AS BOOL) AS valid_lead,
    CAST(NULL AS STRING) AS valid_lead_raw,
    CAST(NULL AS STRING) AS lead_summary,
    CAST(NULL AS BOOL) AS is_spam,
    CAST(NULL AS STRING) AS is_spam_raw,
    TIMESTAMP(NULL) AS _candidate_loaded_at,
    0 AS _candidate_priority
  FROM `data-etl-to-bigquery.ctm_data.activities_raw_final_batch` AS batch

  UNION ALL

  SELECT
    id,
    sid,
    account_id,
    account_name,
    CAST(NULL AS INT64) AS batch_number,
    CAST(NULL AS STRING) AS processed_at,
    name,
    cnam,
    search,
    referrer,
    location,
    source,
    source_id,
    source_sid,
    tgid,
    likelihood,
    CAST(duration AS FLOAT64) AS duration,
    direction,
    talk_time,
    ring_time,
    hold_time,
    wait_time,
    parent_id,
    email,
    street,
    city,
    state,
    country,
    postal_code,
    called_at,
    unix_time,
    tracking_number_id,
    tracking_number_sid,
    tracking_number,
    tracking_label,
    dial_status,
    is_new_caller,
    indexed_at,
    inbound_rate_center,
    business_number,
    business_label,
    receiving_number_id,
    receiving_number_sid,
    billed_amount,
    CAST(billed_at AS TIMESTAMP) AS billed_at,
    caller_number_split,
    contact_number,
    excluded,
    redacted,
    tracking_number_format,
    business_number_format,
    caller_number_format,
    caller_number_complete,
    caller_number_bare,
    tracking_number_bare,
    caller_number,
    CAST(visitor AS STRING) AS visitor,
    call_path,
    left_talk_time,
    right_talk_time,
    transfers,
    call_status,
    status,
    spotted,
    salesforce,
    callbacks,
    emails,
    day,
    month,
    hour,
    ga,
    tag_list,
    CAST(NULL AS STRING) AS notes,
    latitude,
    longitude,
    extended_lookup_on,
    legs,
    _timestamp,
    visitor_sid,
    agent_insights,
    duration_period,
    alternative_number,
    paid,
    inputs,
    geo,
    last_location,
    audio,
    is_s3_link,
    webvisit,
    web_source,
    medium,
    visitor_ip,
    campaign,
    keyword,
    ad_match_type,
    ad_content,
    ad_slot,
    ad_slot_position,
    ad_network,
    creative_id,
    ad_group_id,
    adgroup_id,
    campaign_id,
    ad_format,
    CAST(ad_targeting_type AS STRING) AS ad_targeting_type,
    keyword_id,
    CAST(NULL AS STRING) AS ms,
    CAST(NULL AS FLOAT64) AS caller_number_blocked,
    CAST(NULL AS STRING) AS message_id,
    CAST(NULL AS STRING) AS message_body,
    CAST(NULL AS STRING) AS message_media,
    CAST(NULL AS STRING) AS sms_error_code,
    CAST(NULL AS STRING) AS sale,
    CAST(NULL AS STRING) AS agent_id,
    CAST(NULL AS STRING) AS agent,
    CAST(NULL AS STRING) AS carrier,
    CAST(NULL AS STRING) AS spam,
    CAST(NULL AS STRING) AS extended_lookup,
    CAST(NULL AS STRING) AS form,
    CAST(NULL AS STRING) AS chat_messages,
    CAST(NULL AS STRING) AS chat_status,
    CAST(NULL AS STRING) AS chat_type,
    99 AS source_batch,
    CAST(NULL AS STRING) AS transcription,
    CAST(NULL AS STRING) AS transcription_text,
    CAST(NULL AS STRING) AS summary,
    valid_lead,
    valid_lead_raw,
    lead_summary,
    is_spam,
    is_spam_raw,
    _candidate_loaded_at,
    _candidate_priority
  FROM daily_raw_candidates
)
SELECT * EXCEPT (_candidate_loaded_at, _candidate_priority)
FROM combined_candidates AS t
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY COALESCE(
    CONCAT(CAST(account_id AS STRING), '|id|', CAST(id AS STRING)),
    CONCAT(CAST(account_id AS STRING), '|sid|', sid),
    CONCAT(
      CAST(account_id AS STRING),
      '|fallback|',
      CAST(called_at AS STRING),
      '|',
      IFNULL(caller_number, '')
    )
  )
  ORDER BY
    -- In-flight statuses were drafted pre-discovery; confirm this list with
    -- SELECT status, COUNT(*) FROM ctm_data.activities_data GROUP BY 1 before the console repoint.
    CASE
      WHEN LOWER(TRIM(CAST(status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated')
        OR LOWER(TRIM(CAST(call_status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated')
      THEN 0
      ELSE 1
    END DESC,
    (NULLIF(TRIM(CAST(tracking_label AS STRING)), '') IS NOT NULL) DESC,
    SAFE_CAST(duration AS FLOAT64) DESC NULLS LAST,
    SAFE_CAST(talk_time AS FLOAT64) DESC NULLS LAST,
    SAFE_CAST(processed_at AS TIMESTAMP) DESC NULLS LAST,
    SAFE_CAST(batch_number AS INT64) DESC NULLS LAST,
    _candidate_priority DESC,
    _candidate_loaded_at DESC NULLS LAST,
    FARM_FINGERPRINT(TO_JSON_STRING(t))
) = 1;

CREATE OR REPLACE VIEW `data-etl-to-bigquery.ctm_data.activities_combined_deduped_90d` AS
WITH daily_raw_candidates AS (
  SELECT
    raw.*,
    TIMESTAMP(NULL) AS _candidate_loaded_at,
    0 AS _candidate_priority
  FROM `data-etl-to-bigquery.ctm_data.activities_raw_daily` AS raw
  WHERE (DATE(called_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) OR called_at IS NULL)

  UNION ALL

  SELECT
    lookback.* EXCEPT (
      ctm_sync_loaded_at,
      ctm_sync_run_id,
      ctm_sync_window_start,
      ctm_sync_window_end,
      ctm_sync_lookback_days
    ),
    lookback.ctm_sync_loaded_at AS _candidate_loaded_at,
    1 AS _candidate_priority
  FROM `data-etl-to-bigquery.ctm_data.activities_raw_daily_lookback` AS lookback
  WHERE (DATE(called_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) OR called_at IS NULL)
),
combined_candidates AS (
  SELECT
    batch.*,
    CAST(NULL AS BOOL) AS valid_lead,
    CAST(NULL AS STRING) AS valid_lead_raw,
    CAST(NULL AS STRING) AS lead_summary,
    CAST(NULL AS BOOL) AS is_spam,
    CAST(NULL AS STRING) AS is_spam_raw,
    TIMESTAMP(NULL) AS _candidate_loaded_at,
    0 AS _candidate_priority
  FROM `data-etl-to-bigquery.ctm_data.activities_raw_final_batch` AS batch
  WHERE (DATE(called_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY) OR called_at IS NULL)

  UNION ALL

  SELECT
    id,
    sid,
    account_id,
    account_name,
    CAST(NULL AS INT64) AS batch_number,
    CAST(NULL AS STRING) AS processed_at,
    name,
    cnam,
    search,
    referrer,
    location,
    source,
    source_id,
    source_sid,
    tgid,
    likelihood,
    CAST(duration AS FLOAT64) AS duration,
    direction,
    talk_time,
    ring_time,
    hold_time,
    wait_time,
    parent_id,
    email,
    street,
    city,
    state,
    country,
    postal_code,
    called_at,
    unix_time,
    tracking_number_id,
    tracking_number_sid,
    tracking_number,
    tracking_label,
    dial_status,
    is_new_caller,
    indexed_at,
    inbound_rate_center,
    business_number,
    business_label,
    receiving_number_id,
    receiving_number_sid,
    billed_amount,
    CAST(billed_at AS TIMESTAMP) AS billed_at,
    caller_number_split,
    contact_number,
    excluded,
    redacted,
    tracking_number_format,
    business_number_format,
    caller_number_format,
    caller_number_complete,
    caller_number_bare,
    tracking_number_bare,
    caller_number,
    CAST(visitor AS STRING) AS visitor,
    call_path,
    left_talk_time,
    right_talk_time,
    transfers,
    call_status,
    status,
    spotted,
    salesforce,
    callbacks,
    emails,
    day,
    month,
    hour,
    ga,
    tag_list,
    CAST(NULL AS STRING) AS notes,
    latitude,
    longitude,
    extended_lookup_on,
    legs,
    _timestamp,
    visitor_sid,
    agent_insights,
    duration_period,
    alternative_number,
    paid,
    inputs,
    geo,
    last_location,
    audio,
    is_s3_link,
    webvisit,
    web_source,
    medium,
    visitor_ip,
    campaign,
    keyword,
    ad_match_type,
    ad_content,
    ad_slot,
    ad_slot_position,
    ad_network,
    creative_id,
    ad_group_id,
    adgroup_id,
    campaign_id,
    ad_format,
    CAST(ad_targeting_type AS STRING) AS ad_targeting_type,
    keyword_id,
    CAST(NULL AS STRING) AS ms,
    CAST(NULL AS FLOAT64) AS caller_number_blocked,
    CAST(NULL AS STRING) AS message_id,
    CAST(NULL AS STRING) AS message_body,
    CAST(NULL AS STRING) AS message_media,
    CAST(NULL AS STRING) AS sms_error_code,
    CAST(NULL AS STRING) AS sale,
    CAST(NULL AS STRING) AS agent_id,
    CAST(NULL AS STRING) AS agent,
    CAST(NULL AS STRING) AS carrier,
    CAST(NULL AS STRING) AS spam,
    CAST(NULL AS STRING) AS extended_lookup,
    CAST(NULL AS STRING) AS form,
    CAST(NULL AS STRING) AS chat_messages,
    CAST(NULL AS STRING) AS chat_status,
    CAST(NULL AS STRING) AS chat_type,
    99 AS source_batch,
    CAST(NULL AS STRING) AS transcription,
    CAST(NULL AS STRING) AS transcription_text,
    CAST(NULL AS STRING) AS summary,
    valid_lead,
    valid_lead_raw,
    lead_summary,
    is_spam,
    is_spam_raw,
    _candidate_loaded_at,
    _candidate_priority
  FROM daily_raw_candidates
)
SELECT * EXCEPT (_candidate_loaded_at, _candidate_priority)
FROM combined_candidates AS t
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY COALESCE(
    CONCAT(CAST(account_id AS STRING), '|id|', CAST(id AS STRING)),
    CONCAT(CAST(account_id AS STRING), '|sid|', sid),
    CONCAT(
      CAST(account_id AS STRING),
      '|fallback|',
      CAST(called_at AS STRING),
      '|',
      IFNULL(caller_number, '')
    )
  )
  ORDER BY
    -- In-flight statuses were drafted pre-discovery; confirm this list with
    -- SELECT status, COUNT(*) FROM ctm_data.activities_data GROUP BY 1 before the console repoint.
    CASE
      WHEN LOWER(TRIM(CAST(status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated')
        OR LOWER(TRIM(CAST(call_status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated')
      THEN 0
      ELSE 1
    END DESC,
    (NULLIF(TRIM(CAST(tracking_label AS STRING)), '') IS NOT NULL) DESC,
    SAFE_CAST(duration AS FLOAT64) DESC NULLS LAST,
    SAFE_CAST(talk_time AS FLOAT64) DESC NULLS LAST,
    SAFE_CAST(processed_at AS TIMESTAMP) DESC NULLS LAST,
    SAFE_CAST(batch_number AS INT64) DESC NULLS LAST,
    _candidate_priority DESC,
    _candidate_loaded_at DESC NULLS LAST,
    FARM_FINGERPRINT(TO_JSON_STRING(t))
) = 1;

-- MANUAL-RUN-ONLY: one-time historical dedup for rows older than 90 days.
-- Rows with NULL called_at belong to the active hourly 90-day refresh path.
-- Before running:
--   SELECT COUNT(*) AS total_rows, COUNT(DISTINCT COALESCE(
--     CONCAT(CAST(account_id AS STRING), '|id|', CAST(id AS STRING)),
--     CONCAT(CAST(account_id AS STRING), '|sid|', sid),
--     CONCAT(CAST(account_id AS STRING), '|fallback|', CAST(called_at AS STRING), '|', IFNULL(caller_number, ''))
--   )) AS distinct_activity_keys
--   FROM `data-etl-to-bigquery.ctm_data.activities_data`
--   WHERE DATE(called_at) < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY);
--
-- CREATE OR REPLACE TABLE `data-etl-to-bigquery.ctm_data.activities_data_historical_deduped_manual` AS
-- SELECT *
-- FROM `data-etl-to-bigquery.ctm_data.activities_data` AS t
-- WHERE DATE(called_at) < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
-- QUALIFY ROW_NUMBER() OVER (
--   PARTITION BY COALESCE(
--     CONCAT(CAST(account_id AS STRING), '|id|', CAST(id AS STRING)),
--     CONCAT(CAST(account_id AS STRING), '|sid|', sid),
--     CONCAT(
--       CAST(account_id AS STRING),
--       '|fallback|',
--       CAST(called_at AS STRING),
--       '|',
--       IFNULL(caller_number, '')
--     )
--   )
--   ORDER BY
--     CASE WHEN LOWER(TRIM(CAST(status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated')
--       OR LOWER(TRIM(CAST(call_status AS STRING))) IN ('in progress','in-progress','ringing','queued','initiated')
--       THEN 0 ELSE 1 END DESC,
--     (NULLIF(TRIM(CAST(tracking_label AS STRING)), '') IS NOT NULL) DESC,
--     SAFE_CAST(duration AS FLOAT64) DESC NULLS LAST,
--     SAFE_CAST(talk_time AS FLOAT64) DESC NULLS LAST,
--     SAFE_CAST(processed_at AS TIMESTAMP) DESC NULLS LAST,
--     SAFE_CAST(batch_number AS INT64) DESC NULLS LAST,
--     0 DESC,
--     TIMESTAMP(NULL) DESC NULLS LAST,
--     FARM_FINGERPRINT(TO_JSON_STRING(t))
-- ) = 1;
--
-- After running:
--   SELECT COUNT(*) AS deduped_rows
--   FROM `data-etl-to-bigquery.ctm_data.activities_data_historical_deduped_manual`;
