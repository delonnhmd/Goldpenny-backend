import React from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

import BottomNav, { BottomNavItem } from './BottomNav';
import SafeAreaPage from './SafeAreaPage';
import TopBar from './TopBar';

export default function AppShell({
  title,
  subtitle,
  headerRight,
  children,
  footer,
  bottomNavItems,
  activeBottomNavKey,
}: {
  title: string;
  subtitle?: string | null;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  bottomNavItems?: BottomNavItem[];
  activeBottomNavKey?: string | null;
}) {
  return (
    <SafeAreaPage edges={['top', 'bottom']}>
      <View style={styles.container}>
        <TopBar title={title} subtitle={subtitle} rightContent={headerRight} />
        <View style={styles.body}>{children}</View>
        {footer ? footer : null}
        {bottomNavItems && bottomNavItems.length > 0 ? (
          <BottomNav items={bottomNavItems} activeKey={activeBottomNavKey || undefined} />
        ) : null}
      </View>
    </SafeAreaPage>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.color.background,
  },
  body: {
    flex: 1,
  },
});
