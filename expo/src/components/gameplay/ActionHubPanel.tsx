import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import CollapsibleSection from '@/components/gameplay/CollapsibleSection';
import ProgressMeter from '@/components/ui/ProgressMeter';
import SurfaceCard from '@/components/ui/SurfaceCard';
import { theme } from '@/design/theme';
import { ActionExecutionGuard } from '@/hooks/useDailySession';
import { useBreakpoint } from '@/hooks/useBreakpoint';
import { DailyActionHubResponse, DailyActionItem } from '@/types/gameplay';

import ActionCard from './ActionCard';

function ActionSection({
  title,
  actions,
  onExecute,
  getExecutionGuard,
  collapsible = false,
  defaultExpanded = true,
}: {
  title: string;
  actions: DailyActionItem[];
  onExecute: (action: DailyActionItem) => void;
  getExecutionGuard: (action: DailyActionItem) => ActionExecutionGuard;
  collapsible?: boolean;
  defaultExpanded?: boolean;
}) {
  const { isMobile } = useBreakpoint();
  const [expanded, setExpanded] = useState(!collapsible || defaultExpanded);

  useEffect(() => {
    if (!collapsible || !isMobile) {
      setExpanded(true);
      return;
    }
    setExpanded(defaultExpanded);
  }, [collapsible, defaultExpanded, isMobile]);

  const body = (
    <>
      {actions.length > 0 ? (
        actions.map((action, index) => {
          const executionGuard = getExecutionGuard(action);
          return (
            <ActionCard
              key={`${title}_${action.action_key}_${index}`}
              action={action}
              onExecute={onExecute}
              executionGuard={executionGuard}
            />
          );
        })
      ) : (
        <Text style={styles.empty}>No actions available right now.</Text>
      )}
    </>
  );

  if (!collapsible || !isMobile) {
    return (
      <View style={styles.section}>
        {body}
      </View>
    );
  }

  return (
    <View style={styles.section}>
      <Pressable onPress={() => setExpanded((prev) => !prev)} style={styles.sectionHeaderButton}>
        <Text style={styles.sectionTitle}>{title}</Text>
        <Text style={styles.sectionToggle}>{expanded ? 'Hide' : 'Show'}</Text>
      </Pressable>
      <CollapsibleSection expanded={expanded}>{body}</CollapsibleSection>
    </View>
  );
}

export default function ActionHubPanel({
  hub,
  onExecuteAction,
  getExecutionGuard,
  remainingTimeUnits,
  totalTimeUnits,
  sessionStatus,
  progressRatio,
}: {
  hub: DailyActionHubResponse;
  onExecuteAction: (action: DailyActionItem) => void;
  getExecutionGuard: (action: DailyActionItem) => ActionExecutionGuard;
  remainingTimeUnits: number;
  totalTimeUnits: number;
  sessionStatus: 'active' | 'ended';
  progressRatio: number;
}) {
  return (
    <SurfaceCard style={styles.card}>
      <SurfaceCard variant="muted" style={styles.timeBox}>
        <View style={styles.timeTopRow}>
          <Text style={styles.timeTitle}>{remainingTimeUnits}/{totalTimeUnits} units left</Text>
          <Text style={styles.timeMeta}>
            {sessionStatus === 'active' ? 'Action window open' : 'Day settled'}
          </Text>
        </View>
        <ProgressMeter progress={progressRatio} />
      </SurfaceCard>

      <ActionSection
        title="Recommended"
        actions={hub.recommended_actions}
        onExecute={onExecuteAction}
        getExecutionGuard={getExecutionGuard}
      />
      <ActionSection
        title="Available"
        actions={hub.available_actions}
        onExecute={onExecuteAction}
        getExecutionGuard={getExecutionGuard}
      />
      <ActionSection
        title="Blocked"
        actions={hub.blocked_actions}
        onExecute={onExecuteAction}
        getExecutionGuard={getExecutionGuard}
        collapsible
        defaultExpanded={false}
      />
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  card: {
    gap: theme.spacing.lg,
  },
  timeBox: {
    gap: theme.spacing.md,
  },
  timeTopRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  timeTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.label,
    fontWeight: '800',
  },
  timeMeta: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
  section: {
    gap: theme.spacing.md,
  },
  sectionHeaderButton: {
    minHeight: 44,
    borderRadius: theme.radius.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  sectionTitle: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
    fontWeight: '800',
  },
  sectionToggle: {
    color: theme.color.info,
    ...theme.typography.label,
    fontWeight: '800',
  },
  empty: {
    color: theme.color.muted,
    ...theme.typography.bodySm,
  },
});
