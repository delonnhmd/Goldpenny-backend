// Gold Penny — Soft Launch: IssueReportSheet
// Quick in-game bug / friction report form.

import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { theme } from '@/design/theme';

import { IssueCategory, IssueSeverity, IssuePayload } from './types';

interface Props {
  visible: boolean;
  gameDay?: number;
  sessionId?: string;
  onSubmit: (payload: IssuePayload) => Promise<boolean>;
  onDismiss: () => void;
}

const CATEGORIES: { key: IssueCategory; label: string }[] = [
  { key: 'bug', label: 'Bug' },
  { key: 'friction', label: 'Friction' },
  { key: 'ui', label: 'UI' },
  { key: 'balance', label: 'Balance' },
  { key: 'other', label: 'Other' },
];

const SEVERITIES: { key: IssueSeverity; label: string }[] = [
  { key: 'low', label: 'Low' },
  { key: 'medium', label: 'Medium' },
  { key: 'high', label: 'High' },
  { key: 'blocker', label: 'Blocker' },
];

export function IssueReportSheet({ visible, gameDay, sessionId, onSubmit, onDismiss }: Props) {
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<IssueCategory | null>(null);
  const [severity, setSeverity] = useState<IssueSeverity>('medium');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit() {
    if (!description.trim() || submitting) return;
    setSubmitting(true);
    const ok = await onSubmit({
      session_id: sessionId,
      game_day: gameDay,
      description: description.trim(),
      category: category ?? undefined,
      severity,
    });
    setSubmitting(false);
    if (ok) {
      setDone(true);
      setTimeout(onDismiss, 1200);
    }
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onDismiss}
    >
      <TouchableOpacity style={styles.overlay} onPress={onDismiss} activeOpacity={1} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.sheetContainer}
      >
        <View style={styles.sheet}>
          <View style={styles.handle} />

          {done ? (
            <View style={styles.doneContainer}>
              <Text style={styles.doneText}>Issue reported — thanks!</Text>
            </View>
          ) : (
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              <Text style={styles.title}>Report an Issue</Text>

              {/* Category chips */}
              <Text style={styles.sectionLabel}>Category</Text>
              <View style={styles.chipRow}>
                {CATEGORIES.map(({ key, label }) => (
                  <TouchableOpacity
                    key={key}
                    style={[styles.chip, category === key && styles.chipActive]}
                    onPress={() => setCategory(key)}
                    activeOpacity={0.7}
                  >
                    <Text style={[styles.chipLabel, category === key && styles.chipLabelActive]}>
                      {label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Severity */}
              <Text style={styles.sectionLabel}>Severity</Text>
              <View style={styles.chipRow}>
                {SEVERITIES.map(({ key, label }) => (
                  <TouchableOpacity
                    key={key}
                    style={[styles.chip, severity === key && styles.chipActive]}
                    onPress={() => setSeverity(key)}
                    activeOpacity={0.7}
                  >
                    <Text style={[styles.chipLabel, severity === key && styles.chipLabelActive]}>
                      {label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Description */}
              <Text style={styles.sectionLabel}>Describe the issue</Text>
              <TextInput
                style={styles.textInput}
                placeholder="What happened? What did you expect?"
                placeholderTextColor={theme.color.muted}
                multiline
                maxLength={2000}
                value={description}
                onChangeText={setDescription}
                textAlignVertical="top"
              />

              <TouchableOpacity
                style={[styles.submitButton, (!description.trim() || submitting) && styles.submitDisabled]}
                onPress={handleSubmit}
                disabled={!description.trim() || submitting}
                activeOpacity={0.75}
              >
                {submitting ? (
                  <ActivityIndicator color="#ffffff" size="small" />
                ) : (
                  <Text style={styles.submitLabel}>Send Report</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity style={styles.skipButton} onPress={onDismiss}>
                <Text style={styles.skipLabel}>Cancel</Text>
              </TouchableOpacity>
            </ScrollView>
          )}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  sheetContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
  },
  sheet: {
    backgroundColor: theme.color.surface,
    borderTopLeftRadius: theme.radius.xl,
    borderTopRightRadius: theme.radius.xl,
    padding: theme.spacing.xxl,
    maxHeight: '90%',
    ...theme.shadow.lg,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: theme.radius.pill,
    backgroundColor: theme.color.border,
    marginBottom: theme.spacing.lg,
  },
  title: {
    ...theme.typography.headingMd,
    color: theme.color.textPrimary,
    marginBottom: theme.spacing.lg,
  },
  sectionLabel: {
    ...theme.typography.label,
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: theme.spacing.xs,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.xs,
    marginBottom: theme.spacing.lg,
  },
  chip: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    borderColor: theme.color.border,
  },
  chipActive: {
    backgroundColor: theme.color.accent,
    borderColor: theme.color.accent,
  },
  chipLabel: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondary,
  },
  chipLabelActive: {
    color: '#ffffff',
    fontWeight: '700',
  },
  textInput: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    minHeight: 100,
    marginBottom: theme.spacing.lg,
  },
  submitButton: {
    backgroundColor: theme.color.accent,
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
    marginBottom: theme.spacing.sm,
  },
  submitDisabled: {
    opacity: 0.45,
  },
  submitLabel: {
    ...theme.typography.headingSm,
    color: '#ffffff',
  },
  skipButton: {
    alignItems: 'center',
    paddingVertical: theme.spacing.sm,
  },
  skipLabel: {
    ...theme.typography.bodyMd,
    color: theme.color.muted,
  },
  doneContainer: {
    alignItems: 'center',
    paddingVertical: theme.spacing.xxl,
  },
  doneText: {
    ...theme.typography.headingMd,
    color: theme.color.positive,
  },
});
