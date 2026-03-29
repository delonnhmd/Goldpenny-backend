import AsyncStorage from '@react-native-async-storage/async-storage';

export const DEBUG = process.env.EXPO_PUBLIC_DEBUG === '1';

const DIAGNOSTIC_STORAGE_KEY = 'goldpenny:diagnostics:recent';
const MAX_DIAGNOSTIC_ENTRIES = 25;
const REDACTED = '[redacted]';
const TRUNCATED = '[truncated]';

export type DiagnosticLevel = 'info' | 'warn' | 'error';

export interface DiagnosticEntry {
	id: string;
	timestamp: string;
	level: DiagnosticLevel;
	source: string;
	action?: string;
	message: string;
	context?: Record<string, unknown>;
}

interface DiagnosticOptions {
	action?: string;
	context?: Record<string, unknown>;
	error?: unknown;
}

let recentDiagnostics: DiagnosticEntry[] = [];
let hydratePromise: Promise<void> | null = null;

function isPlainObject(value: unknown): value is Record<string, unknown> {
	return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isSensitiveKey(key: string): boolean {
	return /(token|authorization|password|secret|signature|private|mnemonic|address|uri|nonce|projectid|header)/i.test(key);
}

function sanitizeValue(value: unknown, depth = 0): unknown {
	if (value == null) return value;
	if (depth > 2) return TRUNCATED;

	if (value instanceof Error) {
		return {
			name: value.name,
			message: value.message,
		};
	}

	if (typeof value === 'string') {
		return value.length > 180 ? `${value.slice(0, 177)}...` : value;
	}

	if (typeof value === 'number' || typeof value === 'boolean') {
		return value;
	}

	if (Array.isArray(value)) {
		return value.slice(0, 6).map((entry) => sanitizeValue(entry, depth + 1));
	}

	if (isPlainObject(value)) {
		const sanitizedEntries = Object.entries(value)
			.slice(0, 12)
			.map(([key, entryValue]) => [key, isSensitiveKey(key) ? REDACTED : sanitizeValue(entryValue, depth + 1)]);
		return Object.fromEntries(sanitizedEntries);
	}

	return String(value);
}

function sanitizeContext(context?: Record<string, unknown>): Record<string, unknown> | undefined {
	if (!context) return undefined;
	return sanitizeValue(context) as Record<string, unknown>;
}

function mergeDiagnostics(entries: DiagnosticEntry[]): DiagnosticEntry[] {
	const deduped = new Map<string, DiagnosticEntry>();
	for (const entry of entries) {
		if (!entry?.id) continue;
		deduped.set(entry.id, entry);
	}
	return Array.from(deduped.values())
		.sort((left, right) => right.timestamp.localeCompare(left.timestamp))
		.slice(0, MAX_DIAGNOSTIC_ENTRIES);
}

async function ensureDiagnosticsHydrated(): Promise<void> {
	if (hydratePromise) return hydratePromise;
	hydratePromise = AsyncStorage.getItem(DIAGNOSTIC_STORAGE_KEY)
		.then((raw) => {
			if (!raw) return;
			try {
				const parsed = JSON.parse(raw);
				if (Array.isArray(parsed)) {
					recentDiagnostics = mergeDiagnostics([
						...recentDiagnostics,
						...parsed.filter((entry): entry is DiagnosticEntry => Boolean(entry && typeof entry === 'object')),
					]);
				}
			} catch {
				recentDiagnostics = mergeDiagnostics(recentDiagnostics);
			}
		})
		.catch(() => {
			recentDiagnostics = mergeDiagnostics(recentDiagnostics);
		})
		.finally(() => {
			hydratePromise = null;
		});
	return hydratePromise;
}

function persistDiagnostics(): void {
	AsyncStorage.setItem(DIAGNOSTIC_STORAGE_KEY, JSON.stringify(recentDiagnostics)).catch(() => {
		if (DEBUG) {
			console.warn('[diagnostics]', 'Failed to persist diagnostics history.');
		}
	});
}

function rememberDiagnostic(entry: DiagnosticEntry): void {
	recentDiagnostics = mergeDiagnostics([entry, ...recentDiagnostics]);
	persistDiagnostics();
}

function writeConsole(level: DiagnosticLevel, entry: DiagnosticEntry): void {
	const label = entry.action ? `${entry.source}:${entry.action}` : entry.source;
	const payload = entry.context ? [entry.context] : [];
	if (level === 'info') {
		if (DEBUG) {
			console.log(`[${label}]`, entry.message, ...payload);
		}
		return;
	}
	if (level === 'warn') {
		console.warn(`[${label}]`, entry.message, ...payload);
		return;
	}
	console.error(`[${label}]`, entry.message, ...payload);
}

function recordDiagnostic(level: DiagnosticLevel, source: string, message: string, options?: DiagnosticOptions): DiagnosticEntry {
	const errorContext = options?.error ? { error: sanitizeValue(options.error) } : undefined;
	const entry: DiagnosticEntry = {
		id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
		timestamp: new Date().toISOString(),
		level,
		source,
		action: options?.action,
		message,
		context: sanitizeContext({
			...(options?.context || {}),
			...(errorContext || {}),
		}),
	};
	rememberDiagnostic(entry);
	writeConsole(level, entry);
	return entry;
}

void ensureDiagnosticsHydrated();

export function toErrorDiagnostic(errorValue: unknown): Record<string, unknown> {
	return sanitizeValue(errorValue) as Record<string, unknown>;
}

export function recordInfo(source: string, message: string, options?: DiagnosticOptions): DiagnosticEntry {
	return recordDiagnostic('info', source, message, options);
}

export function recordWarning(source: string, message: string, options?: DiagnosticOptions): DiagnosticEntry {
	return recordDiagnostic('warn', source, message, options);
}

export function recordError(source: string, message: string, options?: DiagnosticOptions): DiagnosticEntry {
	return recordDiagnostic('error', source, message, options);
}

export async function getRecentDiagnostics(): Promise<DiagnosticEntry[]> {
	await ensureDiagnosticsHydrated();
	return [...recentDiagnostics];
}

export async function clearRecentDiagnostics(): Promise<void> {
	recentDiagnostics = [];
	await AsyncStorage.removeItem(DIAGNOSTIC_STORAGE_KEY);
}

export const log = (tag: string, ...values: unknown[]) => {
	if (DEBUG) console.log(`[${tag}]`, ...values);
};

export const warn = (tag: string, ...values: unknown[]) => console.warn(`[${tag}]`, ...values);
export const error = (tag: string, ...values: unknown[]) => console.error(`[${tag}]`, ...values);
