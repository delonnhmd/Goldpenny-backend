import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  PanResponder,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';

import { alpha, theme } from '@/design/theme';

interface MapDetailSheetProps {
  visible: boolean;
  title: string;
  subtitle?: string | null;
  onClose: () => void;
  children: React.ReactNode;
}

const CLOSE_DISTANCE = 120;
const CLOSE_VELOCITY = 0.9;

export default function MapDetailSheet({
  visible,
  title,
  subtitle,
  onClose,
  children,
}: MapDetailSheetProps) {
  const { height } = useWindowDimensions();
  const [mounted, setMounted] = useState(visible);
  const translateY = useRef(new Animated.Value(420)).current;

  const hiddenOffset = useMemo(
    () => Math.max(height * 0.8, 420),
    [height],
  );
  const maxHeight = useMemo(
    () => Math.min(Math.max(height * 0.72, 360), 680),
    [height],
  );

  useEffect(() => {
    if (visible) {
      setMounted(true);
      translateY.setValue(hiddenOffset);
      Animated.spring(translateY, {
        toValue: 0,
        useNativeDriver: true,
        damping: 24,
        stiffness: 260,
        mass: 0.9,
      }).start();
      return;
    }

    if (!mounted) return;

    Animated.timing(translateY, {
      toValue: hiddenOffset,
      duration: 180,
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (finished) {
        setMounted(false);
      }
    });
  }, [hiddenOffset, mounted, translateY, visible]);

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) => (
        visible
        && Math.abs(gesture.dy) > 6
        && Math.abs(gesture.dy) > Math.abs(gesture.dx)
      ),
      onPanResponderMove: (_, gesture) => {
        if (gesture.dy <= 0) {
          translateY.setValue(0);
          return;
        }
        translateY.setValue(gesture.dy);
      },
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dy > CLOSE_DISTANCE || gesture.vy > CLOSE_VELOCITY) {
          onClose();
          return;
        }
        Animated.spring(translateY, {
          toValue: 0,
          useNativeDriver: true,
          damping: 24,
          stiffness: 260,
          mass: 0.9,
        }).start();
      },
      onPanResponderTerminate: () => {
        Animated.spring(translateY, {
          toValue: 0,
          useNativeDriver: true,
          damping: 24,
          stiffness: 260,
          mass: 0.9,
        }).start();
      },
    }),
  ).current;

  if (!mounted) return null;

  return (
    <Animated.View
      style={[
        styles.sheetShell,
        {
          maxHeight,
          transform: [{ translateY }],
        },
      ]}
    >
      <View style={styles.handleZone} {...panResponder.panHandlers}>
        <View style={styles.handle} />
        <View style={styles.headerRow}>
          <View style={styles.headerCopy}>
            <Text style={styles.headerEyebrow}>Slot Detail</Text>
            <Text style={styles.headerTitle}>{title}</Text>
            {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
          </View>
        </View>
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        nestedScrollEnabled
      >
        {children}
      </ScrollView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  sheetShell: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: 'rgba(255, 255, 255, 0.98)',
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: alpha(theme.gameUi.primary, 0.18),
    shadowColor: '#111827',
    shadowOpacity: 0.16,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: -10 },
    elevation: 24,
  },
  handleZone: {
    paddingTop: 10,
    paddingHorizontal: 16,
    paddingBottom: 16,
    minHeight: 88,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: 'rgba(255, 255, 255, 0.98)',
    borderBottomWidth: 1,
    borderBottomColor: alpha(theme.gameUi.cardBorder, 0.92),
  },
  handle: {
    alignSelf: 'center',
    width: 52,
    height: 5,
    borderRadius: 999,
    backgroundColor: alpha(theme.gameUi.textSecondary, 0.32),
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: 'column',
    alignItems: 'flex-start',
    justifyContent: 'center',
  },
  headerCopy: {
    flex: 1,
    gap: 2,
  },
  headerEyebrow: {
    ...theme.typography.caption,
    color: theme.gameUi.primary,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  headerTitle: {
    ...theme.typography.headingSm,
    color: theme.gameUi.textPrimary,
  },
  headerSubtitle: {
    ...theme.typography.bodySm,
    color: theme.gameUi.textSecondary,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 16,
    paddingTop: 14,
    paddingBottom: 28,
    gap: 14,
  },
});
