import React, { useEffect, useMemo, useRef } from 'react';
import {
  Animated,
  Modal,
  Pressable,
  StyleProp,
  StyleSheet,
  View,
  ViewStyle,
} from 'react-native';

import { motion, useReducedMotion } from '@/design/motion';
import { theme } from '@/design/theme';
import { useBreakpoint } from '@/hooks/useBreakpoint';
import { recordInfo } from '@/lib/logger';

type PanelMode = 'sheet' | 'center';

export default function SlideUpPanel({
  visible,
  onClose,
  children,
  mode,
  contentStyle,
}: {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
  mode?: PanelMode;
  contentStyle?: StyleProp<ViewStyle>;
}) {
  const reduced = useReducedMotion();
  const { isMobile } = useBreakpoint();
  const resolvedMode: PanelMode = mode || (isMobile ? 'sheet' : 'center');

  const opacity = useRef(new Animated.Value(0)).current;
  const translate = useRef(new Animated.Value(24)).current;
  const diagnosticsEnabled =
    __DEV__
    || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === 'true'
    || process.env.EXPO_PUBLIC_INTERACTION_DIAGNOSTICS === '1';

  useEffect(() => {
    if (!visible) {
      opacity.setValue(0);
      translate.setValue(24);
      return;
    }

    if (reduced) {
      opacity.setValue(1);
      translate.setValue(0);
      return;
    }

    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: motion.duration.fast,
        easing: motion.easing.standard,
        useNativeDriver: true,
      }),
      Animated.timing(translate, {
        toValue: 0,
        duration: motion.duration.base,
        easing: motion.easing.emphasized,
        useNativeDriver: true,
      }),
    ]).start();
  }, [opacity, reduced, translate, visible]);

  const panelContainerStyle = useMemo(
    () => [
      resolvedMode === 'sheet' ? styles.sheetPanel : styles.centerPanel,
      contentStyle,
    ],
    [contentStyle, resolvedMode],
  );

  const panelAnimatedStyle = useMemo(
    () => [
      styles.panelAnimated,
      {
        opacity,
        transform: [{ translateY: translate }],
      },
    ],
    [opacity, translate],
  );

  const bodyStyle = resolvedMode === 'sheet' ? styles.sheetBody : styles.centerBody;

  useEffect(() => {
    if (!diagnosticsEnabled) return;
    recordInfo('ui.slideUpPanel', 'SlideUpPanel render mode updated.', {
      action: 'render_mode',
      context: {
        visible,
        resolvedMode,
        animationWrapperActive: true,
        maxHeightMovedToStaticContainer: true,
      },
    });
  }, [diagnosticsEnabled, resolvedMode, visible]);

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={onClose}>
      <View style={styles.backdropWrap}>
        <Pressable style={styles.backdropHit} onPress={onClose} />
        <View style={bodyStyle}>
          <View style={panelContainerStyle}>
            <Animated.View style={panelAnimatedStyle}>{children}</Animated.View>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdropWrap: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.55)',
  },
  backdropHit: {
    ...StyleSheet.absoluteFillObject,
  },
  centerBody: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.xl,
  },
  sheetBody: {
    flex: 1,
    justifyContent: 'flex-end',
    paddingHorizontal: theme.spacing.sm,
    paddingBottom: theme.spacing.sm,
  },
  panelAnimated: {
    width: '100%',
    borderWidth: 1,
    borderColor: theme.color.border,
    backgroundColor: theme.color.surface,
    overflow: 'hidden',
    ...theme.shadow.lg,
  },
  centerPanel: {
    width: '100%',
    maxWidth: 760,
    maxHeight: '90%',
    borderRadius: theme.radius.xl,
    overflow: 'hidden',
  },
  sheetPanel: {
    width: '100%',
    maxHeight: '88%',
    borderRadius: theme.radius.xl,
    overflow: 'hidden',
  },
});
