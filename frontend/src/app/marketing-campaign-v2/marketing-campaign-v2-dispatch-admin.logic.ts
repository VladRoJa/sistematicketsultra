/** Pure, testable guards. Backend revalidates these independently. */
export interface DispatchTemplateDraft {
  templateName: string;
  label: string;
  purposes: string[];
  channelIds: string[];
  activeChannelIds: string[];
  variables: string[];
  fileUrl: string;
}

const SOURCES = new Set([
  'first_name', 'expiration_date', 'tariff', 'branch',
  'member_id', 'member_pin', 'amount',
]);

export function isDispatchTemplateDraftValid(draft: DispatchTemplateDraft): boolean {
  const active = new Set(draft.activeChannelIds);
  if (!draft.templateName.trim() || !draft.label.trim() || draft.purposes.length === 0
      || draft.channelIds.length === 0 || new Set(draft.channelIds).size !== draft.channelIds.length
      || draft.channelIds.some(channel => !active.has(channel))) {
    return false;
  }
  if (draft.variables.some(source => !SOURCES.has(source))) {
    return false;
  }
  if (draft.fileUrl.trim()) {
    try {
      const url = new URL(draft.fileUrl.trim());
      if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) {
        return false;
      }
    } catch {
      return false;
    }
  }
  return true;
}
