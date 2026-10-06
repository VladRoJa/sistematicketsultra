export interface CampaignV2MenuChild {
  label: string;
  path: string;
}

export interface CampaignV2MenuGroup {
  label: string;
  path: string;
  submenu?: CampaignV2MenuChild[];
  [key: string]: unknown;
}

const LEGACY_CAMPAIGN_PATH = '/marketing/reactivation';

export const CAMPAIGN_V2_MENU_ITEM: CampaignV2MenuChild = {
  label: 'Campañas',
  path: '/marketing/campaigns-v2',
};

export function withCampaignV2MenuItem(
  menuItems: CampaignV2MenuGroup[],
): CampaignV2MenuGroup[] {
  const marketingIndex = menuItems.findIndex(
    item => item.label === 'Marketing y Conversión',
  );

  if (marketingIndex < 0) {
    return [
      ...menuItems,
      {
        label: 'Marketing y Conversión',
        path: CAMPAIGN_V2_MENU_ITEM.path,
        submenu: [CAMPAIGN_V2_MENU_ITEM],
      },
    ];
  }

  const current = menuItems[marketingIndex];
  const submenu = Array.isArray(current.submenu) ? current.submenu : [];
  const hasLegacy = submenu.some(item => item.path === LEGACY_CAMPAIGN_PATH);
  const existingV2 = submenu.find(item => item.path === CAMPAIGN_V2_MENU_ITEM.path);
  const pathNeedsReplacement = (
    current.path === '/main/ver-tickets'
    || current.path === LEGACY_CAMPAIGN_PATH
  );
  const labelNeedsReplacement = (
    existingV2 !== undefined
    && existingV2.label !== CAMPAIGN_V2_MENU_ITEM.label
  );

  if (!hasLegacy && existingV2 && !pathNeedsReplacement && !labelNeedsReplacement) {
    return menuItems;
  }

  const nextSubmenu = submenu
    .filter(item => item.path !== LEGACY_CAMPAIGN_PATH)
    .map(item => (
      item.path === CAMPAIGN_V2_MENU_ITEM.path
        ? CAMPAIGN_V2_MENU_ITEM
        : item
    ));

  if (!existingV2) {
    nextSubmenu.push(CAMPAIGN_V2_MENU_ITEM);
  }

  const next = [...menuItems];
  next[marketingIndex] = {
    ...current,
    path: pathNeedsReplacement ? CAMPAIGN_V2_MENU_ITEM.path : current.path,
    submenu: nextSubmenu,
  };
  return next;
}
