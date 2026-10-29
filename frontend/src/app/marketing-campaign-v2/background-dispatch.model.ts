/** Issue #1129: presentation of backend-accepted batches, NEVER delivery. */
export type BackgroundDispatchStatus =
  | 'QUEUED' | 'RUNNING' | 'STOP_REQUESTED' | 'STOPPED'
  | 'COMPLETED' | 'REVIEW_REQUIRED';

export interface BackgroundDispatchJob {
  job_id: number;
  campaign_id: number;
  execution_id: number;
  status: BackgroundDispatchStatus;
  total_pending_at_start: number;
  accepted_by_provider: number;
  current_child_id: number | null;
  stop_requested: boolean;
  reason_code: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string | null;
  delivery_confirmed: false;
  may_auto_retry: false;
  may_auto_resume: false;
}

export interface BackgroundDispatchStartRequest {
  approval_id: number;
  execution_id: number;
  expected_manifest_digest: string;
  expected_pending_child_ids: number[];
  request_key: string;
  confirmation: string;
  confirmed: true;
  operator_password: string;
}

export interface BackgroundDispatchJobsResponse {
  jobs: BackgroundDispatchJob[];
  background_dispatch_available: boolean;
}

export const BACKGROUND_DISPATCH_ACTIVE: ReadonlySet<BackgroundDispatchStatus> = new Set([
  'QUEUED', 'RUNNING', 'STOP_REQUESTED',
]);

export function backgroundDispatchLabel(job: BackgroundDispatchJob): string {
  switch (job.status) {
    case 'QUEUED': return 'En cola';
    case 'RUNNING': return 'En ejecución';
    case 'STOP_REQUESTED': return 'Detención solicitada';
    case 'STOPPED': return 'Detenido';
    case 'COMPLETED': return 'Finalizado';
    case 'REVIEW_REQUIRED': return 'Requiere revisión';
  }
}

export function backgroundDispatchProgress(job: BackgroundDispatchJob): number {
  if (!Number.isFinite(job.total_pending_at_start) || job.total_pending_at_start <= 0) return 0;
  return Math.min(100, Math.max(0,
    Math.round(job.accepted_by_provider / job.total_pending_at_start * 100),
  ));
}

export function visibleBackgroundJobs(jobs: BackgroundDispatchJob[], nowMs: number): BackgroundDispatchJob[] {
  const cutoff = nowMs - 24 * 60 * 60 * 1000;
  const visible = jobs.filter(job => BACKGROUND_DISPATCH_ACTIVE.has(job.status)
    || job.status === 'REVIEW_REQUIRED'
    || ((job.status === 'STOPPED' || job.status === 'COMPLETED')
      && !!job.updated_at && Number.isFinite(Date.parse(job.updated_at))
      && Date.parse(job.updated_at) >= cutoff))
    .sort((a, b) => Number(BACKGROUND_DISPATCH_ACTIVE.has(b.status) || b.status === 'REVIEW_REQUIRED')
      - Number(BACKGROUND_DISPATCH_ACTIVE.has(a.status) || a.status === 'REVIEW_REQUIRED')
      || (Date.parse(b.updated_at || '') || 0) - (Date.parse(a.updated_at || '') || 0))
;
  // Never hide an active or unresolved mandate behind three newer jobs.
  // The dock itself is scrollable; include a small terminal history only
  // when fewer than three urgent jobs need attention.
  const urgent = visible.filter(job => BACKGROUND_DISPATCH_ACTIVE.has(job.status)
    || job.status === 'REVIEW_REQUIRED');
  const recent = visible.filter(job => !BACKGROUND_DISPATCH_ACTIVE.has(job.status)
    && job.status !== 'REVIEW_REQUIRED');
  return [...urgent, ...recent.slice(0, Math.max(0, 3 - urgent.length))].slice(0, 20);
}

/** Secure request deduplication id; never used as a credential. Fail closed without WebCrypto. */
export function newBackgroundRequestKey(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}
