import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  NativeScrollEvent,
  NativeSyntheticEvent,
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
const TOP_SCROLL_TOLERANCE = 6;

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
  const scrollOffsetYRef = useRef(0);

  const hiddenOffset = useMemo(
    () => Math.max(height * 0.8, 420),
    [height],
  );
  const maxHeight = useMemo(
    () => Math.min(Math.max(height * 0.78, 420), 760),
    [height],
  );

  useEffect(() => {
    if (visible) {
      setMounted(true);
      scrollOffsetYRef.current = 0;
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

  const springBack = () => {
    Animated.spring(translateY, {
      toValue: 0,
      useNativeDriver: true,
      damping: 24,
      stiffness: 260,
      mass: 0.9,
    }).start();
  };

  const handleDismissRelease = (_: unknown, gesture: { dy: number; vy: number }) => {
    if (gesture.dy > CLOSE_DISTANCE || gesture.vy > CLOSE_VELOCITY) {
      onClose();
      return;
    }
    springBack();
  };

  const isScrollAtTop = () => scrollOffsetYRef.current <= TOP_SCROLL_TOLERANCE;

  const shouldCaptureDismissDrag = (gesture: { dx: number; dy: number }) => (
    visible
    && isScrollAtTop()
    && gesture.dy > 6
    && Math.abs(gesture.dy) > Math.abs(gesture.dx)
  );

  const handleHeaderDrag = (_: unknown, gesture: { dy: number }) => {
    if (gesture.dy <= 0) {
      translateY.setValue(0);
      return;
    }
    translateY.setValue(Math.min(gesture.dy, hiddenOffset));
  };

  const handleSheetDrag = (_: unknown, gesture: { dy: number }) => {
    if (!isScrollAtTop()) return;
    if (gesture.dy <= 0) {
      translateY.setValue(0);
      return;
    }
    translateY.setValue(Math.min(gesture.dy, hiddenOffset));
  };

  const headerPanResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => visible,
      onStartShouldSetPanResponderCapture: () => visible,
      onMoveShouldSetPanResponder: (_, gesture) => (
        visible
        && Math.abs(gesture.dy) > 6
        && Math.abs(gesture.dy) > Math.abs(gesture.dx)
      ),
      onMoveShouldSetPanResponderCapture: (_, gesture) => (
        visible
        && Math.abs(gesture.dy) > 4
        && Math.abs(gesture.dy) > Math.abs(gesture.dx)
      ),
      onPanResponderMove: handleHeaderDrag,
      onPanResponderRelease: handleDismissRelease,
      onPanResponderTerminate: springBack,
      onPanResponderTerminationRequest: () => true,
    }),
  ).current;

  const contentPanResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) => shouldCaptureDismissDrag(gesture),
      onMoveShouldSetPanResponderCapture: (_, gesture) => shouldCaptureDismissDrag(gesture),
      onPanResponderMove: handleSheetDrag,
      onPanResponderRelease: handleDismissRelease,
      onPanResponderTerminate: springBack,
      onPanResponderTerminationRequest: () => true,
    }),
  ).current;

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    scrollOffsetYRef.current = Math.max(0, event.nativeEvent.contentOffset.y || 0);
  };

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
      <View style={styles.handleZone} {...headerPanResponder.panHandlers}>
        <View style={styles.handle} />
        <View style={styles.headerRow}>
          <View style={styles.headerCopy}>
            <Text style={styles.headerEyebrow}>Slot Detail</Text>
            <Text style={styles.headerTitle}>{title}</Text>
            {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
          </View>
        </View>
      </View>

      <View style={styles.scrollShell} {...contentPanResponder.panHandlers}>
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          contentInsetAdjustmentBehavior="automatic"
          showsVerticalScrollIndicator
          nestedScrollEnabled
          bounces={false}
          overScrollMode="never"
          keyboardShouldPersistTaps="handled"
          scrollEventThrottle={16}
          onScroll={handleScroll}
        >
          {children}
        </ScrollView>
      </View>
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
    backgroundColor: theme.ui.bg.sheet,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: alpha(theme.ui.border, 0.34),
    shadowColor: theme.ui.text.onLight,
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
    backgroundColor: theme.ui.bg.sheet,
    borderBottomWidth: 1,
    borderBottomColor: alpha(theme.ui.border, 0.24),
  },
  handle: {
    alignSelf: 'center',
    width: 52,
    height: 5,
    borderRadius: 999,
    backgroundColor: alpha(theme.color.textSecondaryOnLight, 0.32),
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
    color: theme.color.textPrimaryOnLight,
  },
  headerSubtitle: {
    ...theme.typography.bodySm,
    color: theme.color.textSecondaryOnLight,
  },
  scrollShell: {
    flex: 1,
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
