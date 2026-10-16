/** Validate campaign IDs before starting read-only prior-contact reconciliation. */
export type PreviousCampaignIdParse = { ids: number[]; error: '' } | { ids: []; error: string };

export function parsePreviousCampaignIds(raw: string, currentCampaignId: number): PreviousCampaignIdParse {
  const pieces = raw.split(',').map(value => value.trim());
  if (!pieces.length || pieces.length > 20 || pieces.some(value => !/^[1-9]\d*$/.test(value))) {
    return { ids: [], error: 'Indica de 1 a 20 IDs positivos, separados por comas (ejemplo: 20, 21).' };
  }
  const ids = pieces.map(value => Number(value));
  if (ids.some(value => !Number.isSafeInteger(value) || value >= currentCampaignId) ||
      new Set(ids).size !== ids.length) {
    return { ids: [], error: 'Los IDs deben ser únicos y anteriores a esta campaña.' };
  }
  return { ids, error: '' };
}
