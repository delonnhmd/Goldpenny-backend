import React from 'react';
import { StyleSheet, Text } from 'react-native';

import ActionRow from '@/components/ui/ActionRow';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SurfaceCard from '@/components/ui/SurfaceCard';
import { theme } from '@/design/theme';

export default function ErrorStateCard({
  title = 'Failed to load',
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <SurfaceCard variant="warning">
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message || 'Please try refreshing this section.'}</Text>
      {onRetry ? (
        <ActionRow>
          <PrimaryButton label="Retry" onPress={onRetry} />
        </ActionRow>
      ) : null}
    </SurfaceCard>
  );
}

const styles = StyleSheet.create({
  title: {
    color: '#92400e',
    ...theme.typography.headingSm,
  },
  message: {
    color: '#78350f',
    ...theme.typography.bodySm,
  },
});
