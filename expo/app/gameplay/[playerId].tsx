import React from 'react';
import { Redirect, useLocalSearchParams } from 'expo-router';

import { useAuth } from '@/features/auth';

export default function GameplayPlayerRoute() {
  const auth = useAuth();
  const params = useLocalSearchParams<{ playerId?: string }>();
  const rawPlayerId = Array.isArray(params.playerId) ? params.playerId[0] : params.playerId;
  const playerId = String(rawPlayerId || '').trim();
  const linkedPlayerId = String(auth.session?.player_profile?.id || '').trim();

  if (auth.status === 'loading') {
    return null;
  }

  if (!auth.isAuthenticated || !auth.session) {
    return <Redirect href="/auth/login" />;
  }

  if (!linkedPlayerId) {
    return <Redirect href="/auth/create-player" />;
  }

  if (!playerId) {
    return <Redirect href="/gameplay" />;
  }

  if (playerId !== linkedPlayerId) {
    return <Redirect href={`/gameplay/loop/${linkedPlayerId}/brief`} />;
  }

  return <Redirect href={`/gameplay/loop/${playerId}/brief`} />;
}
