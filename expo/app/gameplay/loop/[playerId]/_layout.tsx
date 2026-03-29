import React from 'react';
import { Redirect, Slot, useLocalSearchParams } from 'expo-router';

import { GameplayLoopProvider } from '@/features/gameplayLoop/context';
import { OnboardingProvider } from '@/features/onboarding';
import { PlaytestProvider } from '@/features/playtest';

export default function GameplayLoopLayout() {
  const params = useLocalSearchParams<{ playerId?: string }>();
  const rawPlayerId = Array.isArray(params.playerId) ? params.playerId[0] : params.playerId;
  const playerId = String(rawPlayerId || '').trim();

  if (!playerId) {
    return <Redirect href="/gameplay" />;
  }

  return (
    <GameplayLoopProvider playerId={playerId}>
      <PlaytestProvider playerId={playerId}>
        <OnboardingProvider playerId={playerId}>
          <Slot />
        </OnboardingProvider>
      </PlaytestProvider>
    </GameplayLoopProvider>
  );
}
