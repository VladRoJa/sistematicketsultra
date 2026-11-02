-- WSO-02: review non-FK campaign references. READ ONLY, aggregated only.
\set ON_ERROR_STOP on
SET statement_timeout = '30s';

\echo '=== WSO-02 / Campaign and Contact Center logical pins ==='
WITH superseded AS (
    SELECT r.id, r.contacts_unique
    FROM public.marketing_iventas_sync_runs r
    WHERE r.status = 'COMPLETED'
      AND r.is_canonical = false
      AND EXISTS (
          SELECT 1 FROM public.marketing_iventas_sync_runs newer
          WHERE newer.period_key = r.period_key
            AND newer.date_from = r.date_from
            AND newer.date_to = r.date_to
            AND newer.status = 'COMPLETED'
            AND newer.id > r.id
      )
),
pins AS (
    SELECT r.id, r.contacts_unique,
           EXISTS (
             SELECT 1 FROM public.contact_center_contact_links cc
             JOIN public.marketing_iventas_contacts c
               ON c.id = cc.source_row_id
             WHERE cc.source_type = 'IVENTAS_CONTACT'
               AND c.sync_run_id = r.id
           ) AS cc_pinned,
           EXISTS (
             SELECT 1 FROM public.marketing_reactivation_campaigns m
             WHERE m.filters_json -> 'sources' ->> 'iventas_sync_run_id' = r.id::text
           ) AS reactivation_pinned,
           EXISTS (
             SELECT 1 FROM public.marketing_campaign_v2_campaigns v
             WHERE (
               v.audience_definition_json -> 'source_metadata' ->> 'iventas_sync_run_id' = r.id::text
               OR v.audience_definition_json -> 'sources' ->> 'iventas_sync_run_id' = r.id::text
             )
           ) AS campaign_v2_pinned
    FROM superseded r
)
SELECT COUNT(*) AS all_superseded_runs,
       COUNT(*) FILTER (WHERE cc_pinned) AS cc_protected_runs,
       COUNT(*) FILTER (WHERE reactivation_pinned) AS reactivation_protected_runs,
       COUNT(*) FILTER (WHERE campaign_v2_pinned) AS campaign_v2_protected_runs,
       COUNT(*) FILTER (
         WHERE NOT cc_pinned AND NOT reactivation_pinned AND NOT campaign_v2_pinned
       ) AS eligible_runs_after_all_pins,
       COALESCE(SUM(contacts_unique) FILTER (
         WHERE NOT cc_pinned AND NOT reactivation_pinned AND NOT campaign_v2_pinned
       ),0)::bigint AS eligible_contact_counter_sum
FROM pins;

\echo '=== WSO-02 / no data modified ==='
