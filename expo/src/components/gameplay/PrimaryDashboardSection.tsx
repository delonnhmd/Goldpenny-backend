import React from 'react';
import { StyleSheet, View } from 'react-native';

import SurfaceCard from '@/components/ui/SurfaceCard';
import { theme } from '@/design/theme';

import CollapsibleSection from './CollapsibleSection';
import SectionHeader from './SectionHeader';
import SectionSummaryRow from './SectionSummaryRow';

export default function PrimaryDashboardSection({
  title,
  summary,
  children,
  statusLabel,
  collapsible = false,
  expanded = true,
  onToggle,
}: {
  title: string;
  summary?: string | null;
  children: React.ReactNode;
  statusLabel?: string | null;
  collapsible?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  return (
    <SurfaceCard style={styles.card}>
      <SectionHeader
        title={title}
        collapsible={collapsible}
        expanded={expanded}
        onToggle={onToggle}
      />
      {summary ? <SectionSummaryRow summary={summary} statusLabel={statusLabel} /> : null}
      {collapsible ? (
        <CollapsibleSection expanded={expanded}>
          <View style={styles.body}>{children}</View>
        </CollapsibleSection>
      ) : (
        <View style={styles.body}>{children}</View>
      )}
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: theme.spacing.sm,
  },
  body: {
    gap: theme.spacing.md,
  },
});
