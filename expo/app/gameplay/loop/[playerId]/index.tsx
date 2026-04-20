import { Redirect, useLocalSearchParams } from 'expo-router';

export default function GameplayLoopIndexRoute() {
  const params = useLocalSearchParams<{ playerId?: string }>();
  const rawPlayerId = Array.isArray(params.playerId) ? params.playerId[0] : params.playerId;
  const playerId = String(rawPlayerId || '').trim();

  if (!playerId) {
    return <Redirect href="/gameplay" />;
  }

  return <Redirect href={`/gameplay/loop/${playerId}/brief`} />;
}
