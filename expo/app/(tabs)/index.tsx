import { Redirect } from 'expo-router';

// Gold Penny home redirects directly into the gameplay dashboard.
export default function HomeTab() {
  return <Redirect href="/gameplay" />;
}
