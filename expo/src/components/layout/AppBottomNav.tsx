import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export interface AppBottomNavItem {
  key: string;
  label: string;
  icon?: string;
  onPress: () => void;
}

export const gameplayBottomNavBlueprint: Array<{
  key: string;
  label: string;
  icon: string;
}> = [
  { key: 'brief', label: 'Brief', icon: '\u{1F4F0}' },
  { key: 'dashboard', label: 'Dashboard', icon: '\u{1F4CA}' },
  { key: 'work', label: 'Work', icon: '\u{1F4BC}' },
  { key: 'business', label: 'Business', icon: '\u{1F3EA}' },
  { key: 'market', label: 'Wallet', icon: '\u{1F4B0}' },
  { key: 'life', label: 'Life', icon: '\u{2764}\u{FE0F}' },
  { key: 'map', label: 'Map', icon: '\u{1F5FA}\u{FE0F}' },
];

export default function AppBottomNav({
  items,
  activeKey,
}: {
  items: AppBottomNavItem[];
  activeKey?: string | null;
}) {
  return (
    <View style={styles.wrap}>
      {items.map((item) => {
        const active = activeKey === item.key;
        return (
          <Pressable
            key={item.key}
            onPress={item.onPress}
            style={({ pressed }) => [
              styles.item,
              active ? styles.itemActive : null,
              pressed ? styles.itemPressed : null,
            ]}
          >
            <Text style={[styles.icon, active ? styles.iconActive : null]}>{item.icon || '\u{2022}'}</Text>
            <Text style={[styles.label, active ? styles.labelActive : null]}>{item.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderTopWidth: 1,
    borderTopColor: theme.ui.border,
    backgroundColor: theme.ui.bg.card,
    flexDirection: 'row',
    paddingHorizontal: 4,
    paddingTop: 6,
    paddingBottom: 8,
    gap: 4,
  },
  item: {
    flex: 1,
    minHeight: 52,
    borderRadius: theme.ui.radius.navTile,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    gap: 2,
    paddingHorizontal: 2,
  },
  itemActive: {
    backgroundColor: alpha(theme.ui.tab.active, 0.16),
  },
  itemPressed: {
    opacity: 0.74,
  },
  icon: {
    fontSize: 18,
    color: theme.ui.tab.inactive,
    opacity: 0.94,
  },
  iconActive: {
    color: theme.ui.tab.active,
    opacity: 1,
  },
  label: {
    color: theme.ui.tab.inactive,
    ...theme.typography.caption,
    textAlign: 'center',
    fontWeight: '700',
  },
  labelActive: {
    color: theme.ui.tab.active,
  },
});
