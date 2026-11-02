-- WSO-02 / iVentas: readonly storage and retention-eligibility diagnostic.
-- PostgreSQL 15. No DML, no locks beyond ordinary SELECT/metadata access.
-- Does not expose names, phone numbers, tags, payloads or personal contact IDs.
-- Run: docker compose exec -T db psql -X -U postgres -d sistema_tickets \
--          -v ON_ERROR_STOP=1 < backend/scripts/ops/wso02_iventas_storage_diagnostic.sql

\set ON_ERROR_STOP on

\echo '=== WSO-02 / 1. Physical table + index + TOAST allocation ==='
WITH tables(name) AS (
    VALUES ('marketing_iventas_sync_runs'),
           ('marketing_iventas_raw_pages'),
           ('marketing_iventas_contacts'),
           ('marketing_iventas_contact_tags'),
           ('marketing_iventas_branch_failures')
)
SELECT t.name AS table_name,
       COALESCE(pg_size_pretty(pg_total_relation_size(p.oid)), 'MISSING') AS total,
       COALESCE(pg_size_pretty(pg_relation_size(p.oid)), 'MISSING') AS heap,
       COALESCE(pg_size_pretty(pg_indexes_size(p.oid)), 'MISSING') AS indexes,
       COALESCE(pg_size_pretty(
           pg_total_relation_size(p.oid) - pg_relation_size(p.oid)
           - pg_indexes_size(p.oid)), 'MISSING') AS toast_and_other,
       COALESCE(p.reltuples::bigint, 0) AS approx_rows_after_analyze
FROM tables t
LEFT JOIN pg_class p ON p.oid = to_regclass('public.' || t.name)
ORDER BY pg_total_relation_size(p.oid) DESC NULLS LAST;

\echo '=== WSO-02 / 2. Run state and retained-reader cutoffs ==='
WITH latest_completed_per_cutoff AS (
  SELECT id,
         row_number() OVER (
           PARTITION BY period_key, date_from, date_to ORDER BY id DESC
         ) AS cutoff_order
  FROM public.marketing_iventas_sync_runs
  WHERE status = 'COMPLETED'
),
classified AS (
  SELECT r.id, r.status, r.is_canonical, r.period_key,
         r.date_from, r.date_to, r.contacts_unique,
         CASE
           WHEN r.is_canonical THEN 'PROTECTED_CANONICAL'
           WHEN r.status = 'COMPLETED' AND c.cutoff_order = 1
                THEN 'PROTECTED_EXACT_CUTOFF'
           WHEN r.status = 'COMPLETED' THEN 'SUPERSEDED_COMPLETED_REVIEW'
           ELSE 'NON_COMPLETED_REVIEW'
         END AS bucket
  FROM public.marketing_iventas_sync_runs r
  LEFT JOIN latest_completed_per_cutoff c ON c.id = r.id
)
SELECT bucket, COUNT(*) AS runs,
       COALESCE(SUM(contacts_unique), 0)::bigint AS contacts_unique_counter_sum,
       MIN(date_to) AS earliest_cutoff, MAX(date_to) AS latest_cutoff
FROM classified
GROUP BY bucket
ORDER BY bucket;

\echo '=== WSO-02 / 3. Month-by-month reader coverage / duplication ==='
WITH counts AS (
  SELECT period_key, date_from, date_to,
         COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed_runs,
         COUNT(*) FILTER (WHERE is_canonical) AS canonical_runs,
         COUNT(*) AS all_runs
  FROM public.marketing_iventas_sync_runs
  GROUP BY period_key, date_from, date_to
)
SELECT period_key, COUNT(*) AS distinct_cutoffs,
       SUM(completed_runs) AS completed_runs,
       SUM(all_runs) AS all_runs,
       SUM(GREATEST(completed_runs - 1, 0)) AS repeated_completed_same_cutoff,
       SUM(canonical_runs) AS canonical_runs,
       MIN(date_to) AS first_cutoff, MAX(date_to) AS last_cutoff
FROM counts
GROUP BY period_key
ORDER BY period_key DESC;

\echo '=== WSO-02 / 4. Current/incomplete runs (never purge automatically) ==='
SELECT status, COUNT(*) AS runs,
       MIN(started_at) AS first_started_at,
       MAX(started_at) AS last_started_at
FROM public.marketing_iventas_sync_runs
WHERE status <> 'COMPLETED'
GROUP BY status ORDER BY status;

\echo '=== WSO-02 / 5. Incoming foreign keys on iVentas retention objects ==='
SELECT con.conname AS constraint_name,
       con.conrelid::regclass AS referencing_table,
       con.confrelid::regclass AS referenced_table,
       CASE con.confdeltype
         WHEN 'a' THEN 'NO ACTION'
         WHEN 'r' THEN 'RESTRICT'
         WHEN 'c' THEN 'CASCADE'
         WHEN 'n' THEN 'SET NULL'
         WHEN 'd' THEN 'SET DEFAULT'
         ELSE 'UNKNOWN'
       END AS on_delete
FROM pg_constraint con
WHERE con.contype = 'f'
  AND con.confrelid IN (
    to_regclass('public.marketing_iventas_sync_runs'),
    to_regclass('public.marketing_iventas_raw_pages'),
    to_regclass('public.marketing_iventas_contacts'),
    to_regclass('public.marketing_iventas_contact_tags')
  )
ORDER BY con.confrelid::regclass::text,
         con.conrelid::regclass::text, con.conname;

\echo '=== WSO-02 / 6. Canonical run identities by period (IDs only, no contacts) ==='
SELECT period_key, id AS canonical_run_id, date_from, date_to,
       contacts_unique AS stored_contacts_unique, status
FROM public.marketing_iventas_sync_runs
WHERE is_canonical
ORDER BY period_key DESC;

\echo '=== WSO-02 / diagnostic complete: NO deletions performed ==='
