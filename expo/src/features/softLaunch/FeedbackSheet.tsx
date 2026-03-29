// Gold Penny — Soft Launch: FeedbackSheet
// Modal bottom sheet shown after Day 1 or Day 2 settlement.
// Rating: 1–5 stars.  Three optional short-text questions.

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

import { FeedbackPayload } from './types';

interface Props {
  visible: boolean;
  gameDay: number;
  sessionId?: string;
  onSubmit: (payload: FeedbackPayload) => Promise<boolean>;
  onDismiss: () => void;
}

export function FeedbackSheet({ visible, gameDay, sessionId, onSubmit, onDismiss }: Props) {
  const [rating, setRating] = useState(0);
  const [confusing, setConfusing] = useState('');
  const [hard, setHard] = useState('');
  const [interesting, setInteresting] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit() {
    if (rating === 0 || submitting) return;
    setSubmitting(true);
    const ok = await onSubmit({
      session_id: sessionId,
      game_day: gameDay,
      rating,
      response_confusing: confusing.trim() || undefined,
      response_hard: hard.trim() || undefined,
      response_interesting: interesting.trim() || undefined,
    });
    setSubmitting(false);
    if (ok) {
      setDone(true);
      setTimeout(onDismiss, 1200);
    }
  }

  function handleDismiss() {
    if (submitting) return;
    onDismiss();
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={handleDismiss}
    >
      <TouchableOpacity style={styles.overlay} onPress={handleDismiss} activeOpacity={1} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.sheetContainer}
      >
        <View style={styles.sheet}>
          <View style={styles.handle} />

          {done ? (
            <View style={styles.doneContainer}>
              <Text style={styles.doneText}>Thanks for your feedback!</Text>
            </View>
          ) : (
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              <Text style={styles.title}>How was Day {gameDay}?</Text>
              <Text style={styles.subtitle}>Your feedback shapes the game.</Text>

              {/* Star rating */}
              <View style={styles.starsRow}>
                {[1, 2, 3, 4, 5].map((star) => (
                  <TouchableOpacity
                    key={star}
                    onPress={() => setRating(star)}
                    style={styles.starButton}
                    activeOpacity={0.7}
                  >
                    <Text style={[styles.star, rating >= star && styles.starActive]}>★</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={styles.questionLabel}>What felt confusing?</Text>
              <TextInput
                style={styles.textInput}
                placeholder="Anything hard to understand..."
                placeholderTextColor={theme.color.muted}
                multiline
                maxLength={400}
                value={confusing}
                onChangeText={setConfusing}
              />

              <Text style={styles.questionLabel}>What felt hard?</Text>
              <TextInput
                style={styles.textInput}
                placeholder="Anything that felt too difficult..."
                placeholderTextColor={theme.color.muted}
                multiline
                maxLength={400}
                value={hard}
                onChangeText={setHard}
              />

              <Text style={styles.questionLabel}>What was interesting?</Text>
              <TextInput
                style={styles.textInput}
                placeholder="What kept you engaged?"
                placeholderTextColor={theme.color.muted}
                multiline
                maxLength={400}
                value={interesting}
                onChangeText={setInteresting}
              />

              <TouchableOpacity
                style={[styles.submitButton, (rating === 0 || submitting) && styles.submitDisabled]}
                onPress={handleSubmit}
                disabled={rating === 0 || submitting}
                activeOpacity={0.75}
              >
                {submitting ? (
                  <ActivityIndicator color="#ffffff" size="small" />
                ) : (
                  <Text style={styles.submitLabel}>Submit Feedback</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity style={styles.skipButton} onPress={handleDismiss}>
                <Text style={styles.skipLabel}>Skip for now</Text>
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
    marginBottom: theme.spacing.xs,
  },
  subtitle: {
    ...theme.typography.bodyMd,
    color: theme.color.textSecondary,
    marginBottom: theme.spacing.lg,
  },
  starsRow: {
    flexDirection: 'row',
    marginBottom: theme.spacing.xl,
  },
  starButton: {
    marginRight: theme.spacing.sm,
  },
  star: {
    fontSize: 32,
    color: theme.color.border,
  },
  starActive: {
    color: '#f59e0b',
  },
  questionLabel: {
    ...theme.typography.label,
    color: theme.color.textSecondary,
    marginBottom: theme.spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  textInput: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    ...theme.typography.bodyMd,
    color: theme.color.textPrimary,
    minHeight: 64,
    marginBottom: theme.spacing.lg,
    textAlignVertical: 'top',
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
