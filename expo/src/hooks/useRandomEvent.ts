// Gold Penny — random event hook.
// Rolls one deterministic event per game day, persists it, and exposes recovery actions.

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getAvailableRecoveryActions,
  RANDOM_EVENT_POOL,
  rollDailyEvent,
} from '@/lib/gameEvents';
import {
  createEmptyPersistedGameplayState,
  readPersistedGameplayState,
  updatePersistedGameplayState,
} from '@/lib/gameplayPersistence';
import { normalizeMoneyValue } from '@/lib/economySafety';
import { recordInfo, recordWarning } from '@/lib/logger';
import {
  ActiveRandomEvent,
  RandomEventPersistedState,
  RecoveryActionDefinition,
} from '@/types/randomEvent';

export interface RandomEventContract {
  /** The current active event for this game day, or null if none. */
  activeEvent: ActiveRandomEvent | null;
  /** Recovery actions the player can afford right now. */
  availableRecoveryActions: RecoveryActionDefinition[];
  /**
   * Apply a recovery action by ID.
   * Marks the event as resolved and clears it from view.
   */
  applyRecoveryAction: (recoveryActionId: string) => void;
  /** Dismiss the current event without taking a recovery action. */
  dismissEvent: () => void;
}

export function useRandomEvent(
  playerId: string,
  currentGameDay: number,
  cashOnHand: number,
  enabled = true,
): RandomEventContract {
  const [activeEvent, setActiveEvent] = useState<ActiveRandomEvent | null>(null);
  // Track which day has already been processed to avoid duplicate rolls.
  const processedDayRef = useRef<number>(-1);
  // Guard: prevents double-invocation of resolveEvent (e.g. rapid double-tap).
  const resolvingRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setActiveEvent(null);
      return;
    }
    if (!playerId || currentGameDay < 1) return;
    if (processedDayRef.current === currentGameDay) return;
    processedDayRef.current = currentGameDay;
    // New day: reset the resolve guard so the incoming event can be dismissed.
    resolvingRef.current = false;

    let cancelled = false;

    async function loadOrRoll(): Promise<void> {
      // Check AsyncStorage for a persisted event from this day.
      try {
        const persistedState = await readPersistedGameplayState(playerId);
        const persisted = persistedState?.randomEvent;
        if (persisted && !cancelled) {
          if (persisted.sourceDay === currentGameDay) {
            if (persisted.isResolved) {
              // Already resolved for today — respect that, no event shown.
              setActiveEvent(null);
              return;
            }
            const def = RANDOM_EVENT_POOL.find((e) => e.eventId === persisted.eventId);
            if (def) {
              setActiveEvent({ ...def, sourceDay: currentGameDay, isResolved: false });
              return;
            }
            // Unknown eventId (e.g. removed from pool) — fall through to fresh roll.
            await updatePersistedGameplayState(playerId, (current) => {
              const base = current || createEmptyPersistedGameplayState(playerId, currentGameDay);
              if (base.currentDay > currentGameDay) return base;
              return {
                ...base,
                currentDay: Math.max(base.currentDay, currentGameDay),
                randomEvent: null,
              };
            });
          }
          // Persisted event is from a different day — fall through to roll for today.
        }
      } catch (error) {
        recordWarning('randomEvent', 'Failed to load persisted event state.', {
          action: 'load_or_roll',
          context: {
            currentGameDay,
          },
          error,
        });
        // Storage read failed — fall through to fresh roll.
      }

      if (cancelled) return;

      // Roll a new event for this day.
      const definition = rollDailyEvent(playerId, currentGameDay);
      if (definition) {
        const event: ActiveRandomEvent = {
          ...definition,
          sourceDay: currentGameDay,
          isResolved: false,
        };
        if (!cancelled) setActiveEvent(event);
        recordInfo('randomEvent', 'Rolled daily random event.', {
          action: 'load_or_roll',
          context: {
            currentGameDay,
            eventId: definition.eventId,
          },
        });
        try {
          await updatePersistedGameplayState(playerId, (current) => {
            const base = current || createEmptyPersistedGameplayState(playerId, currentGameDay);
            if (base.currentDay > currentGameDay) return base;
            return {
              ...base,
              currentDay: Math.max(base.currentDay, currentGameDay),
              randomEvent: {
              eventId: definition.eventId,
              sourceDay: currentGameDay,
              isResolved: false,
              } as RandomEventPersistedState,
            };
          });
        } catch (error) {
          recordWarning('randomEvent', 'Failed to persist rolled event.', {
            action: 'load_or_roll',
            context: {
              currentGameDay,
              eventId: definition.eventId,
            },
            error,
          });
          // Non-critical — event remains active in memory.
        }
      } else {
        if (!cancelled) setActiveEvent(null);
        // Clear any stale persisted event from a previous day.
        try {
          await updatePersistedGameplayState(playerId, (current) => {
            const base = current || createEmptyPersistedGameplayState(playerId, currentGameDay);
            if (base.currentDay > currentGameDay) return base;
            return {
              ...base,
              currentDay: Math.max(base.currentDay, currentGameDay),
              randomEvent: null,
            };
          });
        } catch (error) {
          recordWarning('randomEvent', 'Failed to clear stale event state.', {
            action: 'load_or_roll',
            context: {
              currentGameDay,
            },
            error,
          });
          // Non-critical.
        }
      }
    }

    loadOrRoll();

    return () => {
      cancelled = true;
    };
  }, [enabled, playerId, currentGameDay]);

  // Mark the current event as resolved in both state and storage.
  const resolveEvent = useCallback(async (): Promise<void> => {
    // Guard against double-invoke from rapid taps on dismiss / apply buttons.
    if (resolvingRef.current) return;
    resolvingRef.current = true;
    const resolvingEventId = activeEvent?.eventId || null;
    setActiveEvent(null);
    try {
      await updatePersistedGameplayState(playerId, (current) => {
        const base = current || createEmptyPersistedGameplayState(playerId, currentGameDay);
        if (base.currentDay !== currentGameDay) return base;

        const persistedEvent = base.randomEvent;
        const resolvedEvent =
          persistedEvent && persistedEvent.sourceDay === currentGameDay && persistedEvent.eventId === resolvingEventId
            ? { ...persistedEvent, isResolved: true }
            : resolvingEventId
              ? {
                  eventId: resolvingEventId,
                  sourceDay: currentGameDay,
                  isResolved: true,
                }
              : persistedEvent;

        return {
          ...base,
          randomEvent: resolvedEvent,
        };
      });
      recordInfo('randomEvent', 'Resolved active random event.', {
        action: 'resolve_event',
        context: {
          currentGameDay,
          eventId: resolvingEventId,
        },
      });
    } catch (error) {
      recordWarning('randomEvent', 'Failed to persist resolved event state.', {
        action: 'resolve_event',
        context: {
          currentGameDay,
          eventId: resolvingEventId,
        },
        error,
      });
      // Non-critical.
    }
  }, [activeEvent?.eventId, currentGameDay, playerId]);

  const applyRecoveryAction = useCallback(
    (recoveryActionId: string): void => {
      const availableAction = getAvailableRecoveryActions(
        normalizeMoneyValue(cashOnHand, { fallback: 0, allowNegative: true }),
      ).find((action) => action.recoveryActionId === recoveryActionId);
      if (!availableAction || !activeEvent) {
        recordWarning('randomEvent', 'Recovery action rejected by local economy validation.', {
          action: 'apply_recovery_action',
          context: {
            recoveryActionId,
            eventId: activeEvent?.eventId || null,
            currentGameDay,
          },
        });
        return;
      }
      recordInfo('randomEvent', 'Applied recovery action to random event.', {
        action: 'apply_recovery_action',
        context: {
          recoveryActionId,
          eventId: activeEvent?.eventId || null,
          currentGameDay,
        },
      });
      resolveEvent();
    },
    [activeEvent, cashOnHand, currentGameDay, resolveEvent],
  );

  const dismissEvent = useCallback((): void => {
    recordInfo('randomEvent', 'Dismissed random event.', {
      action: 'dismiss_event',
      context: {
        eventId: activeEvent?.eventId || null,
        currentGameDay,
      },
    });
    resolveEvent();
  }, [activeEvent?.eventId, currentGameDay, resolveEvent]);

  const availableRecoveryActions = getAvailableRecoveryActions(
    normalizeMoneyValue(cashOnHand, { fallback: 0, allowNegative: true }),
  );

  return { activeEvent, availableRecoveryActions, applyRecoveryAction, dismissEvent };
}
