import {
  CampaignV2GovernedExecutionReviewReady,
  CampaignV2GovernedMonitor,
} from './marketing-campaign-v2.models';

/**
 * Prepare an explicitly approved, finite sequence of distinct READY children.
 * Does not send messages. The caller must re-read the authoritative monitor
 * and run the existing backend step-up gate for EACH child.
 */
export function pendingGovernedBatchIds(
  monitor: CampaignV2GovernedMonitor | null,
  review: CampaignV2GovernedExecutionReviewReady | null,
): number[] {
  const continuing = monitor?.status === 'CONTINUATION_REVIEW_REQUIRED';
  if (!monitor || !review?.execution ||
      !monitor.approval ||
      (monitor.approval.expired && !continuing) ||
      (!monitor.quota.all_current && !continuing) ||
      monitor.execution?.status !== 'AUTHORIZED' ||
      review.execution.status !== 'AUTHORIZED' ||
      review.manifest_digest !== monitor.approval.manifest_digest ||
      monitor.children_count !== monitor.children.length ||
      monitor.children.some(child => child.needs_manual_review)) {
    return [];
  }

  const childrenByBranch = new Map(monitor.children.map(child => [child.sucursal_canon, child]));
  if (childrenByBranch.size !== monitor.children.length ||
      new Set(review.manifest.batches.map(batch => batch.sucursal_canon)).size !==
      review.manifest.batches.length ||
      review.manifest.batches.length !== monitor.children.length) {
    return [];
  }

  const ordered = review.manifest.batches.map(batch => childrenByBranch.get(batch.sucursal_canon));
  if (ordered.some(child => !child)) { return []; }
  for (let index = 0; index < ordered.length; index += 1) {
    const batch = review.manifest.batches[index];
    const child = ordered[index]!;
    if (batch.planned_status === 'HELD' && child.status !== 'HELD') { return []; }
    if (batch.planned_status === 'READY' && !['READY', 'SUBMITTED'].includes(child.status)) {
      return [];
    }
    if (child.recipient_count !== batch.recipients ||
        child.provider_channel_id !== batch.provider_channel_id) {
      return [];
    }
    if (child.status === 'SUBMITTED' && !child.provider_campaign_id) { return []; }
  }

  const eligible = review.manifest.batches
    .map((batch, index) => batch.planned_status === 'READY' ? ordered[index]! : null)
    .filter((child): child is NonNullable<typeof child> => child !== null);
  const firstReady = eligible.findIndex(child => child.status === 'READY');
  if (firstReady < 0 || eligible.slice(0, firstReady).some(child => child.status !== 'SUBMITTED') ||
      eligible.slice(firstReady).some(child => child.status !== 'READY')) {
    return [];
  }
  if (continuing && firstReady === 0) { return []; }
  const lastSubmittedId = firstReady > 0 ? eligible[firstReady - 1].child_id : null;
  if (monitor.execution.last_child_id !== lastSubmittedId ||
      review.execution.last_child_id !== lastSubmittedId) {
    return [];
  }
  const ids = eligible.slice(firstReady).map(child => child.child_id);
  return new Set(ids).size === ids.length && ids.every(id => Number.isSafeInteger(id) && id > 0)
    ? ids : [];
}
