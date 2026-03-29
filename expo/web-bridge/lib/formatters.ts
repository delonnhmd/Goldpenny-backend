function toNumeric(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : Number.NaN;
  }
  return Number.NaN;
}

export function asNumber(value: unknown): number | null {
  const parsed = toNumeric(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function asText(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function firstMeaningfulLine(value: string | null | undefined): string | null {
  if (!value) return null;
  return (
    value
      .split(/(?<=[.!?])\s+/)
      .map((entry) => entry.trim())
      .find(Boolean) ?? null
  );
}

export function pickFirstString(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const entry of value) {
    const candidate = asText(entry);
    if (candidate) return candidate;
  }
  return null;
}

export function formatXgp(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return 'N/A';
  return `${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} xgp`;
}

export function formatSignedXgp(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return 'N/A';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} xgp`;
}