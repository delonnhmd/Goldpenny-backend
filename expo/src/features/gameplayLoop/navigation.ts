import type { AppBottomNavItem } from '@/components/layout/AppBottomNav';
import type { OnboardingRouteKey } from '@/features/onboarding/context';

type GameplayBottomNavKey =
  | 'map'
  | 'brief'
  | 'dashboard'
  | 'work'
  | 'business'
  | 'market'
  | 'life';

const gameplayBottomNavConfig: {
  key: GameplayBottomNavKey;
  label: string;
  icon: AppBottomNavItem['icon'];
}[] = [
  { key: 'map', label: 'Map', icon: 'map-outline' },
  { key: 'brief', label: 'Brief', icon: 'file-document-outline' },
  { key: 'dashboard', label: 'Dashboard', icon: 'view-dashboard-outline' },
  { key: 'work', label: 'Work', icon: 'briefcase-outline' },
  { key: 'business', label: 'Business', icon: 'storefront-outline' },
  { key: 'market', label: 'Wallet', icon: 'wallet-outline' },
  { key: 'life', label: 'Life', icon: 'heart-outline' },
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
