import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { recordInfo } from '@/lib/logger';
import { theme } from '@/design/theme';

export default function ExpandCollapseView({
  expanded,
  children,
  maxHeight = 2200,
}: {
  expanded: boolean;
  children: React.ReactNode;
  maxHeight?: number;
}) {
  const diagnosticsEnabled =
    __DEV__
    || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
    || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

  useEffect(() => {
    if (!diagnosticsEnabled) return;
    recordInfo('ui.expandCollapse', 'ExpandCollapseView rendered in native-safe plain mode.', {
      action: 'render_mode',
      context: {
        expanded,
        fallbackPlainContainer: true,
        animationWrapperActive: false,
        requestedMaxHeight: maxHeight,
      },
    });
  }, [diagnosticsEnabled, expanded, maxHeight]);

  if (!expanded) return null;

  return <View style={styles.content}>{children}</View>;
}

const styles = StyleSheet.create({
  content: {
    gap: theme.spacing.sm,
    paddingTop: theme.spacing.sm,
  },
});
