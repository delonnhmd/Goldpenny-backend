export interface AccountSummary {
  id: string;
  email: string;
  auth_provider: string;
  status: string;
  created_at: string;
  last_login_at: string | null;
  password_updated_at: string | null;
}

export interface PlayerProfileSummary {
  id: string;
  display_name: string | null;
  gender: string | null;
  region: string | null;
  cash_xgp: number;
  debt_xgp: number;
  health: number;
  stress: number;
  current_job: string | null;
  created_at: string | null;
  load_ready: boolean;
}

export interface AuthSessionResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  account: AccountSummary;
  player_profile: PlayerProfileSummary | null;
}

export interface AuthSessionStateResponse {
  account: AccountSummary;
  player_profile: PlayerProfileSummary | null;
}

export interface ForgotPasswordResponse {
  message: string;
  reset_token: string | null;
  reset_url: string | null;
  expires_at: string | null;
}
