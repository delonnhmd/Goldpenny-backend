import React, { useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import * as Updates from 'expo-updates';

import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SectionCard from '@/components/ui/SectionCard';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import { KEY_LAST_PLAYER_ID } from '@/features/auth/storage';
import { KEY_ADMIN_TOKEN, KEY_BACKEND_OVERRIDE } from '@/lib/apiClient';
import { sendTestPushNotification } from '@/lib/api/notifications';
import {
  clearRecentDiagnostics,
  DiagnosticEntry,
  getRecentDiagnostics,
  recordError,
  recordInfo,
  recordWarning,
} from '@/lib/logger';
import { registerAndSyncPushTokenAsync } from '@/lib/pushNotifications';

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue} numberOfLines={1}>{value}</Text>
    </View>
  );
}

export default function SettingsScreen() {
  const [backendUrl, setBackendUrl] = useState('');
  const [adminToken, setAdminToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticEntry[]>([]);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [clearingDiagnostics, setClearingDiagnostics] = useState(false);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [applyingUpdate, setApplyingUpdate] = useState(false);
  const [pushPlayerId, setPushPlayerId] = useState('');
  const [pushTestBusy, setPushTestBusy] = useState(false);
  const loaded = useRef(false);

  const appName = Constants.expoConfig?.name || 'Gold Penny';
  const appSlug = Constants.expoConfig?.slug || 'goldpenny-expo';
  const appVersion = Constants.expoConfig?.version || 'Unknown';
  const runtimeVersion = Updates.runtimeVersion || 'Unknown';
  const updateChannel = Updates.channel || 'default';

  const loadDiagnostics = async () => {
    setDiagnosticsLoading(true);
    try {
      setDiagnostics(await getRecentDiagnostics());
    } catch (error) {
      recordWarning('settings', 'Failed to load recent diagnostics.', {
        action: 'load_diagnostics',
        error,
      });
    } finally {
      setDiagnosticsLoading(false);
    }
  };

  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    (async () => {
      try {
        const [url, token, rememberedPlayerId] = await Promise.all([
          AsyncStorage.getItem(KEY_BACKEND_OVERRIDE),
          AsyncStorage.getItem(KEY_ADMIN_TOKEN),
          AsyncStorage.getItem(KEY_LAST_PLAYER_ID),
        ]);
        setBackendUrl(url || '');
        setAdminToken(token || '');
        setPushPlayerId(rememberedPlayerId || '');
      } catch (error) {
        recordWarning('settings', 'Failed to hydrate saved settings.', {
          action: 'load_settings',
          error,
        });
        Alert.alert('Settings', 'Unable to load saved settings.');
      }
      await loadDiagnostics();
    })();
  }, []);

  const saveSettings = async () => {
    setSaving(true);
    try {
      await Promise.all([
        backendUrl.trim()
          ? AsyncStorage.setItem(KEY_BACKEND_OVERRIDE, backendUrl.trim())
          : AsyncStorage.removeItem(KEY_BACKEND_OVERRIDE),
        adminToken.trim()
          ? AsyncStorage.setItem(KEY_ADMIN_TOKEN, adminToken.trim())
          : AsyncStorage.removeItem(KEY_ADMIN_TOKEN),
      ]);
      recordInfo('settings', 'Local override settings saved.', {
        action: 'save_settings',
        context: {
          hasBackendOverride: Boolean(backendUrl.trim()),
          hasAdminToken: Boolean(adminToken.trim()),
        },
      });
      Alert.alert('Saved', 'Settings have been saved for this device.');
    } catch (error) {
      recordError('settings', 'Saving override settings failed.', {
        action: 'save_settings',
        error,
      });
      Alert.alert('Save Failed', error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  };

  const resetSettings = async () => {
    setSaving(true);
    try {
      await Promise.all([
        AsyncStorage.removeItem(KEY_BACKEND_OVERRIDE),
        AsyncStorage.removeItem(KEY_ADMIN_TOKEN),
      ]);
      setBackendUrl('');
      setAdminToken('');
      Alert.alert('Reset Complete', 'Local overrides have been cleared.');
    } catch (error) {
      recordError('settings', 'Resetting override settings failed.', {
        action: 'reset_settings',
        error,
      });
      Alert.alert('Reset Failed', error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  };

  const checkForUpdates = async () => {
    setCheckingUpdate(true);
    try {
      const result = await Updates.checkForUpdateAsync();
      Alert.alert('Update Check', result.isAvailable ? 'A new update is available.' : 'You are already on the latest version.');
    } catch (error) {
      recordError('settings', 'Update check failed.', {
        action: 'check_for_updates',
        error,
      });
      Alert.alert('Update Check Failed', error instanceof Error ? error.message : String(error));
    } finally {
      setCheckingUpdate(false);
    }
  };

  const applyUpdate = async () => {
    setApplyingUpdate(true);
    try {
      const result = await Updates.checkForUpdateAsync();
      if (!result.isAvailable) {
        Alert.alert('No Update', 'There is no update to apply.');
        return;
      }
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync();
    } catch (error) {
      recordError('settings', 'Update fetch or reload failed.', {
        action: 'apply_update',
        error,
      });
      Alert.alert('Update Failed', error instanceof Error ? error.message : String(error));
    } finally {
      setApplyingUpdate(false);
    }
  };

  const handleClearDiagnostics = async () => {
    setClearingDiagnostics(true);
    try {
      await clearRecentDiagnostics();
      await loadDiagnostics();
    } catch (error) {
      recordError('settings', 'Clearing recent diagnostics failed.', {
        action: 'clear_diagnostics',
        error,
      });
      Alert.alert('Clear Diagnostics Failed', error instanceof Error ? error.message : String(error));
    } finally {
      setClearingDiagnostics(false);
    }
  };

  const handleSendTestPush = async () => {
    const playerId = pushPlayerId.trim() || (await AsyncStorage.getItem(KEY_LAST_PLAYER_ID)) || '';
    if (!playerId.trim()) {
      Alert.alert('Player ID Required', 'Sign in or enter a player ID before sending a test push.');
      return;
    }

    setPushTestBusy(true);
    try {
      const registration = await registerAndSyncPushTokenAsync(playerId.trim());
      if (!registration.ok || !registration.pushToken) {
        Alert.alert('Push Not Registered', registration.message || 'This device could not register for push notifications.');
        return;
      }

      const result = await sendTestPushNotification(playerId.trim(), 'Test', 'Push is working');
      if (result.ok) {
        Alert.alert('Push Sent', `Sent to ${result.sent} device${result.sent === 1 ? '' : 's'}.`);
        return;
      }

      Alert.alert('Push Test Failed', result.message || result.errors?.[0] || 'Expo did not accept the push request.');
    } catch (error) {
      recordError('settings', 'Send test push failed.', {
        action: 'send_test_push',
        error,
      });
      Alert.alert('Push Test Failed', error instanceof Error ? error.message : String(error));
    } finally {
      setPushTestBusy(false);
    }
  };

  return (
    <AppShell title="Settings" subtitle="V1 operations">
      <PageContainer>
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <ContentStack>
            <SectionCard title="App Version" summary="Runtime and update channel for this build.">
              <InfoRow label="App" value={appName} />
              <InfoRow label="Slug" value={appSlug} />
              <InfoRow label="Version" value={appVersion} />
              <InfoRow label="Runtime" value={runtimeVersion} />
              <InfoRow label="Channel" value={updateChannel} />
              <View style={styles.buttonRow}>
                <SecondaryButton
                  label={checkingUpdate ? 'Checking...' : 'Check Update'}
                  onPress={checkingUpdate ? undefined : checkForUpdates}
                  disabled={checkingUpdate || applyingUpdate}
                />
                <SecondaryButton
                  label={applyingUpdate ? 'Applying...' : 'Apply Update'}
                  onPress={applyingUpdate ? undefined : applyUpdate}
                  disabled={checkingUpdate || applyingUpdate}
                />
              </View>
            </SectionCard>

            <SectionCard title="Backend Settings" summary="Local developer override. Leave blank for the bundled backend URL.">
              <Text style={styles.inputLabel}>Backend URL</Text>
              <TextInput
                style={styles.input}
                placeholder="https://api.example.com"
                placeholderTextColor={theme.color.muted}
                value={backendUrl}
                onChangeText={setBackendUrl}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <Text style={styles.inputLabel}>Admin Token</Text>
              <TextInput
                style={styles.input}
                placeholder="Optional"
                placeholderTextColor={theme.color.muted}
                value={adminToken}
                onChangeText={setAdminToken}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry
              />
              <View style={styles.buttonRow}>
                <SecondaryButton label="Reset" onPress={saving ? undefined : resetSettings} disabled={saving} />
                <PrimaryButton label={saving ? 'Saving...' : 'Save'} onPress={saving ? undefined : saveSettings} disabled={saving} />
              </View>
            </SectionCard>

            <SectionCard title="Push Test" summary="Registers this device token, then sends one backend test notification.">
              <Text style={styles.inputLabel}>Player ID</Text>
              <TextInput
                style={styles.input}
                placeholder="Signed-in player ID"
                placeholderTextColor={theme.color.muted}
                value={pushPlayerId}
                onChangeText={setPushPlayerId}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <PrimaryButton
                label={pushTestBusy ? 'Sending...' : 'Send Test Push'}
                onPress={pushTestBusy ? undefined : handleSendTestPush}
                disabled={pushTestBusy}
              />
            </SectionCard>

            <SectionCard title="Diagnostics" summary="Recent local logs from the current device.">
              <View style={styles.buttonRow}>
                <SecondaryButton
                  label={diagnosticsLoading ? 'Loading...' : 'Reload'}
                  onPress={diagnosticsLoading ? undefined : loadDiagnostics}
                  disabled={diagnosticsLoading || clearingDiagnostics}
                />
                <SecondaryButton
                  label={clearingDiagnostics ? 'Clearing...' : 'Clear'}
                  onPress={clearingDiagnostics ? undefined : handleClearDiagnostics}
                  disabled={diagnosticsLoading || clearingDiagnostics}
                />
              </View>
              {diagnostics.length === 0 ? (
                <Text style={styles.note}>No diagnostics stored on this device.</Text>
              ) : (
                diagnostics.slice(0, 12).map((entry) => (
                  <View key={entry.id} style={styles.diagnosticCard}>
                    <Text style={styles.diagnosticLevel}>{entry.level.toUpperCase()} - {entry.source}</Text>
                    <Text style={styles.diagnosticMessage}>{entry.message}</Text>
                    <Text style={styles.diagnosticTime}>{new Date(entry.timestamp).toLocaleString()}</Text>
                  </View>
                ))
              )}
            </SectionCard>
          </ContentStack>
        </ScrollView>
      </PageContainer>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingTop: theme.spacing.lg,
    paddingBottom: theme.spacing.xxxl,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
    paddingVertical: theme.spacing.xxs,
  },
  infoLabel: {
    ...theme.typography.caption,
    color: theme.color.muted,
    flex: 1,
  },
  infoValue: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
    fontWeight: '700',
    flex: 1,
    textAlign: 'right',
  },
  inputLabel: {
    ...theme.typography.caption,
    color: theme.color.textPrimary,
    fontWeight: '800',
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    color: theme.color.textPrimary,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    ...theme.typography.bodySm,
  },
  buttonRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.md,
  },
  note: {
    ...theme.typography.bodySm,
    color: theme.color.muted,
  },
  diagnosticCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
    marginTop: theme.spacing.sm,
  },
  diagnosticLevel: {
    ...theme.typography.caption,
    color: theme.color.accent,
    fontWeight: '900',
  },
  diagnosticMessage: {
    ...theme.typography.bodySm,
    color: theme.color.textPrimary,
  },
  diagnosticTime: {
    ...theme.typography.caption,
    color: theme.color.muted,
  },
});
