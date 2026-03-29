import React from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import SlideUpPanel from '@/components/motion/SlideUpPanel';
import ActionPreviewTemplate from '@/components/templates/ActionPreviewTemplate';
import ActionRow from '@/components/ui/ActionRow';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import SurfaceCard from '@/components/ui/SurfaceCard';
import { ActionExecutionGuard } from '@/hooks/useDailySession';
import { confidenceLabel, trendLabel } from '@/lib/gameplayFormatters';
import { ActionPreviewResponse, DailyActionItem } from '@/types/gameplay';
import { theme } from '@/design/theme';

function ImpactRow({
  label,
  value,
}: {
  label: string;
  value?: { direction: string; text?: string };
}) {
  return (
    <SurfaceCard variant="muted" style={styles.impactRow}>
      <Text style={styles.impactLabel}>{label}</Text>
      <Text style={styles.impactValue}>
        {value ? `${trendLabel(value.direction as never)}${value.text ? ` | ${value.text}` : ''}` : 'No estimate'}
      </Text>
    </SurfaceCard>
  );
}

export default function ActionPreviewModal({
  visible,
  action,
  preview,
  loading,
  error,
  onClose,
  onExecuteAction,
  executeDisabled,
  executeGuard,
  executing,
}: {
  visible: boolean;
  action: DailyActionItem | null;
  preview: ActionPreviewResponse | null;
  loading: boolean;
  error?: string | null;
  onClose: () => void;
  onExecuteAction?: () => void | Promise<void>;
  executeDisabled?: boolean;
  executeGuard?: ActionExecutionGuard;
  executing?: boolean;
}) {
  const hasPreviewBlockers = Boolean(preview && preview.blockers && preview.blockers.length > 0);
  const blockedByGuard = executeGuard && !executeGuard.allowed;
  const canExecute =
    Boolean(onExecuteAction) &&
    Boolean(action) &&
    !executeDisabled &&
    !hasPreviewBlockers &&
    !blockedByGuard &&
    !executing;

  return (
    <SlideUpPanel visible={visible} onClose={onClose}>
      <ActionPreviewTemplate
        header={(
          <View style={styles.header}>
            <Text style={styles.title}>{action?.title || 'Action Preview'}</Text>
            <SecondaryButton label="Close" onPress={onClose} />
          </View>
        )}
        body={(
          <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
            {loading ? (
              <SurfaceCard variant="highlighted" style={styles.loadingBlock}>
                <ActivityIndicator size="small" color={theme.color.accent} />
                <Text style={styles.loadingText}>Calculating expected outcome...</Text>
              </SurfaceCard>
            ) : error ? (
              <SurfaceCard variant="warning" style={styles.warningBlock}>
                <Text style={styles.warningTitle}>Preview unavailable</Text>
                <Text style={styles.warningText}>{error}</Text>
              </SurfaceCard>
            ) : preview ? (
              <>
                <Text style={styles.summary}>{preview.summary}</Text>
                <ImpactRow label="Cash Impact" value={preview.expected_cash_impact} />
                <ImpactRow label="Stress Impact" value={preview.expected_stress_impact} />
                <ImpactRow label="Health Impact" value={preview.expected_health_impact} />
                <ImpactRow label="Time Impact" value={preview.expected_time_impact} />
                <ImpactRow label="Career Impact" value={preview.expected_career_impact} />
                <ImpactRow label="Distress Impact" value={preview.expected_distress_impact} />

                <SurfaceCard variant="highlighted" style={styles.metaBlock}>
                  <Text style={styles.metaTitle}>Confidence</Text>
                  <Text style={styles.metaText}>{confidenceLabel(preview.confidence_level)}</Text>
                  {executeGuard ? (
                    <Text style={styles.metaText}>Time Cost: {executeGuard.timeCostUnits} units</Text>
                  ) : null}
                </SurfaceCard>

                {preview.blockers.length > 0 ? (
                  <SurfaceCard variant="warning" style={styles.warningBlock}>
                    <Text style={styles.warningTitle}>Blockers</Text>
                    {preview.blockers.map((item, index) => (
                      <Text key={`blocker_${index}`} style={styles.warningText}>
                        - {item}
                      </Text>
                    ))}
                  </SurfaceCard>
                ) : null}

                {preview.warnings.length > 0 ? (
                  <SurfaceCard variant="warning" style={styles.warningBlock}>
                    <Text style={styles.warningTitle}>Warnings</Text>
                    {preview.warnings.map((item, index) => (
                      <Text key={`warning_${index}`} style={styles.warningText}>
                        - {item}
                      </Text>
                    ))}
                  </SurfaceCard>
                ) : null}
              </>
            ) : (
              <Text style={styles.loadingText}>No preview selected.</Text>
            )}
          </ScrollView>
        )}
        footer={(
          <View style={styles.footerWrap}>
            <ActionRow>
              <SecondaryButton label="Back" onPress={onClose} />
              <PrimaryButton
                label={executing ? 'Executing...' : 'Execute Action'}
                onPress={action && onExecuteAction ? () => onExecuteAction() : undefined}
                disabled={!canExecute}
                loading={Boolean(executing)}
              />
            </ActionRow>
            {!canExecute && executeGuard?.reason ? (
              <Text style={styles.footerHint}>{executeGuard.reason}</Text>
            ) : null}
            {!canExecute && !executeGuard?.reason ? (
              <Text style={styles.footerHint}>Action cannot be executed in the current state.</Text>
            ) : null}
          </View>
        )}
      />
    </SlideUpPanel>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingMd,
    flex: 1,
  },
  body: {
    gap: theme.spacing.sm,
  },
  summary: {
    color: theme.color.textSecondary,
    ...theme.typography.bodyMd,
  },
  impactRow: {
    gap: theme.spacing.xxs,
  },
  impactLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.label,
    textTransform: 'uppercase',
  },
  impactValue: {
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
  metaBlock: {
    gap: theme.spacing.xxs,
  },
  metaTitle: {
    color: theme.color.info,
    ...theme.typography.label,
  },
  metaText: {
    color: '#1e3a8a',
    ...theme.typography.bodySm,
  },
  warningBlock: {
    gap: theme.spacing.xxs,
  },
  warningTitle: {
    color: '#92400e',
    ...theme.typography.label,
  },
  warningText: {
    color: '#78350f',
    ...theme.typography.bodySm,
  },
  loadingBlock: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  loadingText: {
    color: theme.color.info,
    ...theme.typography.bodySm,
  },
  footerWrap: {
    gap: theme.spacing.xs,
  },
  footerHint: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
});
