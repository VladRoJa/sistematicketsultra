import {
  CampaignV2BudgetRateRevision,
  CampaignV2ChannelBinding,
  CampaignV2DispatchTemplate,
  CampaignV2QuotaPolicyRevision,
} from './marketing-campaign-v2.models';

export interface CampaignV2ReadinessRow {
  sucursalCanon: string;
  sendViaSucursalCanon: string | null;
  channelId: string;
  bindingId: number;
  portfolioKey: string | null;
  portfolioVerified: false;
  accountAlias: string | null;
  operationalChannelCap: number | null;
  operationalPortfolioCap: number | null;
  unitCostMxn: string | null;
  rateSource: string | null;
  policySource: string | null;
  templateCompatible: boolean;
  configured: boolean;
  issues: string[];
}

function latestBy<T>(
  values: T[], key: (value: T) => string,
  date: (value: T) => string, revision: (value: T) => number,
): Map<string, T> {
  const selected = new Map<string, T>();
  for (const item of [...values].sort(
    (a, b) => date(b).localeCompare(date(a)) || revision(b) - revision(a),
  )) {
    const itemKey = key(item);
    if (!selected.has(itemKey)) { selected.set(itemKey, item); }
  }
  return selected;
}

export function campaignV2BuildReadinessRows(
  template: CampaignV2DispatchTemplate | null,
  bindings: CampaignV2ChannelBinding[],
  policies: CampaignV2QuotaPolicyRevision[],
  rates: CampaignV2BudgetRateRevision[],
): CampaignV2ReadinessRow[] {
  const active = bindings.filter(row => row.is_active && row.is_default);
  const latestPolicies = latestBy(
    policies, row => row.provider_channel_id, row => row.valid_from, row => row.revision_id,
  );
  const latestRates = latestBy(
    rates.filter(row => row.template_id === template?.id),
    row => row.provider_channel_id, row => row.valid_from, row => row.revision_id,
  );
  const byBranch = new Map<string, number>();
  for (const row of active) {
    byBranch.set(row.sucursal_canon, (byBranch.get(row.sucursal_canon) ?? 0) + 1);
  }
  return active.map(binding => {
    const routeId = binding.metadata['dispatch_via_binding_id'];
    const routed = typeof routeId === 'number';
    const sender = routed ? active.find(row => row.id === routeId) : binding;
    const approvedRoute = !routed || (binding.sucursal_canon === 'INDEPENDENCIA'
      && sender?.sucursal_canon === 'TEC_MXL');
    const channelId = sender?.provider_channel_id ?? binding.provider_channel_id;
    const policy = latestPolicies.get(channelId);
    const rate = latestRates.get(channelId);
    const issues: string[] = [];
    const compatible = Boolean(template?.is_active && (
      template.compatible_channel_ids.includes(channelId)
    ));
    if (!compatible) { issues.push('Plantilla sin asociación válida'); }
    if (routed && (!sender || !approvedRoute)) {
      issues.push('Canal emisor alternativo no disponible o no autorizado');
    }
    if ((byBranch.get(binding.sucursal_canon) ?? 0) !== 1) {
      issues.push('Más de un canal predeterminado');
    }
    // Portfolio verification and manual policy are informational in the
    // exception-only send contract. The backend enforces 250 for each special
    // branch independently and still requires exact channel/template mapping.
    return {
      sucursalCanon: binding.sucursal_canon,
      sendViaSucursalCanon: routed ? sender?.sucursal_canon ?? null : null,
      channelId,
      bindingId: sender?.id ?? binding.id,
      portfolioKey: policy?.portfolio_key || null,
      portfolioVerified: false as const,
      accountAlias: policy?.account_key || null,
      operationalChannelCap: (
        ['INDEPENDENCIA', 'INSURGENTES'].includes((sender?.sucursal_canon ?? binding.sucursal_canon).trim().toUpperCase()) ||
        ['6a29c8ffe83fa20008b5a789', '6a2aff2d555186000912586d'].includes(channelId)
      ) ? 250 : null,
      operationalPortfolioCap: null,
      unitCostMxn: rate?.unit_cost_mxn ?? null,
      rateSource: rate?.source_reference ?? null,
      policySource: policy?.source_reference ?? null,
      templateCompatible: compatible,
      configured: issues.length === 0,
      issues,
    };
  }).sort((a, b) => a.sucursalCanon.localeCompare(b.sucursalCanon));
}
