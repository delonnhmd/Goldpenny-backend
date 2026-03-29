import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import React, { useEffect, useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import AppShell from '@/components/layout/AppShell';
import ContentStack from '@/components/layout/ContentStack';
import PageContainer from '@/components/layout/PageContainer';
import PrimaryButton from '@/components/ui/PrimaryButton';
import SecondaryButton from '@/components/ui/SecondaryButton';
import SectionCard from '@/components/ui/SectionCard';
import { theme } from '@/design/theme';
import { createPlayablePlayer, getPlayablePlayerSummary } from '@/lib/api/onboarding';
import { recordInfo, recordWarning } from '@/lib/logger';

const PLAYER_ID_STORAGE_KEY = 'goldpenny:gameplay:lastPlayerId';
const LEGACY_PLAYER_ID_STORAGE_KEY = 'gameplay:lastPlayerId';
const GENDER_STORAGE_KEY = 'goldpenny:gameplay:lastGender';
const DEFAULT_PLAYER_ID = 'player1';
const DEV_AUTO_CREATE_PLAYER =
  __DEV__
  || process.env.EXPO_PUBLIC_DEV_AUTO_CREATE_PLAYER === 'true'
  || process.env.EXPO_PUBLIC_DEV_AUTO_CREATE_PLAYER === '1';
const DEV_FALLBACK_PLAYER_ID = String(process.env.EXPO_PUBLIC_DEV_FALLBACK_PLAYER_ID || '').trim();

function normalizeErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error || 'Unknown error');
}

function isPlayerMissingError(error: unknown): boolean {
  const message = normalizeErrorMessage(error).toLowerCase();
  return (
    message.includes('player not found')
    || message.includes('profile not found')
    || message.includes('user not found')
  );
}

function isOnboardingBootstrapFailure(error: unknown): boolean {
  const message = normalizeErrorMessage(error).toLowerCase();
  return (
    message.includes('/onboarding/new-player')
    || message.includes('onboarding setup failed')
    || message.includes('unexpected onboarding service error')
  );
}

export default function GameplayIndexRoute() {
  const [playerId, setPlayerId] = useState(DEFAULT_PLAYER_ID);
  const [gender, setGender] = useState<'male' | 'female' | null>(null);
  const [opening, setOpening] = useState(false);
  const [entryError, setEntryError] = useState<string | null>(null);
  const [entryInfo, setEntryInfo] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const remembered =
          (await AsyncStorage.getItem(PLAYER_ID_STORAGE_KEY)) ||
          (await AsyncStorage.getItem(LEGACY_PLAYER_ID_STORAGE_KEY));
        if (remembered) {
          setPlayerId(remembered);
        } else {
          setPlayerId(DEFAULT_PLAYER_ID);
        }

        const rememberedGender = await AsyncStorage.getItem(GENDER_STORAGE_KEY);
        if (rememberedGender === 'male' || rememberedGender === 'female') {
          setGender(rememberedGender);
        } else {
          setGender(null);
        }
      } catch {
        // Ignore storage read issues and allow manual entry.
      }
    })();
  }, []);

  const openDashboard = async () => {
    const requestedPlayerId = playerId.trim();
    let resolvedPlayerId = requestedPlayerId;

    setEntryError(null);
    setEntryInfo(null);

    if (!requestedPlayerId) {
      setEntryError('Enter a player ID before opening gameplay.');
      return;
    }

    if (!gender) {
      setEntryError('Select gender before opening gameplay.');
      return;
    }

    setOpening(true);

    try {
      try {
        await getPlayablePlayerSummary(requestedPlayerId);
        recordInfo('gameplayEntry', 'Playable player validated.', {
          action: 'validate_player',
          context: {
            requestedPlayerId,
          },
        });
      } catch (validationError) {
        if (!isPlayerMissingError(validationError)) {
          const message = normalizeErrorMessage(validationError);
          setEntryInfo('Player validation is temporarily unavailable. Opening gameplay with fallback-safe mode.');
          recordWarning('gameplayEntry', 'Player validation failed with non-not-found error; allowing loop entry.', {
            action: 'validate_player_non_blocking',
            context: {
              requestedPlayerId,
              message,
            },
            error: validationError,
          });
        } else if (DEV_AUTO_CREATE_PLAYER) {
          const created = await createPlayablePlayer({
            player_id: requestedPlayerId,
            display_name: requestedPlayerId,
            gender,
            region: 'suburban',
            starter_job_code: 'retail_worker',
          });
          if (!created.player_id) {
            throw new Error('Backend did not return a player_id for created dev player.');
          }
          resolvedPlayerId = created.player_id;
          setEntryInfo(
            created.load_ready === false
              ? `Created player "${requestedPlayerId}" with minimal starter setup (${resolvedPlayerId}).`
              : `Created a new dev player for "${requestedPlayerId}" and mapped to ${resolvedPlayerId}.`,
          );
          setPlayerId(resolvedPlayerId);
          recordInfo('gameplayEntry', 'Auto-created dev player from missing player id.', {
            action: 'auto_create_player',
            context: {
              requestedPlayerId,
              resolvedPlayerId,
            },
          });
        } else {
          setEntryError(`Player "${requestedPlayerId}" was not found. Enter a valid existing player ID.`);
          recordWarning('gameplayEntry', 'Blocked loop entry because player id was not found.', {
            action: 'validate_player_blocked',
            context: {
              requestedPlayerId,
            },
            error: validationError,
          });
          return;
        }
      }

      try {
        await AsyncStorage.setItem(PLAYER_ID_STORAGE_KEY, resolvedPlayerId);
        await AsyncStorage.setItem(GENDER_STORAGE_KEY, gender);
      } catch {
        // Persisting last player and gender is optional.
      }
      router.push(`/gameplay/loop/${resolvedPlayerId}/brief`);
    } catch (error) {
      const message = normalizeErrorMessage(error);
      if (isOnboardingBootstrapFailure(error) && DEV_FALLBACK_PLAYER_ID) {
        setEntryInfo(`Player creation failed. Routing to fallback player ${DEV_FALLBACK_PLAYER_ID}.`);
        setEntryError(null);
        try {
          await AsyncStorage.setItem(PLAYER_ID_STORAGE_KEY, DEV_FALLBACK_PLAYER_ID);
          await AsyncStorage.setItem(GENDER_STORAGE_KEY, gender);
        } catch {
          // Ignore storage issues for fallback route.
        }
        recordWarning('gameplayEntry', 'Used fallback dev player after onboarding bootstrap failure.', {
          action: 'fallback_player_route',
          context: {
            requestedPlayerId,
            fallbackPlayerId: DEV_FALLBACK_PLAYER_ID,
            message,
          },
          error,
        });
        router.push(`/gameplay/loop/${DEV_FALLBACK_PLAYER_ID}/brief`);
        return;
      }

      const friendlyMessage = isOnboardingBootstrapFailure(error)
        ? 'Could not create a new player right now. Check backend logs, then tap Retry.'
        : message;
      setEntryError(friendlyMessage);
      recordWarning('gameplayEntry', 'Failed to open gameplay loop.', {
        action: 'open_loop',
        context: {
          requestedPlayerId,
          resolvedPlayerId,
          message,
        },
        error,
      });
    } finally {
      setOpening(false);
    }
  };

  return (
    <AppShell
      title="Gold Penny"
      subtitle="Continue your gameplay session"
    >
      <PageContainer>
        <ContentStack style={styles.content}>
          <SectionCard
            title="Gameplay Dashboard"
            summary="Enter your player ID to open the mobile gameplay loop screens."
          >
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              value={playerId}
              onChangeText={setPlayerId}
              placeholder={`Player ID (default: ${DEFAULT_PLAYER_ID})`}
              placeholderTextColor={theme.color.muted}
              editable={!opening}
            />
            <View style={styles.genderSection}>
              <Text style={styles.genderLabel}>Select Gender</Text>
              <View style={styles.genderRow}>
                <Pressable
                  accessibilityRole="button"
                  style={[
                    styles.genderOption,
                    gender === 'male' ? styles.genderOptionActive : null,
                  ]}
                  onPress={() => setGender('male')}
                  disabled={opening}
                >
                  <Text
                    style={[
                      styles.genderOptionText,
                      gender === 'male' ? styles.genderOptionTextActive : null,
                    ]}
                  >
                    Male
                  </Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  style={[
                    styles.genderOption,
                    gender === 'female' ? styles.genderOptionActive : null,
                  ]}
                  onPress={() => setGender('female')}
                  disabled={opening}
                >
                  <Text
                    style={[
                      styles.genderOptionText,
                      gender === 'female' ? styles.genderOptionTextActive : null,
                    ]}
                  >
                    Female
                  </Text>
                </Pressable>
              </View>
            </View>
            <Text style={styles.hint}>The last player ID is stored on this device so you can return to gameplay more quickly.</Text>
            {entryInfo ? <Text style={styles.infoText}>{entryInfo}</Text> : null}
            {entryError ? <Text style={styles.errorText}>{entryError}</Text> : null}
            <PrimaryButton
              label={opening ? 'Opening Gameplay Loop...' : 'Open Gameplay Loop'}
              onPress={openDashboard}
              disabled={opening}
              loading={opening}
            />
            {entryError ? (
              <SecondaryButton
                label="Retry"
                onPress={() => {
                  void openDashboard();
                }}
                disabled={opening}
              />
            ) : null}
          </SectionCard>
        </ContentStack>
      </PageContainer>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingTop: theme.spacing.xl,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    color: theme.color.textPrimary,
    ...theme.typography.bodyMd,
    backgroundColor: theme.color.surfaceAlt,
    minHeight: 44,
  },
  hint: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
  },
  genderSection: {
    gap: theme.spacing.xs,
  },
  genderLabel: {
    color: theme.color.textPrimary,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  genderRow: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  genderOption: {
    flex: 1,
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    minHeight: 42,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: theme.color.surfaceAlt,
  },
  genderOptionActive: {
    borderColor: theme.color.accent,
    backgroundColor: '#dbeafe',
  },
  genderOptionText: {
    color: theme.color.textSecondary,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  genderOptionTextActive: {
    color: theme.color.accent,
  },
  infoText: {
    color: '#1e3a8a',
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
  errorText: {
    color: theme.color.danger,
    ...theme.typography.bodySm,
    fontWeight: '700',
  },
});
