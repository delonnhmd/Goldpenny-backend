import React from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

import AppBottomNav, { AppBottomNavItem } from './AppBottomNav';
import SafeAreaPage from './SafeAreaPage';
import TopBar from './TopBar';

export default function AppShell({
  title,
  subtitle,
  headerRight,
  topStatusBar,
  showTopBar = true,
  children,
  footer,
  bottomNavItems,
  activeBottomNavKey,
}: {
  title: string;
  subtitle?: string | null;
  headerRight?: React.ReactNode;
  topStatusBar?: React.ReactNode;
  showTopBar?: boolean;
  children: React.ReactNode;
  footer?: React.ReactNode;
  bottomNavItems?: AppBottomNavItem[];
  activeBottomNavKey?: string | null;
}) {
  return (
    <SafeAreaPage edges={['top', 'bottom']}>
      <View style={styles.container}>
        {topStatusBar ? topStatusBar : null}
        {showTopBar ? <TopBar title={title} subtitle={subtitle} rightContent={headerRight} /> : null}
        <View style={styles.body}>{children}</View>
        {footer ? footer : null}
        {bottomNavItems && bottomNavItems.length > 0 ? (
          <AppBottomNav items={bottomNavItems} activeKey={activeBottomNavKey || undefined} />
        ) : null}
      </View>
    </SafeAreaPage>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.ui.bg.app,
  },
  body: {
    flex: 1,
  },
});
