export type CommitmentStatus =
  | 'inactive'
  | 'active'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | 'replaced'
  | string;

export type CommitmentAlignmentLabel = 'aligned' | 'mostly_aligned' | 'drifting' | 'off_track' | 'none' | string;
export type CommitmentDriftLevel = 'none' | 'low' | 'moderate' | 'high' | string;

export interface AvailableCommitmentItem {
  commitment_key: string;
  title: string;
  description: string;
  suggested_duration_days: number;
  expected_upside: string;
  expected_downside: string;
  adherence_focus: string[];
  current_fit_label: string;
  risk_label: string;
  debug_meta?: Record<string, unknown>;
}

export interface AvailableCommitmentsResponse {
  player_id: string;
  as_of_date: string;
  items: AvailableCommitmentItem[];
  debug_meta?: Record<string, unknown>;
}

export interface CommitmentActivationRequest {
  commitment_key: string;
  duration_days?: number;
  replace_active?: boolean;
}

export interface ActiveCommitmentResponse {
  player_id: string;
  as_of_date: string;
  status: CommitmentStatus;
  commitment_key: string;
  title: string;
  description: string;
  duration_days: number;
  start_date?: string | null;
  target_end_date?: string | null;
  days_remaining: number;
  adherence_score: number;
  momentum_score: number;
  alignment_label: CommitmentAlignmentLabel;
  drift_level: CommitmentDriftLevel;
  days_followed: number;
  days_drifted: number;
  likely_payoff: string;
  likely_downside: string;
  summary: string;
  suggested_correction?: string | null;
  reward_summary?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface CommitmentSummaryResponse {
  player_id: string;
  as_of_date: string;
  active_commitment: ActiveCommitmentResponse;
  debug_meta?: Record<string, unknown>;
}

export interface CommitmentFeedbackItem {
  severity: 'success' | 'info' | 'warning' | 'critical' | string;
  title: string;
  body: string;
  commitment_key: string;
  feedback_type: 'on_track' | 'drifting' | 'off_track' | 'inactive' | 'driver' | string;
  suggested_correction?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface CommitmentFeedbackResponse {
  player_id: string;
  as_of_date: string;
  items: CommitmentFeedbackItem[];
  debug_meta?: Record<string, unknown>;
}

export interface CommitmentHistoryItem {
  commitment_key: string;
  title: string;
  status: CommitmentStatus;
  start_date?: string | null;
  target_end_date?: string | null;
  completed_on_date?: string | null;
  adherence_score: number;
  momentum_score: number;
  days_followed: number;
  days_drifted: number;
  completion_summary?: string | null;
  reward_summary?: string | null;
  debug_meta?: Record<string, unknown>;
}

export interface CommitmentHistoryResponse {
  player_id: string;
  as_of_date: string;
  entries: CommitmentHistoryItem[];
  debug_meta?: Record<string, unknown>;
}
