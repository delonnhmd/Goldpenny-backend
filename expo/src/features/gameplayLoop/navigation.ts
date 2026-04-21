import type { AppBottomNavItem } from '@/components/layout/AppBottomNav';
import type { OnboardingRouteKey } from '@/features/onboarding/context';

type GameplayBottomNavKey =
  | 'map'
  | 'life'
  | 'dashboard'
  | 'business'
  | 'market';

const gameplayBottomNavConfig: {
  key: GameplayBottomNavKey;
  label: string;
  icon: AppBottomNavItem['icon'];
}[] = [
  { key: 'map', label: 'Map', icon: 'map-outline' },
  { key: 'life', label: 'Life', icon: 'heart-outline' },
  { key: 'dashboard', label: 'Work', icon: 'view-dashboard-outline' },
  { key: 'business', label: 'Business', icon: 'storefront-outline' },
  { key: 'market', label: 'Wallet', icon: 'wallet-outline' },
];

export function buildGameplayBottomNavItems(
  navigateTo: (route: OnboardingRouteKey) => boolean,
): AppBottomNavItem[] {
  return gameplayBottomNavConfig.map((item) => ({
    ...item,
    onPress: () => {
      navigateTo(item.key);
    },
  }));
}
