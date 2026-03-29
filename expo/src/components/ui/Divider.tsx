import React from 'react';
import { StyleSheet, View } from 'react-native';

import { theme } from '@/design/theme';

export default function Divider() {
  return <View style={styles.line} />;
}

const styles = StyleSheet.create({
  line: {
    width: '100%',
    borderBottomWidth: 1,
    borderBottomColor: theme.color.border,
    marginVertical: theme.spacing.xs,
  },
});
