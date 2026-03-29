// Gold Penny — Soft Launch: shared types

export interface SoftLaunchStatus {
  is_member: boolean;
  cohort_tag: string | null;
  joined_at: string | null;
}

export interface FeedbackPayload {
  session_id?: string;
  game_day: number;
  rating: number;
  response_confusing?: string;
  response_hard?: string;
  response_interesting?: string;
}

export interface IssuePayload {
  session_id?: string;
  game_day?: number;
  description: string;
  category?: 'bug' | 'friction' | 'ui' | 'balance' | 'other';
  severity?: 'low' | 'medium' | 'high' | 'blocker';
  extra_context_json?: string;
}

export type IssueCategory = 'bug' | 'friction' | 'ui' | 'balance' | 'other';
export type IssueSeverity = 'low' | 'medium' | 'high' | 'blocker';
