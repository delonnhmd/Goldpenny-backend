import React, { useMemo } from 'react';
import { Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { severityColor } from '@/lib/gameplayFormatters';
import { PlayerNotificationItem } from '@/types/gameplay';

const severityRank: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

export default function NotificationsDrawer({
  visible,
  notifications,
  onClose,
}: {
  visible: boolean;
  notifications: PlayerNotificationItem[];
  onClose: () => void;
}) {
  const sorted = useMemo(() => {
    return [...notifications].sort((a, b) => {
      const aRank = severityRank[a.severity] ?? 99;
      const bRank = severityRank[b.severity] ?? 99;
      if (aRank !== bRank) return aRank - bRank;
      return (b.created_at || '').localeCompare(a.created_at || '');
    });
  }, [notifications]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.drawer}>
          <View style={styles.header}>
            <Text style={styles.title}>Notifications</Text>
            <TouchableOpacity onPress={onClose} style={styles.close}>
              <Text style={styles.closeText}>Close</Text>
            </TouchableOpacity>
          </View>

          <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
            {sorted.length > 0 ? (
              sorted.map((item) => (
                <View key={item.id} style={styles.item}>
                  <View style={styles.itemHeader}>
                    <Text style={[styles.severity, { color: severityColor(item.severity) }]}>{item.severity}</Text>
                    <Text style={styles.category}>{item.category}</Text>
                  </View>
                  <Text style={styles.itemTitle}>{item.title}</Text>
                  <Text style={styles.itemBody}>{item.body}</Text>
                  {item.suggested_action ? (
                    <Text style={styles.itemAction}>Suggested: {item.suggested_action}</Text>
                  ) : null}
                </View>
              ))
            ) : (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>No alerts right now</Text>
                <Text style={styles.emptyBody}>You are clear for now. Keep checking daily.</Text>
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(2, 6, 23, 0.45)',
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  drawer: {
    width: '88%',
    maxWidth: 400,
    backgroundColor: '#ffffff',
    borderLeftWidth: 1,
    borderLeftColor: '#e2e8f0',
  },
  header: {
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    color: '#0f172a',
    fontSize: 18,
    fontWeight: '800',
  },
  close: {
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  closeText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '700',
  },
  body: {
    padding: 12,
    gap: 10,
  },
  item: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#f8fafc',
    padding: 10,
    gap: 5,
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  severity: {
    textTransform: 'uppercase',
    fontSize: 10,
    fontWeight: '800',
  },
  category: {
    color: '#64748b',
    fontSize: 11,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  itemTitle: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '700',
  },
  itemBody: {
    color: '#334155',
    fontSize: 12,
    lineHeight: 17,
  },
  itemAction: {
    color: '#1d4ed8',
    fontSize: 12,
    fontWeight: '600',
  },
  empty: {
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 10,
    backgroundColor: '#ffffff',
    padding: 12,
    gap: 5,
  },
  emptyTitle: {
    color: '#0f172a',
    fontSize: 14,
    fontWeight: '700',
  },
  emptyBody: {
    color: '#64748b',
    fontSize: 12,
    lineHeight: 17,
  },
});
