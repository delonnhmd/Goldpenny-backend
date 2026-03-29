// Gold Penny — Soft Launch: API client functions

import { fetchApi } from '@/lib/apiClient';

import { FeedbackPayload, IssuePayload, SoftLaunchStatus } from './types';

export async function joinSoftLaunch(inviteCode: string): Promise<{
  cohort_tag: string;
  is_approved: boolean;
  message: string;
}> {
  return fetchApi('/soft-launch/join', {
    method: 'POST',
    body: JSON.stringify({ invite_code: inviteCode }),
  });
}

export async function fetchSoftLaunchStatus(): Promise<SoftLaunchStatus> {
  return fetchApi('/soft-launch/status');
}

export async function submitFeedback(payload: FeedbackPayload): Promise<{
  ok: boolean;
  feedback_id: string;
}> {
  return fetchApi('/soft-launch/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function submitIssue(payload: IssuePayload): Promise<{
  ok: boolean;
  issue_id: string;
}> {
  return fetchApi('/soft-launch/issue', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
