/** Browser-free validators for Campaign V2 admin forms. Backend revalidates. */
export function isCampaignV2MxnUnitCostValid(value: string): boolean {
  const normalized = value.trim();
  const amount = Number(normalized);
  return /^\d+(\.\d{1,6})?$/.test(normalized)
    && Number.isFinite(amount) && amount > 0 && amount <= 1000;
}

export function isCampaignV2NominalLimitValid(value: string): boolean {
  const normalized = value.trim();
  return !normalized
    || (/^[1-9]\d*$/.test(normalized) && Number.isSafeInteger(Number(normalized)));
}

export function isCampaignV2RemainingCountValid(value: string): boolean {
  const normalized = value.trim();
  return /^\d+$/.test(normalized) && Number.isSafeInteger(Number(normalized));
}

export function isCampaignV2ZonedDateString(value: string): boolean {
  return /(Z|[+-]\d\d:\d\d)$/.test(value);
}
