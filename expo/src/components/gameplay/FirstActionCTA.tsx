import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';

import PrimaryButton from '@/components/ui/PrimaryButton';
import { alpha, theme } from '@/design/theme';
import type { PlayerBusinessesResponse } from '@/types/business';
import type { PlayerDashboardResponse } from '@/types/gameplay';

export type FirstActionVariant = 'get_job' | 'restock' | 'start_shift' | 'run_business';

interface FirstActionCTAProps {
  playerId: string;
  dashboard: PlayerDashboardResponse | null;
  businesses: PlayerBusinessesResponse | null;
  disabled?: boolean;
}

interface DerivedAction {
  variant: FirstActionVariant;
  label: string;
  situation: string;
  outcome: string;
  href: string;
}

const LOW_CASH_THRESHOLD = 100;

function pickFirstAction(
  dashboard: PlayerDashboardResponse | null,
  businesses: PlayerBusinessesResponse | null,
  playerId: string,
): DerivedAction {
  const stats = dashboard?.stats;
  const cash = Number(stats?.cash_xgp ?? 0);
  const currentJob = String(stats?.current_job || '').trim();
  const hasJob = currentJob.length > 0;

  const activeBusinesses = (businesses?.businesses || []).filter((b) => b.is_active);
  const hasBusiness = activeBusinesses.length > 0;

  const hasEmptyInventoryBusiness = activeBusinesses.some((b) => {
    const total =
      Number(b.inventory_produce_units || 0) +
      Number(b.inventory_essentials_units || 0) +
      Number(b.inventory_protein_units || 0);
    return total <= 0;
  });

  // Priority: job > inventory > cash > otherwise.
  if (!hasJob) {
    return {
      variant: 'get_job',
      label: 'Get a Job',
      situation: 'No job yet — your first paycheck is one tap away.',
      outcome: 'Pick a starter role and start earning today.',
      href: `/gameplay/loop/${playerId}/work`,
    };
  }
  if (hasBusiness && hasEmptyInventoryBusiness) {
    return {
      variant: 'restock',
      label: 'Restock Now',
      situation: 'Your business is out of stock and cannot operate.',
      outcome: 'Buy inventory so your business can run.',
      href: `/gameplay/loop/${playerId}/business`,
    };
  }
  if (cash < LOW_CASH_THRESHOLD) {
    return {
      variant: 'start_shift',
      label: 'Start Shift',
      situation: `Cash is low (${Math.round(cash)} XGP). A shift is the fastest fix.`,
      outcome: 'Earn wages and reset stress at the end of the day.',
      href: `/gameplay/loop/${playerId}/work`,
    };
  }
  if (hasBusiness) {
    return {
      variant: 'run_business',
      label: 'Run Business',
      situation: 'Cash is steady — operate your business for net profit.',
      outcome: 'Sell stock, log a daily profit, and grow reputation.',
      href: `/gameplay/loop/${playerId}/business`,
    };
  }
  return {
    variant: 'start_shift',
    label: 'Start Shift',
    situation: 'Get to work — paychecks fund everything else.',
    outcome: 'Earn wages today. Plan tomorrow with the result.',
    href: `/gameplay/loop/${playerId}/work`,
  };
}

export default function FirstActionCTA({
  playerId,
  dashboard,
  businesses,
  disabled = false,
}: FirstActionCTAProps) {
  const action = pickFirstAction(dashboard, businesses, playerId);
  return (
    <View style={styles.card} accessibilityLabel="Primary action">
      <Text style={styles.eyebrow}>Do this first</Text>
      <Text style={styles.situation}>{action.situation}</Text>
      <Text style={styles.outcome}>{action.outcome}</Text>
      <PrimaryButton
        label={action.label}
        onPress={() => {
          router.push(action.href as never);
        }}
        disabled={disabled}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: alpha(theme.ui.positive, 0.32),
    borderRadius: theme.radius.xl,
    backgroundColor: alpha(theme.ui.positive, 0.06),
    padding: theme.spacing.lg,
    gap: theme.spacing.xs,
    ...theme.shadow.md,
  },
  eyebrow: {
    ...theme.typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    color: theme.ui.positive,
    fontWeight: '800',
  },
  situation: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  outcome: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
    marginBottom: theme.spacing.xs,
  },
});
