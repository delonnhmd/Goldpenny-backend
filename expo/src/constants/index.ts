// Gold Penny production constants.
// EXPO_PUBLIC_BACKEND is required for gameplay API requests.
// Default to the hosted Render API so builds still connect even when
// EXPO_PUBLIC_BACKEND is missing. Local override remains available in Settings.
export const BACKEND = process.env.EXPO_PUBLIC_BACKEND ?? 'https://goldpenny-backend.onrender.com';
// Build timestamp to help verify OTA updates and bust caches.
export const BUILD_TS = '2026-03-23T00:00:00Z';
