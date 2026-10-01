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

export const CAMPAIGN_V2_MENU_ITEM: CampaignV2MenuChild = {
  label: 'Campañas V2',
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
  if (submenu.some(item => item.path === CAMPAIGN_V2_MENU_ITEM.path)) {
    return menuItems;
  }

  const next = [...menuItems];
  next[marketingIndex] = {
    ...current,
    path: current.path === '/main/ver-tickets' ? CAMPAIGN_V2_MENU_ITEM.path : current.path,
    submenu: [...submenu, CAMPAIGN_V2_MENU_ITEM],
  };
  return next;
}
