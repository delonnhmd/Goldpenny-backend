import React from 'react';
import { StyleSheet } from 'react-native';

import SurfaceCard from '@/components/ui/SurfaceCard';
import { theme } from '@/design/theme';

import CollapsibleSection from './CollapsibleSection';
import SectionHeader from './SectionHeader';
import SectionSummaryRow from './SectionSummaryRow';

export default function SecondaryDashboardSection({
  title,
  summary,
  expanded,
  onToggle,
  children,
  statusLabel,
}: {
  title: string;
  summary: string;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  statusLabel?: string | null;
}) {
  return (
    <SurfaceCard variant="muted" style={styles.card}>
      <SectionHeader
        title={title}
        collapsible
        expanded={expanded}
        onToggle={onToggle}
      />
      <SectionSummaryRow summary={summary} statusLabel={statusLabel} />
      <CollapsibleSection expanded={expanded}>{children}</CollapsibleSection>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: theme.spacing.sm,
  },
});
