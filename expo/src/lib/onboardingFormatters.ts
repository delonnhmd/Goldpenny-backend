import { OnboardingStatus } from '@/types/onboarding';

export function onboardingStatusLabel(status: OnboardingStatus): string {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'completed') return 'Completed';
  if (normalized === 'skipped') return 'Skipped';
  if (normalized === 'in_progress') return 'In Progress';
  return 'Not Started';
}

export function onboardingStatusTone(status: OnboardingStatus): string {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'completed') return '#166534';
  if (normalized === 'skipped') return '#475569';
  if (normalized === 'in_progress') return '#1d4ed8';
  return '#334155';
}

export function onboardingSectionLabel(sectionKey: string | null | undefined): string {
  const key = String(sectionKey || '').trim();
  if (!key) return 'Current step';
  return key
    .split('_')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');
}

export function onboardingProgressRatio(progressLabel: string | null | undefined): number {
  const raw = String(progressLabel || '');
  const [left, right] = raw.split('/');
  const completed = Number(left);
  const total = Number((right || '').split(' ')[0]);
  if (!Number.isFinite(completed) || !Number.isFinite(total) || total <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(1, completed / total));
}

export function unlockStatusLabel(unlocked: boolean): string {
  return unlocked ? 'Unlocked' : 'Locked';
}

