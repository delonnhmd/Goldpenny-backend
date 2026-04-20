import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export interface AppBottomNavItem {
  key: string;
  label: string;
  icon?: string;
  onPress: () => void;
}

export const gameplayBottomNavBlueprint: {
  key: string;
  label: string;
  icon: string;
}[] = [
  { key: 'map', label: 'Map', icon: '\u{1F5FA}\u{FE0F}' },
  { key: 'work', label: 'Work', icon: '\u{1F4BC}' },
  { key: 'business', label: 'Business', icon: '\u{1F3EA}' },
  { key: 'portfolio', label: 'Portfolio', icon: '\u{1F4C8}' },
  { key: 'life', label: 'Life', icon: '\u{2764}\u{FE0F}' },
];

export default function AppBottomNav({
  items,
  activeKey,
}: {
  items: AppBottomNavItem[];
  activeKey?: string | null;
}) {
  const webGridStyle = Platform.OS === 'web'
    ? ({ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)' } as never)
    : null;

  return (
    <View style={[styles.wrap, webGridStyle]}>
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
    paddingHorizontal: 0,
    paddingTop: 6,
    paddingBottom: 8,
  },
  item: {
    flex: 1,
    minHeight: 52,
    borderRadius: 0,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    gap: 2,
    paddingHorizontal: 4,
  },
  itemActive: {
    backgroundColor: alpha(theme.ui.tab.active, 0.12),
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
