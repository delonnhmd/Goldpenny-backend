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
    borderTopColor: '#1f2937',
    backgroundColor: '#111827',
    flexDirection: 'row',
    paddingHorizontal: 6,
    paddingTop: 6,
    paddingBottom: 8,
    gap: theme.spacing.xs,
  },
  item: {
    flex: 1,
    minHeight: 42,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: 'transparent',
  },
  itemActive: {
    backgroundColor: 'rgba(59, 130, 246, 0.18)',
  },
  itemPressed: {
    opacity: 0.74,
  },
  label: {
    color: '#94a3b8',
    ...theme.typography.label,
    textAlign: 'center',
  },
  labelActive: {
    color: '#60a5fa',
  },
});
