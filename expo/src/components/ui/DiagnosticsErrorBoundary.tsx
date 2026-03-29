import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '@/design/theme';
import { recordError } from '@/lib/logger';

type Props = {
  children: React.ReactNode;
};

type State = {
  hasError: boolean;
  errorMessage: string;
};

export default class DiagnosticsErrorBoundary extends React.Component<Props, State> {
  state: State = {
    hasError: false,
    errorMessage: '',
  };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      errorMessage: error?.message || 'Unexpected app error.',
    };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    recordError('app.render', 'Unhandled render error.', {
      action: 'error_boundary',
      error,
      context: {
        componentStack: info.componentStack
          ?.split('\n')
          .map((line) => line.trim())
          .filter(Boolean)
          .slice(0, 4),
      },
    });
  }

  private handleRetry = () => {
    this.setState({ hasError: false, errorMessage: '' });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <View style={styles.container}>
        <View style={styles.card}>
          <Text style={styles.title}>App error</Text>
          <Text style={styles.message}>
            {this.state.errorMessage || 'Something went wrong while loading Gold Penny.'}
          </Text>
          <Text style={styles.note}>
            Recent diagnostics are available in Settings after the app recovers.
          </Text>
          <Pressable accessibilityRole="button" onPress={this.handleRetry} style={styles.button}>
            <Text style={styles.buttonLabel}>Try again</Text>
          </Pressable>
        </View>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.lg,
    backgroundColor: theme.color.background,
  },
  card: {
    borderRadius: theme.radius.lg,
    padding: theme.spacing.lg,
    backgroundColor: theme.color.surface,
    borderWidth: 1,
    borderColor: theme.color.border,
    gap: theme.spacing.sm,
  },
  title: {
    color: theme.color.textPrimary,
    ...theme.typography.headingSm,
    fontWeight: '800',
  },
  message: {
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
  },
  note: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  button: {
    marginTop: theme.spacing.sm,
    minHeight: 44,
    borderRadius: theme.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.color.textPrimary,
    paddingHorizontal: theme.spacing.md,
  },
  buttonLabel: {
    color: theme.color.background,
    ...theme.typography.bodyMd,
    fontWeight: '700',
  },
});
