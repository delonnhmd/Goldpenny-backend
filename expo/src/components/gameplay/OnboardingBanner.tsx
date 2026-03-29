import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { OnboardingGuidanceResponse, OnboardingStateResponse } from '@/types/onboarding';

function primaryLabel(stepKey: string): string | null {
  if (stepKey === 'welcome_core_premise') return 'Start Here';
  if (stepKey === 'read_todays_brief') return 'Show Actions';
  return null;
}

function stepHint(stepKey: string, guidance: OnboardingGuidanceResponse | null): string {
  if (stepKey === 'welcome_core_premise') return 'You only need one short day to learn the loop.';
  if (stepKey === 'read_todays_brief') return 'Look for one risk and one opportunity, then act.';
  if (stepKey === 'first_income_action') return 'Tap Work in the lower action bar to earn real cash.';
  if (stepKey === 'end_first_day') return 'Tap End Day in the lower action bar to lock the result.';
  if (stepKey === 'guided_day_2_pressure') return guidance?.blocker_reason || 'Bills, debt, and recovery now matter.';
  if (stepKey === 'guided_day_3_opportunity') return guidance?.blocker_reason || 'Look for one safe opportunity without breaking your cash buffer.';
  return guidance?.blocker_reason || 'Follow the highlighted next step.';
}

export default function OnboardingBanner({
  state,
  guidance,
  busy,
  onAdvance,
  onSkip,
}: {
  state: OnboardingStateResponse;
  guidance: OnboardingGuidanceResponse | null;
  busy?: boolean;
  onAdvance?: (actionKey?: string | null) => void;
  onSkip?: () => void;
}) {
  const stepKey = String(guidance?.step_key || state.current_step_key || 'welcome_core_premise');
  const buttonLabel = primaryLabel(stepKey);
  const title = guidance?.title || state.current_step_title || 'First Day Guide';
  const body = guidance?.body || state.current_step_body || 'Read the Daily Brief, take one action, then end the day.';
  const hint = stepHint(stepKey, guidance);
  const guideTitle = guidance?.guided_day_number && guidance.guided_day_number > 1 ? 'Early Days Guide' : 'First Session Guide';
  const guideLabel = guidance?.guided_label || state.guided_label || state.progress_label || '1/4 steps';

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{guideTitle}</Text>
        <Text style={styles.stepPill}>{guideLabel}</Text>
      </View>

      <Text style={styles.stepTitle}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
      <Text style={styles.hint}>{hint}</Text>

      <View style={styles.actionsRow}>
        {buttonLabel && onAdvance ? (
          <PrimaryButton
            label={buttonLabel}
            onPress={() => onAdvance(guidance?.required_action_key)}
            disabled={Boolean(busy)}
            style={styles.primaryButton}
          />
        ) : null}
        {guidance?.can_skip && onSkip ? (
          <SecondaryButton
            label="Skip"
            onPress={onSkip}
            disabled={Boolean(busy)}
            style={styles.skipButton}
          />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: 12,
    backgroundColor: '#eff6ff',
    padding: 14,
    gap: 8,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    flexWrap: 'wrap',
  },
  title: {
    color: '#1e40af',
    fontSize: 12,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  stepPill: {
    color: '#1d4ed8',
    fontSize: 11,
    fontWeight: '800',
  },
  stepTitle: {
    color: '#0f172a',
    fontSize: 16,
    fontWeight: '700',
  },
  body: {
    color: '#334155',
    fontSize: 13,
    lineHeight: 18,
  },
  hint: {
    color: '#1e3a8a',
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '600',
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  primaryButton: {
    flexGrow: 1,
    minWidth: 132,
  },
  skipButton: {
    minWidth: 92,
  },
});
