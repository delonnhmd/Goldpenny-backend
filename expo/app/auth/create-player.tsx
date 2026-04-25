import React, { useEffect, useMemo, useState } from 'react';
import { Redirect, router } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { getAuthErrorMessage, useAuth } from '@/features/auth';
import { AuthField, AuthShell, authScreenStyles } from '@/features/auth/AuthShell';
import { SignupQuestionAnswers, SignupQuestionKey } from '@/types/auth';

function suggestedDisplayName(email: string | null | undefined): string {
  const localPart = String(email || '').split('@', 1)[0] || '';
  const normalized = localPart.replace(/[._-]+/g, ' ').trim();
  return normalized || 'Gold Penny Player';
}

interface QuestionOption {
  key: string;
  label: string;
  impact: string;
}

interface QuestionDefinition {
  key: SignupQuestionKey;
  title: string;
  body: string;
  options: QuestionOption[];
}

const QUESTION_DEFINITIONS: QuestionDefinition[] = [
  {
    key: 'risk_tolerance',
    title: 'Risk Tolerance',
    body: 'How do you usually handle uncertain money moves?',
    options: [
      { key: 'cautious', label: 'Play Safe', impact: 'More cash discipline, less pressure.' },
      { key: 'balanced', label: 'Stay Balanced', impact: 'Stable middle-ground start.' },
      { key: 'bold', label: 'Take Chances', impact: 'More swing, more pressure, more edge.' },
    ],
  },
  {
    key: 'work_ethic',
    title: 'Work Ethic',
    body: 'What does your default grind mode feel like?',
    options: [
      { key: 'steady', label: 'Steady Shift', impact: 'Reliable productivity with lower strain.' },
      { key: 'grinder', label: 'Full Grind', impact: 'Higher output, more stress and wear.' },
      { key: 'clock_out', label: 'Protect Energy', impact: 'Lower strain, slower momentum.' },
    ],
  },
  {
    key: 'spending_behavior',
    title: 'Spending Style',
    body: 'When money is tight, what is your instinct?',
    options: [
      { key: 'stretch_every_coin', label: 'Stretch It', impact: 'Better cash and debt control.' },
      { key: 'balanced', label: 'Mix It', impact: 'Even-handed starting profile.' },
      { key: 'spend_freely', label: 'Spend Fast', impact: 'Less cash cushion, more debt drag.' },
    ],
  },
  {
    key: 'health_habits',
    title: 'Health Habits',
    body: 'How are you taking care of yourself lately?',
    options: [
      { key: 'disciplined', label: 'Locked In', impact: 'Better health and stress tolerance.' },
      { key: 'mixed', label: 'Up And Down', impact: 'Neutral baseline.' },
      { key: 'rough_patch', label: 'Rough Patch', impact: 'Lower resilience at the start.' },
    ],
  },
  {
    key: 'education_background',
    title: 'Education',
    body: 'What kind of learning background fits you best?',
    options: [
      { key: 'self_taught', label: 'Self Taught', impact: 'Fast practical learning, lean resources.' },
      { key: 'high_school', label: 'High School', impact: 'Plain survival start.' },
      { key: 'college', label: 'College Debt', impact: 'More upside, more debt pressure.' },
    ],
  },
  {
    key: 'hustle_preference',
    title: 'Hustle Lane',
    body: 'Which lane sounds most natural on Day 1?',
    options: [
      { key: 'hands_on', label: 'Hands-On', impact: 'Better manual-work start.' },
      { key: 'service', label: 'Service', impact: 'Better people-facing survival start.' },
      { key: 'sales', label: 'Sales', impact: 'Higher social upside, more pressure.' },
    ],
  },
];

export default function CreatePlayerScreen() {
  const auth = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [answers, setAnswers] = useState<SignupQuestionAnswers>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (displayName.trim()) return;
    setDisplayName(suggestedDisplayName(auth.session?.account.email));
  }, [auth.session?.account.email, displayName]);

  const answeredCount = useMemo(
    () => QUESTION_DEFINITIONS.filter((question) => Boolean(answers[question.key])).length,
    [answers],
  );
  const allAnswered = answeredCount === QUESTION_DEFINITIONS.length;
  const canSubmit = displayName.trim().length > 0 && allAnswered && !submitting;

  if (auth.status === 'loading') {
    return (
      <AuthShell
        title="Gold Penny"
        subtitle="Restoring your account"
        cardTitle="Loading"
        cardSummary="Checking whether this account already has a linked player profile."
      >
        <Text style={authScreenStyles.helperText}>One moment while we verify your Day 1 setup state.</Text>
      </AuthShell>
    );
  }

  if (!auth.isAuthenticated || !auth.session) {
    return <Redirect href="/auth/login" />;
  }

  if (auth.hasPlayerProfile) {
    return <Redirect href="/gameplay" />;
  }

  const handleAnswer = (questionKey: SignupQuestionKey, optionKey: string) => {
    setAnswers((current) => ({
      ...current,
      [questionKey]: optionKey,
    }));
  };

  const handleCreatePlayer = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await auth.createPlayerProfile({
        display_name: displayName.trim(),
        signup_answers: answers,
      });
      router.replace('/gameplay');
    } catch (nextError) {
      setError(getAuthErrorMessage(nextError));
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = async () => {
    await auth.signOut();
    router.replace('/auth/login');
  };

  return (
    <AuthShell
      title="Gold Penny"
      subtitle="Build your Day 1 survival profile"
      cardTitle="Create New Player"
      cardSummary="Answer six quick questions to shape a rough starting hand: low cash, debt pressure, no premium job access, and a starter grind lane."
    >
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Text style={authScreenStyles.helperText}>
          This setup is intentionally short. Your answers tilt starting stress, cash, debt, productivity, learning momentum, and early social upside, but they do not lock your future.
        </Text>

        <View style={styles.summaryCard}>
          <Text style={styles.summaryEyebrow}>Day 1 Rules</Text>
          <Text style={styles.summaryTitle}>You start under pressure</Text>
          <Text style={styles.summaryBody}>
            Expect a tight wallet, some debt, low status, no premium jobs, and a starter work lane built around survival roles.
          </Text>
          <Text style={styles.summaryMeta}>
            Questions answered: {answeredCount}/{QUESTION_DEFINITIONS.length}
          </Text>
        </View>

        <AuthField
          label="Display Name"
          value={displayName}
          onChangeText={setDisplayName}
          placeholder="Your player name"
          autoCapitalize="words"
          editable={!submitting}
        />

        {QUESTION_DEFINITIONS.map((question) => {
          const selected = answers[question.key] || null;
          return (
            <View key={question.key} style={styles.questionCard}>
              <Text style={styles.questionTitle}>{question.title}</Text>
              <Text style={styles.questionBody}>{question.body}</Text>
              <View style={styles.optionList}>
                {question.options.map((option) => {
                  const isSelected = selected === option.key;
                  return (
                    <Pressable
                      key={option.key}
                      accessibilityRole="button"
                      onPress={() => handleAnswer(question.key, option.key)}
                      style={({ pressed }) => [
                        styles.optionCard,
                        isSelected ? styles.optionCardSelected : null,
                        pressed ? styles.optionCardPressed : null,
                      ]}
                    >
                      <Text style={[styles.optionLabel, isSelected ? styles.optionLabelSelected : null]}>
                        {option.label}
                      </Text>
                      <Text style={[styles.optionImpact, isSelected ? styles.optionImpactSelected : null]}>
                        {option.impact}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          );
        })}

        <Text style={authScreenStyles.helperText}>Account: {auth.session.account.email}</Text>
        <Text style={authScreenStyles.helperText}>
          Already created this account on another device? Log in with that email and Gold Penny will restore the linked player instead of creating a new one.
        </Text>
        {error ? <Text selectable style={authScreenStyles.errorText}>{error}</Text> : null}

        <PrimaryButton
          label={submitting ? 'Creating Survival Profile...' : 'Create Survival Profile'}
          onPress={canSubmit ? handleCreatePlayer : undefined}
          loading={submitting}
          disabled={!canSubmit}
          style={authScreenStyles.fullWidthButton}
        />
        <SecondaryButton
          label="Log Out"
          onPress={submitting ? undefined : handleLogout}
          disabled={submitting}
          style={authScreenStyles.fullWidthButton}
        />
      </ScrollView>
    </AuthShell>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    maxHeight: 620,
  },
  content: {
    gap: theme.spacing.md,
    paddingBottom: theme.spacing.xs,
  },
  summaryCard: {
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    backgroundColor: theme.ui.bg.card,
    borderWidth: 1,
    borderColor: theme.ui.warning,
    gap: theme.spacing.xxs,
  },
  summaryEyebrow: {
    ...theme.typography.caption,
    color: theme.ui.warning,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '800',
  },
  summaryTitle: {
    ...theme.typography.bodyLg,
    color: theme.ui.text.onDark,
    fontWeight: '800',
  },
  summaryBody: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onDarkMuted,
  },
  summaryMeta: {
    ...theme.typography.caption,
    color: theme.ui.warning,
    fontWeight: '700',
  },
  questionCard: {
    borderRadius: theme.radius.lg,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    backgroundColor: theme.color.surfaceAlt,
    borderWidth: 1,
    borderColor: theme.color.border,
    gap: theme.spacing.sm,
  },
  questionTitle: {
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    fontWeight: '800',
  },
  questionBody: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  optionList: {
    gap: theme.spacing.xs,
  },
  optionCard: {
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.color.border,
    backgroundColor: theme.color.surface,
    gap: 4,
  },
  optionCardSelected: {
    borderColor: theme.ui.action,
    backgroundColor: theme.ui.bg.cardRaised,
  },
  optionCardPressed: {
    opacity: 0.85,
  },
  optionLabel: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
  },
  optionLabelSelected: {
    color: theme.ui.text.onDark,
  },
  optionImpact: {
    ...theme.typography.caption,
    color: theme.color.textSecondary,
  },
  optionImpactSelected: {
    color: theme.ui.action,
  },
});
