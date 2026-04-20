import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import SectionCard from '@/components/ui/SectionCard';
import { theme } from '@/design/theme';

export function AuthShell({
  title,
  subtitle,
  cardTitle,
  cardSummary,
  children,
}: {
  title: string;
  subtitle: string;
  cardTitle: string;
  cardSummary: string;
  children: React.ReactNode;
}) {
  return (
    <AppShell title={title} subtitle={subtitle}>
      <PageContainer>
        <ContentStack style={styles.content}>
          <SectionCard title={cardTitle} summary={cardSummary}>
            {children}
          </SectionCard>
        </ContentStack>
      </PageContainer>
    </AppShell>
  );
}

export function AuthField({
  label,
  value,
  onChangeText,
  placeholder,
  secureTextEntry,
  autoCapitalize = 'none',
  autoCorrect = false,
  keyboardType,
  editable = true,
}: {
  label: string;
  value: string;
  onChangeText: (next: string) => void;
  placeholder: string;
  secureTextEntry?: boolean;
  autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
  autoCorrect?: boolean;
  keyboardType?: 'default' | 'email-address' | 'numeric' | 'url';
  editable?: boolean;
}) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.inputLabel}>{label}</Text>
      <TextInput
        style={styles.input}
        placeholder={placeholder}
        placeholderTextColor={theme.color.muted}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secureTextEntry}
        autoCapitalize={autoCapitalize}
        autoCorrect={autoCorrect}
        keyboardType={keyboardType}
        editable={editable}
      />
    </View>
  );
}

export const authScreenStyles = StyleSheet.create({
  helperText: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  successText: {
    color: theme.ui.positive,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  errorText: {
    color: theme.color.danger,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  buttonRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  fullWidthButton: {
    width: '100%',
  },
});

const styles = StyleSheet.create({
  content: {
    paddingTop: theme.spacing.xl,
  },
  fieldGroup: {
    gap: theme.spacing.xs,
  },
  inputLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  input: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    backgroundColor: theme.color.surfaceAlt,
    minHeight: 44,
  },
});
