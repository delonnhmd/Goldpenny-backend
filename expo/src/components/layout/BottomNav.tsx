import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

export interface BottomNavItem {
  key: string;
  label: string;
  onPress: () => void;
}

export default function BottomNav({
  items,
  activeKey,
}: {
  items: BottomNavItem[];
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
    borderTopColor: theme.color.border,
    backgroundColor: theme.color.surface,
    flexDirection: 'row',
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
    gap: theme.spacing.xs,
  },
  item: {
    flex: 1,
    minHeight: 36,
    borderRadius: theme.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.color.surface,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  itemActive: {
    borderColor: '#bfdbfe',
    backgroundColor: '#eff6ff',
  },
  itemPressed: {
    opacity: 0.8,
  },
  label: {
    color: theme.color.textSecondary,
    ...theme.typography.label,
    textAlign: 'center',
  },
  labelActive: {
    color: theme.color.info,
  },
});
