const DEFAULT_DEEP_LINK = 'goldpenny://gameplay';
const DEFAULT_CANONICAL_HOST = 'goldpenny.pennyfloat.com';

function clean(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function normalizeBaseUrl(value: string | null | undefined): string | null {
  const raw = clean(value);
  if (!raw) return null;
  const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const parsed = new URL(withProtocol);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return null;
  }
}

export function resolveBackendBaseUrl(override?: string | null): string | null {
  return (
    normalizeBaseUrl(override) ??
    normalizeBaseUrl(process.env.GOLDPENNY_BACKEND_URL) ??
    normalizeBaseUrl(process.env.NEXT_PUBLIC_GOLDPENNY_BACKEND_URL)
  );
}

export function resolvePlayerId(override?: string | null): string | null {
  return clean(override) ?? clean(process.env.GOLDPENNY_DEFAULT_PLAYER_ID) ?? clean(process.env.NEXT_PUBLIC_GOLDPENNY_DEFAULT_PLAYER_ID);
}

export function getCanonicalHost(): string {
  return clean(process.env.NEXT_PUBLIC_GOLDPENNY_CANONICAL_HOST) ?? DEFAULT_CANONICAL_HOST;
}

export function getDeepLinkBase(): string {
  return clean(process.env.NEXT_PUBLIC_GOLDPENNY_DEEP_LINK) ?? DEFAULT_DEEP_LINK;
}

export function buildGameplayDeepLink(playerId?: string | null): string {
  const base = getDeepLinkBase();
  const safePlayerId = clean(playerId);
  if (!safePlayerId) return base;
  const separator = base.includes('?') ? '&' : '?';
  return `${base}${separator}playerId=${encodeURIComponent(safePlayerId)}`;
}