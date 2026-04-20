import BottomSheet, {
  BottomSheetBackdrop,
  BottomSheetScrollView,
  useBottomSheetSpringConfigs,
} from '@gorhom/bottom-sheet';
import type {
  BottomSheetBackdropProps,
  BottomSheetHandleProps,
} from '@gorhom/bottom-sheet';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { alpha, theme } from '@/design/theme';

interface MapDetailSheetProps {
  visible: boolean;
  title: string;
  subtitle?: string | null;
  onClose: () => void;
  children: React.ReactNode;
}

const SNAP_POINTS: (string | number)[] = ['25%', '55%', '90%'];
const PEEK_INDEX = 0;
const MID_INDEX = 1;
const EXPANDED_INDEX = 2;

function SheetHandle({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string | null;
}) {
  return (
    <View style={styles.handleShell}>
      <View style={styles.handle} />
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.headerEyebrow}>Slot Detail</Text>
          <Text style={styles.headerTitle}>{title}</Text>
          {subtitle ? <Text style={styles.headerSubtitle}>{subtitle}</Text> : null}
        </View>
      </View>
    </View>
  );
}

export default function MapDetailSheet({
  visible,
  title,
  subtitle,
  onClose,
  children,
}: MapDetailSheetProps) {
  const sheetRef = useRef<React.ElementRef<typeof BottomSheet>>(null);
  const [sheetIndex, setSheetIndex] = useState<number>(-1);

  const animationConfigs = useBottomSheetSpringConfigs({
    damping: 30,
    stiffness: 300,
    overshootClamping: false,
  });

  useEffect(() => {
    if (!sheetRef.current) return;
    if (visible) {
      sheetRef.current.snapToIndex(MID_INDEX, animationConfigs);
      return;
    }
    sheetRef.current.close();
  }, [animationConfigs, visible]);

  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...props}
        appearsOnIndex={PEEK_INDEX}
        disappearsOnIndex={-1}
        opacity={1}
        pressBehavior="close"
        style={styles.backdrop}
      />
    ),
    [],
  );

  const renderHandle = useCallback(
    (_props: BottomSheetHandleProps) => (
      <SheetHandle title={title} subtitle={subtitle} />
    ),
    [subtitle, title],
  );

  return (
    <View pointerEvents={visible ? 'auto' : 'none'} style={StyleSheet.absoluteFill}>
      <BottomSheet
        ref={sheetRef}
        index={visible ? MID_INDEX : -1}
        snapPoints={SNAP_POINTS}
        animateOnMount={false}
        enableDynamicSizing={false}
        enablePanDownToClose
        enableContentPanningGesture={false}
        enableHandlePanningGesture
        overDragResistanceFactor={2.4}
        animationConfigs={animationConfigs}
        onChange={(index) => setSheetIndex(index)}
        onClose={onClose}
        handleComponent={renderHandle}
        backdropComponent={renderBackdrop}
        style={styles.sheetShell}
        backgroundStyle={styles.background}
        handleIndicatorStyle={styles.hiddenIndicator}
      >
        <BottomSheetScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          overScrollMode="never"
          bounces={false}
          scrollEnabled={sheetIndex === EXPANDED_INDEX}
          nestedScrollEnabled
          keyboardShouldPersistTaps="handled"
        >
          {children}
        </BottomSheetScrollView>
      </BottomSheet>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    backgroundColor: alpha(theme.ui.bg.app, 0.24),
  },
  sheetShell: {
    shadowColor: theme.ui.border,
    shadowOpacity: 0.16,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: -10 },
    elevation: 24,
  },
  background: {
    backgroundColor: theme.ui.bg.sheet,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: theme.ui.border,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
  },
  hiddenIndicator: {
    opacity: 0,
  },
  handleShell: {
    paddingTop: 10,
    paddingHorizontal: 16,
    paddingBottom: 16,
    minHeight: 88,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    backgroundColor: theme.ui.bg.sheet,
    borderBottomWidth: 1,
    borderBottomColor: theme.ui.border,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: theme.ui.text.onDarkMuted,
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
    color: theme.ui.text.onLightMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  headerTitle: {
    ...theme.typography.headingSm,
    color: theme.ui.text.onLight,
  },
  headerSubtitle: {
    ...theme.typography.bodySm,
    color: theme.ui.text.onLightMuted,
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
