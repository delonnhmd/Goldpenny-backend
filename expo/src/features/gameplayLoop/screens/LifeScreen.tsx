import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { useOnboarding } from '@/features/onboarding';
import { useScreenTimer } from '@/hooks/useScreenTimer';
import { formatMoney } from '@/lib/gameplayFormatters';

import { useGameplayLoop } from '../context';
import {
  GameplayCompactMetricRows,
  GameplayStickyActionArea,
  GameplaySummaryCard,
  GameplayWarningBanner,
} from '../components/GameplayUIParts';
import GameplayLoopScaffold from '../GameplayLoopScaffold';

const HOUSING_INFO = {
  suburban: { label: 'Suburban', rent: 80, gas: 40, stressNote: '−2 stress/wk', stressMod: -2 },
  downtown: { label: 'Downtown', rent: 140, gas: 20, stressNote: '+5 stress/wk', stressMod: 5 },
} as const;

const LOAN_AMOUNTS = [100, 200, 300, 500] as const;

export default function LifeScreen() {
  useScreenTimer('life');
  const loop = useGameplayLoop();
  const onboarding = useOnboarding();
  const stats = loop.dashboard?.stats;
  const cash = stats?.cash_xgp ?? 0;
  const stress = stats?.stress ?? 0;
  const health = stats?.health ?? 100;
  const debt = loop.expenseDebt?.debtAmount ?? stats?.debt_xgp ?? 0;
  const currentHousing = (stats?.region_key ?? 'suburban') as 'suburban' | 'downtown';

  const [loanAmount, setLoanAmount] = useState<100 | 200 | 300 | 500>(100);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const busy = loop.executingAction || busyAction !== null;

  async function handleEat(mealType: 'breakfast' | 'lunch' | 'dinner') {
    if (busy) return;
    setBusyAction(`eat_${mealType}`);
    await loop.eatMeal(mealType);
    setBusyAction(null);
  }

  async function handleLoan() {
    if (busy) return;
    setBusyAction('loan');
    await loop.takeLoan(loanAmount);
    setBusyAction(null);
  }

  async function handleHousing(housingType: 'suburban' | 'downtown') {
    if (busy || housingType === currentHousing) return;
    setBusyAction(`housing_${housingType}`);
    await loop.selectHousing(housingType);
    setBusyAction(null);
  }

  const loanRepay = Math.round(loanAmount * 1.15);

  return (
    <GameplayLoopScaffold
      title="Life"
      subtitle="Housing, food, and emergency loans"
      activeNavKey="life"
      footer={(
        <GameplayStickyActionArea
          secondaryLabel="Open Dashboard"
          onSecondaryPress={() => onboarding.navigateTo('dashboard')}
          primaryLabel="Back To Work"
          onPrimaryPress={() => onboarding.navigateTo('work')}
        />
      )}
    >
      {/* ── Health & Stress ── */}
      {stats ? (
        <GameplaySummaryCard eyebrow="Your condition" title="Health &amp; Stress">
          <GameplayCompactMetricRows
            items={[
              { label: 'Health', value: `${Math.round(health)}`, tone: health >= 65 ? 'positive' : 'warning' },
              { label: 'Stress', value: `${Math.round(stress)}`, tone: stress >= 65 ? 'danger' : 'warning' },
              { label: 'Cash', value: formatMoney(cash), tone: cash >= 50 ? 'positive' : 'danger' },
              { label: 'Debt', value: formatMoney(debt), tone: debt > 0 ? 'warning' : 'positive' },
            ]}
          />
        </GameplaySummaryCard>
      ) : null}

      {/* ── Food ── */}
      <GameplaySummaryCard
        eyebrow="Food"
        title="Eat a Meal"
        subtitle="Each meal costs 6 XGP, restores +5 health, and reduces stress by 3."
      >
        {cash < 6 ? (
          <GameplayWarningBanner
            title="Not enough cash"
            message="You need at least 6 XGP to buy a meal."
            tone="danger"
          />
        ) : null}
        <View style={styles.buttonRow}>
          <View style={styles.mealBtn}>
            <PrimaryButton
              label={busyAction === 'eat_breakfast' ? 'Eating...' : 'Breakfast  (−6 XGP)'}
              onPress={() => void handleEat('breakfast')}
              disabled={busy || cash < 6}
            />
          </View>
          <View style={styles.mealBtn}>
            <SecondaryButton
              label={busyAction === 'eat_lunch' ? 'Eating...' : 'Lunch  (−6 XGP)'}
              onPress={() => void handleEat('lunch')}
              disabled={busy || cash < 6}
            />
          </View>
          <View style={styles.mealBtn}>
            <SecondaryButton
              label={busyAction === 'eat_dinner' ? 'Eating...' : 'Dinner  (−6 XGP)'}
              onPress={() => void handleEat('dinner')}
              disabled={busy || cash < 6}
            />
          </View>
        </View>
      </GameplaySummaryCard>

      {/* ── Housing ── */}
      <GameplaySummaryCard
        eyebrow="Housing"
        title="Where You Live"
        subtitle="Your neighbourhood affects rent, transport costs, and weekly stress."
      >
        <View style={styles.housingGrid}>
          {(['suburban', 'downtown'] as const).map((key) => {
            const info = HOUSING_INFO[key];
            const isActive = currentHousing === key;
            return (
              <View key={key} style={[styles.housingCard, isActive ? styles.housingCardActive : null]}>
                <Text style={styles.housingLabel}>{info.label}</Text>
                <Text style={styles.housingMeta}>Rent: {info.rent} XGP/wk</Text>
                <Text style={styles.housingMeta}>Gas:  {info.gas} XGP/wk</Text>
                <Text style={[styles.housingStress, info.stressMod < 0 ? styles.textPositive : styles.textWarning]}>
                  {info.stressNote}
                </Text>
                {isActive ? (
                  <Text style={styles.activeLabel}>Current home</Text>
                ) : (
                  <View style={styles.housingBtnWrap}>
                    <SecondaryButton
                      label={busyAction === `housing_${key}` ? 'Moving...' : `Move here`}
                      onPress={() => void handleHousing(key)}
                      disabled={busy}
                    />
                  </View>
                )}
              </View>
            );
          })}
        </View>
      </GameplaySummaryCard>

      {/* ── Loans ── */}
      <GameplaySummaryCard
        eyebrow="Emergency Money"
        title="Quick Loan"
        subtitle="Borrow cash now and repay 15% more. Use only when you have no other options."
      >
        {debt > 200 ? (
          <GameplayWarningBanner
            title="You already have significant debt"
            message={`Current debt: ${formatMoney(debt)}. Every loan adds more — try earning first.`}
            tone="warning"
          />
        ) : null}
        <Text style={styles.loanHelp}>Pick an amount:</Text>
        <View style={styles.loanAmountRow}>
          {LOAN_AMOUNTS.map((amt) => {
            const active = loanAmount === amt;
            return (
              <View key={amt} style={styles.loanAmtBtn}>
                {active ? (
                  <PrimaryButton
                    label={`${amt} XGP`}
                    onPress={() => setLoanAmount(amt)}
                    disabled={busy}
                  />
                ) : (
                  <SecondaryButton
                    label={`${amt} XGP`}
                    onPress={() => setLoanAmount(amt)}
                    disabled={busy}
                  />
                )}
              </View>
            );
          })}
        </View>
        <Text style={styles.loanRepayNote}>
          You will receive {loanAmount} XGP and owe {loanRepay} XGP (+15% flat).
        </Text>
        <View style={styles.loanConfirmBtn}>
          <PrimaryButton
            label={busyAction === 'loan' ? 'Borrowing...' : `Borrow ${loanAmount} XGP`}
            onPress={() => void handleLoan()}
            disabled={busy}
          />
        </View>
      </GameplaySummaryCard>
    </GameplayLoopScaffold>
  );
}

const styles = StyleSheet.create({
  buttonRow: {
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  mealBtn: {
    flex: 1,
  },
  housingGrid: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.sm,
  },
  housingCard: {
    flex: 1,
    backgroundColor: theme.color.surface,
    borderRadius: theme.radius.md,
    borderWidth: 2,
    borderColor: theme.color.border,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  housingCardActive: {
    borderColor: theme.color.accent,
  },
  housingLabel: {
    ...theme.typography.headingSm,
    color: theme.color.textPrimary,
    marginBottom: theme.spacing.xs,
  },
  housingMeta: {
    ...theme.typography.bodyMd,
    color: theme.color.textSecondary,
  },
  housingStress: {
    ...theme.typography.bodyMd,
    fontWeight: '600',
    marginTop: theme.spacing.xs,
  },
  textPositive: {
    color: theme.color.positive,
  },
  textWarning: {
    color: theme.color.warning,
  },
  activeLabel: {
    ...theme.typography.label,
    color: theme.color.accent,
    marginTop: theme.spacing.sm,
    textAlign: 'center',
  },
  housingBtnWrap: {
    marginTop: theme.spacing.sm,
  },
  loanHelp: {
    ...theme.typography.bodyMd,
    color: theme.color.textSecondary,
    marginBottom: theme.spacing.xs,
  },
  loanAmountRow: {
    flexDirection: 'row',
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
  },
  loanAmtBtn: {
    flex: 1,
  },
  loanRepayNote: {
    ...theme.typography.bodyMd,
    color: theme.color.warning,
    marginBottom: theme.spacing.sm,
    fontStyle: 'italic',
  },
  loanConfirmBtn: {
    marginTop: theme.spacing.xs,
  },
});
