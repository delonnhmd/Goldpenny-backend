import React from 'react';
import { Redirect, useLocalSearchParams } from 'expo-router';

export default function GameplayLoopDashboardRoute() {
  const params = useLocalSearchParams<{ playerId?: string | string[] }>();
  const rawPlayerId = Array.isArray(params.playerId) ? params.playerId[0] : params.playerId;
  const playerId = String(rawPlayerId || '').trim();

  return <Redirect href={`/gameplay/loop/${playerId}/work`} />;
}
