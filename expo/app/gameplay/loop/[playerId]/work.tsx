import { Redirect, useLocalSearchParams } from 'expo-router';
import React from 'react';

export default function GameplayLoopWorkRoute() {
  const { playerId } = useLocalSearchParams<{ playerId: string }>();
  return <Redirect href={`/gameplay/loop/${playerId}/dashboard`} />;
}
