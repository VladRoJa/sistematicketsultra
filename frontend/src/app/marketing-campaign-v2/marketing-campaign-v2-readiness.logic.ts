import {
  CampaignV2BudgetRateRevision,
  CampaignV2ChannelBinding,
  CampaignV2DispatchTemplate,
  CampaignV2QuotaPolicyRevision,
} from './marketing-campaign-v2.models';

export interface CampaignV2ReadinessRow {
  sucursalCanon: string;
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
  const byPortfolio = new Map<string, Set<number>>();
  for (const channel of active) {
    const policy = latestPolicies.get(channel.provider_channel_id);
    if (policy?.portfolio_key && policy.operational_portfolio_cap !== null) {
      const caps = byPortfolio.get(policy.portfolio_key) ?? new Set<number>();
      caps.add(policy.operational_portfolio_cap);
      byPortfolio.set(policy.portfolio_key, caps);
    }
  }
  return active.map(binding => {
    const policy = latestPolicies.get(binding.provider_channel_id);
    const rate = latestRates.get(binding.provider_channel_id);
    const issues: string[] = [];
    const compatible = Boolean(template?.is_active && (
      template.compatible_channel_ids.includes(binding.provider_channel_id)
    ));
    if (!compatible) { issues.push('Plantilla sin asociación válida'); }
    if ((byBranch.get(binding.sucursal_canon) ?? 0) !== 1) {
      issues.push('Más de un canal predeterminado');
    }
    if (!policy?.portfolio_key) { issues.push('Portafolio sin identificar'); }
    if (!policy?.operational_channel_cap || !policy.operational_portfolio_cap) {
      issues.push('Límites internos pendientes');
    }
    if (policy?.portfolio_key && (byPortfolio.get(policy.portfolio_key)?.size ?? 0) > 1) {
      issues.push('Límites inconsistentes del portafolio');
    }
    if (!rate) { issues.push('Tarifa MXN pendiente'); }
    return {
      sucursalCanon: binding.sucursal_canon,
      channelId: binding.provider_channel_id,
      bindingId: binding.id,
      portfolioKey: policy?.portfolio_key || null,
      portfolioVerified: false as const,
      accountAlias: policy?.account_key || null,
      operationalChannelCap: policy?.operational_channel_cap ?? null,
      operationalPortfolioCap: policy?.operational_portfolio_cap ?? null,
      unitCostMxn: rate?.unit_cost_mxn ?? null,
      rateSource: rate?.source_reference ?? null,
      policySource: policy?.source_reference ?? null,
      templateCompatible: compatible,
      configured: issues.length === 0,
      issues,
    };
  }).sort((a, b) => a.sucursalCanon.localeCompare(b.sucursalCanon));
}
