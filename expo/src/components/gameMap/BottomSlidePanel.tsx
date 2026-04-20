import React, { useRef, useState } from 'react';
import {
  Animated,
  Dimensions,
  PanResponder,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { theme } from '@/design/theme';

export interface BriefItem {
  key: string;
  icon: string;
  title: string;
  bullets: string[];
}

export interface OpportunityCard {
  key: string;
  icon: string;
  title: string;
  subtitle: string;
  bonus?: string;
  actionLabel: string;
  onPress: () => void;
}

interface BottomSlidePanelProps {
  briefItems: BriefItem[];
  opportunities: OpportunityCard[];
  collapsed?: boolean;
}

const SCREEN_HEIGHT = Dimensions.get('window').height;
const COLLAPSED_HEIGHT = SCREEN_HEIGHT * 0.28;
const EXPANDED_HEIGHT = SCREEN_HEIGHT * 0.65;
const SNAP_THRESHOLD = 60;

export default function BottomSlidePanel({
  briefItems,
  opportunities,
}: BottomSlidePanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const panelHeight = useRef(new Animated.Value(COLLAPSED_HEIGHT)).current;
  const lastHeight = useRef(COLLAPSED_HEIGHT);

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dy) > 8,
      onPanResponderMove: (_, gesture) => {
        const newHeight = Math.max(
          COLLAPSED_HEIGHT,
          Math.min(EXPANDED_HEIGHT, lastHeight.current - gesture.dy),
        );
        panelHeight.setValue(newHeight);
      },
      onPanResponderRelease: (_, gesture) => {
        const currentVal = lastHeight.current - gesture.dy;
        const shouldExpand = gesture.dy < -SNAP_THRESHOLD || currentVal > (COLLAPSED_HEIGHT + EXPANDED_HEIGHT) / 2;
        const target = shouldExpand ? EXPANDED_HEIGHT : COLLAPSED_HEIGHT;
        setIsExpanded(shouldExpand);
        lastHeight.current = target;
        Animated.spring(panelHeight, {
          toValue: target,
          useNativeDriver: false,
          tension: 80,
          friction: 12,
        }).start();
      },
    }),
  ).current;

  const togglePanel = () => {
    const target = isExpanded ? COLLAPSED_HEIGHT : EXPANDED_HEIGHT;
    setIsExpanded(!isExpanded);
    lastHeight.current = target;
    Animated.spring(panelHeight, {
      toValue: target,
      useNativeDriver: false,
      tension: 80,
      friction: 12,
    }).start();
  };

  return (
    <Animated.View style={[styles.panel, { height: panelHeight }]}>
      {/* Drag handle */}
      <View {...panResponder.panHandlers}>
        <Pressable onPress={togglePanel} style={styles.handleArea}>
          <View style={styles.handle} />
          <Text style={styles.panelTitle}>
            {isExpanded ? 'Daily Brief & Opportunities' : 'Swipe up for more'}
          </Text>
        </Pressable>
      </View>

      <ScrollView
        style={styles.scrollContent}
        contentContainerStyle={styles.scrollInner}
        showsVerticalScrollIndicator={false}
        scrollEnabled={isExpanded}
      >
        {/* Daily Brief Section */}
        {briefItems.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>DAILY BRIEF</Text>
            {briefItems.map((item) => (
              <View key={item.key} style={styles.briefCard}>
                <View style={styles.briefHeader}>
                  <Text style={styles.briefIcon}>{item.icon}</Text>
                  <Text style={styles.briefTitle}>{item.title}</Text>
                </View>
                {item.bullets.map((bullet, i) => (
                  <Text key={`${item.key}_bullet_${i}`} style={styles.briefBullet}>
                    {'\u{2022}'} {bullet}
                  </Text>
                ))}
              </View>
            ))}
          </View>
        ) : null}

        {/* Opportunities Section */}
        {opportunities.length > 0 ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>OPPORTUNITIES</Text>
            {opportunities.map((opp) => (
              <View key={opp.key} style={styles.oppCard}>
                <View style={styles.oppHeader}>
                  <Text style={styles.oppIcon}>{opp.icon}</Text>
                  <View style={styles.oppCopy}>
                    <Text style={styles.oppTitle}>{opp.title}</Text>
                    <Text style={styles.oppSubtitle}>{opp.subtitle}</Text>
                  </View>
                  {opp.bonus ? (
                    <View style={styles.bonusBadge}>
                      <Text style={styles.bonusText}>{opp.bonus}</Text>
                    </View>
                  ) : null}
                </View>
                <Pressable
                  style={({ pressed }) => [styles.oppButton, pressed && styles.oppButtonPressed]}
                  onPress={opp.onPress}
                >
                  <Text style={styles.oppButtonText}>{opp.actionLabel}</Text>
                </Pressable>
              </View>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  panel: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: theme.ui.bg.sheet,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    shadowColor: theme.ui.text.onLight,
    shadowOpacity: 0.15,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: -4 },
    elevation: 12,
    zIndex: 40,
  },
  handleArea: {
    alignItems: 'center',
    paddingTop: 10,
    paddingBottom: 8,
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: theme.ui.text.onLightMuted,
    marginBottom: 6,
  },
  panelTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: theme.color.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  scrollContent: {
    flex: 1,
  },
  scrollInner: {
    paddingHorizontal: 16,
    paddingBottom: 32,
    gap: 16,
  },
  section: {
    gap: 8,
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: '800',
    color: theme.color.muted,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginBottom: 2,
  },
  // Brief cards
  briefCard: {
    backgroundColor: theme.ui.bg.sheet,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.ui.border,
    padding: 12,
    gap: 4,
  },
  briefHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 2,
  },
  briefIcon: {
    fontSize: 16,
  },
  briefTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: theme.color.textPrimary,
    flex: 1,
  },
  briefBullet: {
    fontSize: 11,
    color: theme.color.textSecondary,
    lineHeight: 16,
    paddingLeft: 24,
  },
  // Opportunity cards
  oppCard: {
    backgroundColor: theme.ui.bg.sheet,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.ui.info,
    padding: 12,
    gap: 10,
    shadowColor: theme.ui.action,
    shadowOpacity: 0.06,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  oppHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  oppIcon: {
    fontSize: 24,
  },
  oppCopy: {
    flex: 1,
    gap: 1,
  },
  oppTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: theme.color.textPrimary,
  },
  oppSubtitle: {
    fontSize: 11,
    color: theme.color.textSecondary,
  },
  bonusBadge: {
    backgroundColor: theme.ui.positive,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  bonusText: {
    fontSize: 11,
    fontWeight: '800',
    color: theme.ui.positive,
  },
  oppButton: {
    backgroundColor: theme.ui.action,
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
  },
  oppButtonPressed: {
    backgroundColor: theme.ui.action,
    transform: [{ scale: 0.97 }],
  },
  oppButtonText: {
    fontSize: 13,
    fontWeight: '700',
    color: theme.ui.bg.sheet,
  },
});
