import React, { useEffect, useRef } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';

export interface FABAction {
  key: string;
  icon: string;
  label: string;
  color: string;
  disabled?: boolean;
  onPress: () => void;
}

interface FloatingActionButtonsProps {
  actions: FABAction[];
}

function FABButton({ action, index }: { action: FABAction; index: number }) {
  const enterAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(enterAnim, {
      toValue: 1,
      duration: 280,
      delay: index * 60,
      useNativeDriver: true,
    }).start();
  }, [enterAnim, index]);

  const scale = enterAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.5, 1],
  });
  const opacity = enterAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 1],
  });

  return (
    <Animated.View style={{ transform: [{ scale }], opacity }}>
      <Pressable
        style={({ pressed }) => [
          styles.fab,
          { backgroundColor: action.disabled ? '#94a3b8' : action.color },
          pressed && !action.disabled ? styles.fabPressed : null,
        ]}
        onPress={action.disabled ? undefined : action.onPress}
        disabled={action.disabled}
      >
        <Text style={styles.fabIcon}>{action.icon}</Text>
        <Text style={styles.fabLabel}>{action.label}</Text>
      </Pressable>
    </Animated.View>
  );
}

export default function FloatingActionButtons({ actions }: FloatingActionButtonsProps) {
  return (
    <View style={styles.container}>
      {actions.map((action, i) => (
        <FABButton key={action.key} action={action} index={i} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    right: 12,
    bottom: 16,
    gap: 10,
    alignItems: 'flex-end',
    zIndex: 30,
  },
  fab: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 5,
  },
  fabPressed: {
    transform: [{ scale: 0.92 }],
    opacity: 0.9,
  },
  fabIcon: {
    fontSize: 20,
  },
  fabLabel: {
    fontSize: 7,
    fontWeight: '800',
    color: '#ffffff',
    textTransform: 'uppercase',
    marginTop: 1,
    letterSpacing: 0.3,
  },
});
