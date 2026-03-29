import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';

import ActionRow from './ActionRow';
import PrimaryButton from './PrimaryButton';
import SurfaceCard from './SurfaceCard';

export default function ErrorStateView({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <SurfaceCard variant="warning">
      <View style={styles.wrap}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.message}>{message || 'Try refreshing this section.'}</Text>
        {onRetry ? (
          <ActionRow>
            <PrimaryButton label="Retry" onPress={onRetry} />
          </ActionRow>
        ) : null}
      </View>
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: theme.spacing.sm,
  },
  title: {
    color: '#92400e',
    ...theme.typography.headingSm,
  },
  message: {
    color: '#78350f',
    ...theme.typography.bodySm,
  },
});
