import React from 'react';

import AppBottomNav, { AppBottomNavItem } from './AppBottomNav';

export interface BottomNavItem extends AppBottomNavItem {}

export default function BottomNav({
  items,
  activeKey,
}: {
  items: BottomNavItem[];
  activeKey?: string | null;
}) {
  return <AppBottomNav items={items} activeKey={activeKey} />;
}
