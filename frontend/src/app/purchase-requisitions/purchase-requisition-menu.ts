export interface PurchaseRequisitionMenuChild {
  label: string;
  path: string;
}

export interface PurchaseRequisitionMenuGroup {
  label: string;
  path: string;
  submenu?: PurchaseRequisitionMenuChild[];
  [key: string]: unknown;
}

export const PURCHASE_REQUISITION_MENU_ITEM: PurchaseRequisitionMenuChild = {
  label: 'Requisiciones',
  path: '/main/requisiciones',
};

export function withPurchaseRequisitionMenuItem(
  menuItems: PurchaseRequisitionMenuGroup[],
): PurchaseRequisitionMenuGroup[] {
  const ticketsIndex = menuItems.findIndex(
    item => item.label === 'Tickets',
  );

  if (ticketsIndex < 0) {
    return menuItems;
  }

  const current = menuItems[ticketsIndex];
  const submenu = Array.isArray(current.submenu) ? current.submenu : [];

  if (submenu.some(item => item.path === PURCHASE_REQUISITION_MENU_ITEM.path)) {
    return menuItems;
  }

  const insertAfterCreate = submenu.findIndex(
    item => item.path === '/main/crear-ticket',
  );
  const nextSubmenu = [...submenu];
  nextSubmenu.splice(
    insertAfterCreate >= 0 ? insertAfterCreate + 1 : nextSubmenu.length,
    0,
    PURCHASE_REQUISITION_MENU_ITEM,
  );

  const next = [...menuItems];
  next[ticketsIndex] = {
    ...current,
    submenu: nextSubmenu,
  };
  return next;
}
