import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { theme } from '@/design/theme';

export default function SectionHeader({
  title,
  summary,
  collapsible = false,
  expanded = false,
  onToggle,
}: {
  title: string;
  summary?: string | null;
  collapsible?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const HeaderContent = (
    <View style={styles.row}>
      <View style={styles.copy}>
        <Text style={styles.title}>{title}</Text>
        {summary ? <Text style={styles.summary}>{summary}</Text> : null}
      </View>
      {collapsible ? <Text style={styles.chevron}>{expanded ? 'Hide' : 'Show'}</Text> : null}
    </View>
  );

  if (!collapsible || !onToggle) {
    return HeaderContent;
  }

  return (
    <TouchableOpacity onPress={onToggle} style={styles.buttonWrap}>
      {HeaderContent}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  buttonWrap: {
    borderRadius: theme.radius.md,
    minHeight: 44,
    justifyContent: 'center',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  copy: {
    flex: 1,
    gap: theme.spacing.xs,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingMd,
    fontWeight: '800',
  },
  summary: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
  chevron: {
    color: theme.color.info,
    ...theme.typography.label,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
});
