import {
  CampaignV2BudgetRateRevision,
  CampaignV2DispatchTemplate,
} from './marketing-campaign-v2.models';

export interface CampaignV2IndicativeBudget {
  status: 'UNPRICED' | 'INCOMPLETE' | 'RANGE';
  min_mxn: string | null;
  max_mxn: string | null;
  missing_channels: number;
  covered_channels: number;
}

function moneyFromMicros(micros: number, recipients: number): string {
  return (Math.round(micros * recipients / 10000) / 100).toFixed(2);
}

/** Informative envelope, not a quote for exact branches or final sendable recipients. */
export function campaignV2IndicativeBudget(
  template: CampaignV2DispatchTemplate | undefined,
  revisions: CampaignV2BudgetRateRevision[],
  recipients: number,
  asOf: string,
): CampaignV2IndicativeBudget {
  const empty: CampaignV2IndicativeBudget = {
    status: 'UNPRICED', min_mxn: null, max_mxn: null,
    missing_channels: 0, covered_channels: 0,
  };
  if (!template || !Number.isSafeInteger(recipients) || recipients <= 0
      || template.compatible_channel_ids.length === 0) {
    return empty;
  }
  const now = Date.parse(asOf);
  if (!Number.isFinite(now)) { return empty; }
  const channels = [...new Set(template.compatible_channel_ids)];
  const priceMicros: number[] = [];
  let missing = 0;
  for (const channel of channels) {
    const latest = revisions
      .filter(rate => rate.template_id === template.id
        && rate.provider_channel_id === channel
        && Date.parse(rate.valid_from) <= now)
      .sort((a, b) => Date.parse(b.valid_from) - Date.parse(a.valid_from)
        || b.revision_id - a.revision_id)[0];
    if (!latest || !/^\d+(\.\d{1,6})?$/.test(latest.unit_cost_mxn)) {
      missing++;
      continue;
    }
    const micros = Math.round(Number(latest.unit_cost_mxn) * 1e6);
    if (!Number.isSafeInteger(micros) || micros <= 0) {
      missing++;
      continue;
    }
    priceMicros.push(micros);
  }
  if (!priceMicros.length || missing) {
    return {
      status: 'INCOMPLETE', min_mxn: null, max_mxn: null,
      missing_channels: missing, covered_channels: priceMicros.length,
    };
  }
  return {
    status: 'RANGE',
    min_mxn: moneyFromMicros(Math.min(...priceMicros), recipients),
    max_mxn: moneyFromMicros(Math.max(...priceMicros), recipients),
    missing_channels: 0, covered_channels: priceMicros.length,
  };
}
