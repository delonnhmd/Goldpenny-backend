import { Redirect, useLocalSearchParams } from 'expo-router';

export default function LegacyWalletRedirect() {
  const { playerId } = useLocalSearchParams<{ playerId: string }>();
  return <Redirect href={`/gameplay/loop/${playerId}/portfolio`} />;
}
