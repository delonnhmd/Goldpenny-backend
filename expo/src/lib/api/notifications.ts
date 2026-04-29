import { fetchApi } from '@/lib/apiClient';

export interface RegisterPushTokenPayload {
  player_id: string;
  push_token: string;
  platform?: 'ios' | 'android' | 'unknown';
}

export interface RegisterPushTokenResponse {
  ok: boolean;
  token_id: string;
  player_id: string;
  platform: string;
}

export interface PushSendResponse {
  ok: boolean;
  player_id: string;
  tokens: number;
  sent: number;
  failed: number;
  tickets: Record<string, unknown>[];
  errors: string[];
  message?: string | null;
}

export async function registerPushToken(payload: RegisterPushTokenPayload): Promise<RegisterPushTokenResponse> {
  return fetchApi<RegisterPushTokenResponse>('/notifications/register-token', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function sendTestPushNotification(
  playerId: string,
  title = 'Test',
  body = 'Push is working',
): Promise<PushSendResponse> {
  return fetchApi<PushSendResponse>('/notifications/test', {
    method: 'POST',
    body: JSON.stringify({
      player_id: playerId,
      title,
      body,
    }),
  });
}
