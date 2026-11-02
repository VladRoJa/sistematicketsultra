-- WSO-02: retention preview, READ ONLY. Run after basic storage diagnostic.
-- Estimates how many physically persisted rows belong to historical buckets.
-- A 16M-contact index scan may take time. Prints aggregates only, never PII.
-- NO DELETE, no VACUUM, no changes to canonicality.
\set ON_ERROR_STOP on
SET statement_timeout = '120s';
SET lock_timeout = '3s';

\echo '=== WSO-02 / 7. Exact persisted rows by retention bucket (includes Contact Center logical references) ==='
-- This is a READ ONLY count. The 16M-row contacts index may need several seconds.
-- PROTECTED_CONTACT_CENTER guards non-FK source_row_id references.
WITH latest_completed_per_cutoff AS (
  SELECT DISTINCT ON (period_key, date_from, date_to)
         id
  FROM public.marketing_iventas_sync_runs
  WHERE status = 'COMPLETED'
  ORDER BY period_key, date_from, date_to, id DESC
),
linked_runs AS (
  SELECT c.sync_run_id, COUNT(*)::bigint AS linked_contacts
  FROM public.contact_center_contact_links cc
  JOIN public.marketing_iventas_contacts c
    ON c.id = cc.source_row_id
  WHERE cc.source_type = 'IVENTAS_CONTACT'
    AND cc.source_row_id IS NOT NULL
  GROUP BY c.sync_run_id
),
classified AS (
  SELECT r.id, r.contacts_unique,
         CASE
           WHEN r.is_canonical THEN 'PROTECTED_CANONICAL'
           WHEN COALESCE(l.linked_contacts, 0) > 0 THEN 'PROTECTED_CONTACT_CENTER'
           WHEN r.status = 'COMPLETED' AND lc.id IS NOT NULL
                THEN 'PROTECTED_EXACT_CUTOFF'
           WHEN r.status = 'COMPLETED'
                THEN 'SUPERSEDED_COMPLETED_REVIEW'
           ELSE 'NON_COMPLETED_REVIEW'
         END AS bucket,
         COALESCE(l.linked_contacts, 0) AS cc_links
  FROM public.marketing_iventas_sync_runs r
  LEFT JOIN latest_completed_per_cutoff lc ON lc.id = r.id
  LEFT JOIN linked_runs l ON l.sync_run_id = r.id
),
contacts_by_run AS MATERIALIZED (
  SELECT sync_run_id, COUNT(*)::bigint AS rows
  FROM public.marketing_iventas_contacts
  GROUP BY sync_run_id
),
tags_by_run AS MATERIALIZED (
  SELECT sync_run_id, COUNT(*)::bigint AS rows
  FROM public.marketing_iventas_contact_tags
  GROUP BY sync_run_id
),
raw_by_run AS MATERIALIZED (
  SELECT sync_run_id, COUNT(*)::bigint AS rows
  FROM public.marketing_iventas_raw_pages
  GROUP BY sync_run_id
)
SELECT b.bucket,
       COUNT(*) AS runs,
       COALESCE(SUM(b.contacts_unique), 0)::bigint AS counter_contacts,
       COALESCE(SUM(c.rows), 0)::bigint AS exact_contact_rows,
       COALESCE(SUM(t.rows), 0)::bigint AS exact_tag_rows,
       COALESCE(SUM(p.rows), 0)::bigint AS exact_raw_pages,
       COALESCE(SUM(b.cc_links), 0)::bigint AS contact_center_links
FROM classified b
LEFT JOIN contacts_by_run c ON c.sync_run_id = b.id
LEFT JOIN tags_by_run t ON t.sync_run_id = b.id
LEFT JOIN raw_by_run p ON p.sync_run_id = b.id
GROUP BY b.bucket
ORDER BY b.bucket;

\echo '=== WSO-02 / 8. Contacts index footprint (scan counts since stats reset) ==='
SELECT indexrelname AS index_name,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
       idx_scan AS scans_since_stats_reset,
       idx_tup_read AS tuples_read,
       idx_tup_fetch AS tuples_fetched
FROM pg_stat_user_indexes
WHERE relid = 'public.marketing_iventas_contacts'::regclass
ORDER BY pg_relation_size(indexrelid) DESC;

\echo '=== WSO-02 / exact count and logical reference inventory complete; NO deletions ==='
