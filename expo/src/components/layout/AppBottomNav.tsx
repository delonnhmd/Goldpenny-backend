import { MaterialCommunityIcons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

export interface AppBottomNavItem {
  key: string;
  label: string;
  icon?: React.ComponentProps<typeof MaterialCommunityIcons>['name'];
  onPress: () => void;
}

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
        const color = active ? theme.ui.tab.active : theme.ui.tab.inactive;
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
            <MaterialCommunityIcons name={item.icon || 'circle-medium'} size={20} color={color} />
            <Text style={[styles.label, { color }]}>{item.label}</Text>
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
    paddingHorizontal: theme.spacing.xs,
    paddingTop: theme.spacing.sm,
    paddingBottom: theme.spacing.sm,
    gap: theme.spacing.xs,
  },
  item: {
    flex: 1,
    minHeight: 56,
    borderRadius: theme.ui.radius.navTile,
    alignItems: 'center',
    justifyContent: 'center',
    gap: theme.spacing.xxs,
  },
  itemActive: {
    backgroundColor: alpha(theme.ui.action, 0.14),
  },
  itemPressed: {
    opacity: 0.78,
  },
  label: {
    ...theme.typography.caption,
    fontWeight: '700',
    textAlign: 'center',
  },
});
