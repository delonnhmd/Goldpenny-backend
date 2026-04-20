import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { KEY_ADMIN_TOKEN, KEY_BACKEND_OVERRIDE } from '@/lib/apiClient';
import * as Updates from 'expo-updates';

import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SectionCard from '@/components/ui/SectionCard';
import SecondaryButton from '@/components/ui/SecondaryButton';
import { theme } from '@/design/theme';
import {
  clearRecentDiagnostics,
  DiagnosticEntry,
  getRecentDiagnostics,
  recordError,
  recordInfo,
  recordWarning,
} from '@/lib/logger';
import {
  buildPlaytestReport,
  clearPlaytestData,
  PlaytestReport,
} from '@/lib/playtestAnalytics';

// ── Step 68: Day 1 balance presets (must stay in sync with balance_config.py) ──
const BALANCE_PRESETS = {
  easy:        { income_multiplier: 1.30, expense_pressure_multiplier: 0.80, stress_sensitivity: 0.75, health_decay_rate: 0.70, opportunity_spawn_rate: 1.60 },
  normal:      { income_multiplier: 1.00, expense_pressure_multiplier: 1.00, stress_sensitivity: 1.00, health_decay_rate: 1.00, opportunity_spawn_rate: 1.00 },
  hard:        { income_multiplier: 0.85, expense_pressure_multiplier: 1.25, stress_sensitivity: 1.35, health_decay_rate: 1.40, opportunity_spawn_rate: 0.65 },
  stress_test: { income_multiplier: 0.60, expense_pressure_multiplier: 1.60, stress_sensitivity: 2.00, health_decay_rate: 2.00, opportunity_spawn_rate: 0.40 },
} as const;
type BalancePresetKey = keyof typeof BALANCE_PRESETS;
const BALANCE_PRESET_STORAGE_KEY = 'goldpenny:dev:balance_preset' as const;

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
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [applyingUpdate, setApplyingUpdate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticEntry[]>([]);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [clearingDiagnostics, setClearingDiagnostics] = useState(false);
  const [playtestReport, setPlaytestReport] = useState<PlaytestReport | null>(null);
  const [playtestLoading, setPlaytestLoading] = useState(false);
  const [clearingPlaytest, setClearingPlaytest] = useState(false);
  const [playtestPlayerId, setPlaytestPlayerId] = useState('');
  const [playtestGameDay, setPlaytestGameDay] = useState('1');
  const [balancePreset, setBalancePreset] = useState<BalancePresetKey>('normal');
  const loaded = useRef(false);

  const appName = Constants.expoConfig?.name || 'Gold Penny';
  const appSlug = Constants.expoConfig?.slug || 'goldpenny-expo';
  const appVersion = Constants.expoConfig?.version || 'Unknown';
  const runtimeVersion = Updates.runtimeVersion || 'Unknown';
  const updateChannel = Updates.channel || 'default';
  const mainWebsite = 'https://www.pennyfloat.com';
  const gameplayWebsite = 'https://goldpenny.pennyfloat.com';

  const hasOverrides = useMemo(
    () => Boolean(backendUrl.trim() || adminToken.trim()),
    [backendUrl, adminToken],
  );

  const loadDiagnostics = async () => {
    setDiagnosticsLoading(true);
    try {
      const entries = await getRecentDiagnostics();
      setDiagnostics(entries);
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
        const [url, token] = await Promise.all([
          AsyncStorage.getItem(KEY_BACKEND_OVERRIDE),
          AsyncStorage.getItem(KEY_ADMIN_TOKEN),
        ]);
        const rememberedPlayerId = await AsyncStorage.getItem('goldpenny:gameplay:lastPlayerId');
        if (rememberedPlayerId) setPlaytestPlayerId(rememberedPlayerId);
        setBackendUrl(url || '');
        setAdminToken(token || '');
        const savedPreset = await AsyncStorage.getItem(BALANCE_PRESET_STORAGE_KEY);
        if (savedPreset && savedPreset in BALANCE_PRESETS) {
          setBalancePreset(savedPreset as BalancePresetKey);
        }
      } catch (error) {
        recordWarning('settings', 'Failed to hydrate saved settings.', {
          action: 'load_settings',
          error,
        });
        Alert.alert('Settings', 'Unable to load saved settings. You can still enter new values below.');
      }
      await loadDiagnostics();
    })();
  }, []);

  const checkForUpdates = async () => {
    setCheckingUpdate(true);
    try {
      const res = await Updates.checkForUpdateAsync();
      recordInfo('settings', 'Checked for updates.', {
        action: 'check_for_updates',
        context: {
          isAvailable: res.isAvailable,
        },
      });
      Alert.alert('Update Check', res.isAvailable ? 'A new update is available.' : 'You are already on the latest version.');
    } catch (e: any) {
      recordError('settings', 'Update check failed.', {
        action: 'check_for_updates',
        error: e,
      });
      Alert.alert('Update Check Failed', e?.message || String(e));
    } finally {
      setCheckingUpdate(false);
      await loadDiagnostics();
    }
  };

  const fetchAndReload = async () => {
    setApplyingUpdate(true);
    try {
      const res = await Updates.checkForUpdateAsync();
      if (res.isAvailable) {
        recordInfo('settings', 'Fetched OTA update and reloading.', {
          action: 'fetch_and_reload',
        });
        await Updates.fetchUpdateAsync();
        await Updates.reloadAsync();
        return;
      }
      Alert.alert('No Update', 'No update is currently available.');
    } catch (e: any) {
      recordError('settings', 'Update fetch or reload failed.', {
        action: 'fetch_and_reload',
        error: e,
      });
      Alert.alert('Update Apply Failed', e?.message || String(e));
    } finally {
      setApplyingUpdate(false);
      await loadDiagnostics();
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const normalizedBackend = backendUrl.trim();
      const normalizedToken = adminToken.trim();

      if (normalizedBackend && !/^https?:\/\//i.test(normalizedBackend)) {
        Alert.alert('Invalid URL', 'Please enter a valid http(s) URL');
        return;
      }

      if (normalizedBackend) {
        await AsyncStorage.setItem(KEY_BACKEND_OVERRIDE, normalizedBackend);
      } else {
        await AsyncStorage.removeItem(KEY_BACKEND_OVERRIDE);
      }

      if (normalizedToken) {
        await AsyncStorage.setItem(KEY_ADMIN_TOKEN, normalizedToken);
      } else {
        await AsyncStorage.removeItem(KEY_ADMIN_TOKEN);
      }

      setBackendUrl(normalizedBackend);
      setAdminToken(normalizedToken);
      recordInfo('settings', 'Local override settings saved.', {
        action: 'save_settings',
        context: {
          hasBackendOverride: Boolean(normalizedBackend),
          hasAdminToken: Boolean(normalizedToken),
        },
      });
      Alert.alert('Saved', 'Advanced settings have been saved for this device.');
    } catch (e: any) {
      recordError('settings', 'Saving override settings failed.', {
        action: 'save_settings',
        error: e,
      });
      Alert.alert('Error', e?.message || String(e));
    } finally {
      setSaving(false);
      await loadDiagnostics();
    }
  };

  const resetOverrides = async () => {
    setSaving(true);
    try {
      await AsyncStorage.multiRemove([KEY_BACKEND_OVERRIDE, KEY_ADMIN_TOKEN, 'admin:address']);
      setBackendUrl('');
      setAdminToken('');
      recordInfo('settings', 'Local overrides reset.', {
        action: 'reset_overrides',
      });
      Alert.alert('Reset Complete', 'Advanced settings have been cleared for this device.');
    } catch (e: any) {
      recordError('settings', 'Resetting override settings failed.', {
        action: 'reset_overrides',
        error: e,
      });
      Alert.alert('Reset Failed', e?.message || String(e));
    } finally {
      setSaving(false);
      await loadDiagnostics();
    }
  };

  const handleClearDiagnostics = async () => {
    setClearingDiagnostics(true);
    try {
      await clearRecentDiagnostics();
      recordInfo('settings', 'Cleared recent diagnostics.', {
        action: 'clear_diagnostics',
      });
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

  const loadPlaytestReport = async () => {
    const pid = playtestPlayerId.trim();
    if (!pid) {
      Alert.alert('Player ID Required', 'Enter a player ID to load the playtest report.');
      return;
    }
    const gameDay = Math.max(1, parseInt(playtestGameDay.trim(), 10) || 1);
    setPlaytestLoading(true);
    try {
      const report = await buildPlaytestReport(pid, 'settings_session', gameDay);
      setPlaytestReport(report);
    } catch (error) {
      Alert.alert('Report Error', error instanceof Error ? error.message : String(error));
    } finally {
      setPlaytestLoading(false);
    }
  };

  const handleSelectBalancePreset = async (name: BalancePresetKey) => {
    setBalancePreset(name);
    try {
      await AsyncStorage.setItem(BALANCE_PRESET_STORAGE_KEY, name);
    } catch (e) {
      recordWarning('settings', 'Failed to persist balance preset.', { action: 'select_balance_preset', error: e });
    }
  };

  const handleClearPlaytestData = async () => {
    const pid = playtestPlayerId.trim();
    if (!pid) return;
    setClearingPlaytest(true);
    try {
      await clearPlaytestData(pid);
      setPlaytestReport(null);
      Alert.alert('Cleared', 'Playtest analytics data has been cleared for this player.');
    } catch (error) {
      Alert.alert('Clear Error', error instanceof Error ? error.message : String(error));
    } finally {
      setClearingPlaytest(false);
    }
  };

  return (
    <AppShell title="Settings" subtitle="Gold Penny app preferences">
      <PageContainer>
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <ContentStack gap={theme.spacing.md}>
            <SectionCard
              title="App Identity"
              summary="Current build, release channel, and brand identity information for this installation."
            >
              <InfoRow label="App" value={appName} />
              <InfoRow label="Slug" value={appSlug} />
              <InfoRow label="Version" value={appVersion} />
              <InfoRow label="Runtime" value={runtimeVersion} />
              <InfoRow label="Channel" value={updateChannel} />
              <InfoRow label="Website" value={mainWebsite} />
              <InfoRow label="Game Site" value={gameplayWebsite} />
            </SectionCard>

            <SectionCard
              title="App Updates"
              summary="Use these controls to check for and apply over-the-air updates."
            >
              <View style={styles.buttonRow}>
                <SecondaryButton
                  label={checkingUpdate ? 'Checking...' : 'Check for Updates'}
                  onPress={checkForUpdates}
                  disabled={checkingUpdate || applyingUpdate}
                />
                <PrimaryButton
                  label={applyingUpdate ? 'Applying...' : 'Fetch and Reload'}
                  onPress={fetchAndReload}
                  disabled={checkingUpdate || applyingUpdate}
                  loading={applyingUpdate}
                />
              </View>
            </SectionCard>

            <SectionCard
              title="Advanced API Settings"
              summary="Optional support and QA overrides for server routing and authenticated maintenance requests. Regular gameplay now uses the built-in account sign-in flow."
            >
              <Text style={styles.inputLabel}>Server URL Override</Text>
              <TextInput
                style={styles.input}
                placeholder="https://your-api.example.com"
                placeholderTextColor={theme.color.muted}
                value={backendUrl}
                onChangeText={setBackendUrl}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="url"
                keyboardType="url"
              />

              <Text style={styles.inputLabel}>Support Access Token</Text>
              <TextInput
                style={styles.input}
                placeholder="Optional support token"
                placeholderTextColor={theme.color.muted}
                value={adminToken}
                onChangeText={setAdminToken}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="off"
                secureTextEntry
              />

              <View style={styles.buttonRow}>
                <SecondaryButton
                  label="Reset Advanced Settings"
                  onPress={hasOverrides ? resetOverrides : undefined}
                  disabled={!hasOverrides || saving}
                />
                <PrimaryButton
                  label="Save Advanced Settings"
                  onPress={saveSettings}
                  loading={saving}
                  disabled={saving}
                />
              </View>

              <Text style={styles.note}>
                These values are stored locally on this device and only affect this app install.
              </Text>
            </SectionCard>

            <SectionCard
              title="Recent Diagnostics"
              summary="Recent startup, network, persistence, gameplay, and optional integration issues captured on this device. Sensitive values are redacted before storage."
            >
              <View style={styles.buttonRow}>
                <SecondaryButton
                  label={diagnosticsLoading ? 'Refreshing...' : 'Refresh Diagnostics'}
                  onPress={diagnosticsLoading ? undefined : loadDiagnostics}
                  disabled={diagnosticsLoading || clearingDiagnostics}
                />
                <SecondaryButton
                  label={clearingDiagnostics ? 'Clearing...' : 'Clear Diagnostics'}
                  onPress={clearingDiagnostics ? undefined : handleClearDiagnostics}
                  disabled={diagnosticsLoading || clearingDiagnostics}
                />
              </View>

              {diagnostics.length === 0 ? (
                <Text style={styles.note}>No diagnostics captured yet on this device.</Text>
              ) : (
                diagnostics.slice(0, 8).map((entry) => {
                  const levelStyle =
                    entry.level === 'error'
                      ? styles.diagnosticLevelError
                      : entry.level === 'warn'
                        ? styles.diagnosticLevelWarn
                        : styles.diagnosticLevelInfo;
                  return (
                    <View key={entry.id} style={styles.diagnosticCard}>
                      <View style={styles.diagnosticHeader}>
                        <Text style={[styles.diagnosticLevel, levelStyle]}>{entry.level.toUpperCase()}</Text>
                        <Text style={styles.diagnosticMeta} numberOfLines={1}>{entry.source}</Text>
                      </View>
                      <Text style={styles.diagnosticMessage}>{entry.message}</Text>
                      <Text style={styles.diagnosticTime}>{new Date(entry.timestamp).toLocaleString()}</Text>
                    </View>
                  );
                })
              )}
            </SectionCard>

            <SectionCard
              title="Balance Config (Dev)"
              summary="Step 68: tune the Day 1 balance layer. Selected preset is applied by the backend on next work action. No app restart required."
            >
              <Text style={styles.inputLabel}>Active Preset</Text>
              <View style={styles.buttonRow}>
                {(Object.keys(BALANCE_PRESETS) as BalancePresetKey[]).map((name) => (
                  <SecondaryButton
                    key={name}
                    label={name === balancePreset ? `● ${name}` : name}
                    onPress={() => handleSelectBalancePreset(name)}
                  />
                ))}
              </View>
              <View style={styles.diagnosticCard}>
                <Text style={styles.diagnosticLevel}>CONFIG: {balancePreset.toUpperCase()}</Text>
                <InfoRow label="Income ×" value={String(BALANCE_PRESETS[balancePreset].income_multiplier)} />
                <InfoRow label="Expense ×" value={String(BALANCE_PRESETS[balancePreset].expense_pressure_multiplier)} />
                <InfoRow label="Stress ×" value={String(BALANCE_PRESETS[balancePreset].stress_sensitivity)} />
                <InfoRow label="Health ×" value={String(BALANCE_PRESETS[balancePreset].health_decay_rate)} />
                <InfoRow label="Opportunity ×" value={String(BALANCE_PRESETS[balancePreset].opportunity_spawn_rate)} />
              </View>
              <Text style={styles.note}>Preset is stored locally. Switch preset via POST /internal/balance/day1-preset to apply server-side.</Text>
            </SectionCard>

            <SectionCard
              title="Playtest Review"
              summary="Internal dev tool. Load Day 1 funnel, screen time, balance telemetry, and friction signals for any player session stored on this device."
            >
              <Text style={styles.inputLabel}>Player ID</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter player ID"
                placeholderTextColor={theme.color.muted}
                value={playtestPlayerId}
                onChangeText={setPlaytestPlayerId}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="off"
              />
              <Text style={styles.inputLabel}>Game Day</Text>
              <TextInput
                style={styles.input}
                placeholder="1"
                placeholderTextColor={theme.color.muted}
                value={playtestGameDay}
                onChangeText={setPlaytestGameDay}
                keyboardType="numeric"
                autoCorrect={false}
              />
              <View style={styles.buttonRow}>
                <SecondaryButton
                  label={playtestLoading ? 'Loading...' : 'Load Report'}
                  onPress={playtestLoading ? undefined : loadPlaytestReport}
                  disabled={playtestLoading || clearingPlaytest}
                />
                <SecondaryButton
                  label={clearingPlaytest ? 'Clearing...' : 'Clear Data'}
                  onPress={clearingPlaytest ? undefined : handleClearPlaytestData}
                  disabled={playtestLoading || clearingPlaytest}
                />
              </View>

              {playtestReport ? (
                <>
                  <View style={styles.diagnosticCard}>
                    <Text style={styles.diagnosticLevel}>FUNNEL ({playtestReport.funnelCompletionRate.completionLabel})</Text>
                    <InfoRow label="Session Started" value={playtestReport.funnelCompletionRate.sessionStarted ? '✓' : '—'} />
                    <InfoRow label="Life Seen" value={playtestReport.funnelCompletionRate.lifeSeen ? '✓' : '—'} />
                    <InfoRow label="Work Seen" value={playtestReport.funnelCompletionRate.workSeen ? '✓' : '—'} />
                    <InfoRow label="First Work Action" value={playtestReport.funnelCompletionRate.firstWorkAction ? '✓' : '—'} />
                    <InfoRow label="Portfolio Seen" value={playtestReport.funnelCompletionRate.portfolioSeen ? '✓' : '—'} />
                    <InfoRow label="Summary Seen" value={playtestReport.funnelCompletionRate.summarySeen ? '✓' : '—'} />
                    <InfoRow label="Day Completed" value={playtestReport.funnelCompletionRate.dayCompleted ? '✓' : '—'} />
                    <InfoRow label="Total Events" value={String(playtestReport.totalEventCount)} />
                    <InfoRow label="Sessions" value={String(playtestReport.sessionCount)} />
                  </View>

                  {playtestReport.balanceTelemetry ? (
                    <View style={styles.diagnosticCard}>
                      <Text style={styles.diagnosticLevel}>BALANCE OUTCOME</Text>
                      <InfoRow label="Starting Cash" value={playtestReport.balanceTelemetry.startingCash != null ? String(playtestReport.balanceTelemetry.startingCash) : '—'} />
                      <InfoRow label="Ending Cash" value={playtestReport.balanceTelemetry.endingCash != null ? String(playtestReport.balanceTelemetry.endingCash) : '—'} />
                      <InfoRow label="Cash Delta" value={playtestReport.balanceTelemetry.cashDelta != null ? String(playtestReport.balanceTelemetry.cashDelta) : '—'} />
                      <InfoRow label="Stress Delta" value={playtestReport.balanceTelemetry.stressDelta != null ? String(playtestReport.balanceTelemetry.stressDelta) : '—'} />
                      <InfoRow label="Health Delta" value={playtestReport.balanceTelemetry.healthDelta != null ? String(playtestReport.balanceTelemetry.healthDelta) : '—'} />
                      <InfoRow label="Expense Pressure" value={playtestReport.balanceTelemetry.expensePressure ?? '—'} />
                      <InfoRow label="Income Earned" value={playtestReport.balanceTelemetry.incomeEarned != null ? String(playtestReport.balanceTelemetry.incomeEarned) : '—'} />
                      <InfoRow label="Ended Positive" value={playtestReport.balanceTelemetry.endedPositive != null ? (playtestReport.balanceTelemetry.endedPositive ? 'Yes' : 'No') : '—'} />
                    </View>
                  ) : null}

                  {playtestReport.frictionSignals ? (
                    <View style={styles.diagnosticCard}>
                      <Text style={styles.diagnosticLevel}>FRICTION SIGNALS</Text>
                      <InfoRow label="Onboarding Skipped" value={playtestReport.frictionSignals.onboardingSkipped ? '⚠ Yes' : 'No'} />
                      <InfoRow label="No Work Action" value={playtestReport.frictionSignals.noWorkActionTaken ? '⚠ Yes' : 'No'} />
                      <InfoRow label="No Portfolio Visit" value={playtestReport.frictionSignals.noPortfolioVisit ? '⚠ Yes' : 'No'} />
                      <InfoRow label="No Business Visit" value={playtestReport.frictionSignals.noBusinessVisit ? '⚠ Yes' : 'No'} />
                      <InfoRow label="Exited Before Summary" value={playtestReport.frictionSignals.exitedBeforeSummary ? '⚠ Yes' : 'No'} />
                      <InfoRow label="Long Idle Count" value={String(playtestReport.frictionSignals.longIdleCount)} />
                    </View>
                  ) : null}

                  {playtestReport.screenTimeSummary.length > 0 ? (
                    <View style={styles.diagnosticCard}>
                      <Text style={styles.diagnosticLevel}>SCREEN TIME</Text>
                      {playtestReport.screenTimeSummary.map((entry) => (
                        <InfoRow
                          key={entry.screen}
                          label={entry.screen}
                          value={`${Math.round(entry.averageMs / 1000)}s avg (${entry.count}x)`}
                        />
                      ))}
                    </View>
                  ) : null}

                  {playtestReport.recentEvents.length > 0 ? (
                    <View style={styles.diagnosticCard}>
                      <Text style={styles.diagnosticLevel}>RECENT EVENTS (last {playtestReport.recentEvents.length})</Text>
                      {playtestReport.recentEvents.slice(0, 12).map((event) => (
                        <View key={event.id} style={styles.diagnosticCard}>
                          <Text style={styles.diagnosticMeta}>{event.eventName}</Text>
                          <Text style={styles.diagnosticTime}>{new Date(event.timestamp).toLocaleString()} · Day {event.gameDay}</Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                </>
              ) : (
                <Text style={styles.note}>Enter a player ID and tap Load Report to inspect playtest data.</Text>
              )}
            </SectionCard>
          </ContentStack>
        </ScrollView>
      </PageContainer>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingTop: theme.spacing.md,
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
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  infoValue: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
    fontWeight: '700',
    flexShrink: 1,
    textAlign: 'right',
  },
  inputLabel: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  input: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    color: theme.color.textPrimary,
    backgroundColor: theme.color.surfaceAlt,
    ...theme.typography.bodyMd,
    minHeight: 44,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    flexWrap: 'wrap',
  },
  note: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  diagnosticCard: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.color.surfaceAlt,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    gap: theme.spacing.xxs,
  },
  diagnosticHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  diagnosticLevel: {
    ...theme.typography.bodySm,
    fontWeight: '800',
  },
  diagnosticLevelInfo: {
    color: '#1d4ed8',
  },
  diagnosticLevelWarn: {
    color: '#b45309',
  },
  diagnosticLevelError: {
    color: '#b91c1c',
  },
  diagnosticMeta: {
    flex: 1,
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '600',
  },
  diagnosticMessage: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
  },
  diagnosticTime: {
    color: theme.color.textSecondary,
    ...theme.typography.caption,
  },
});
