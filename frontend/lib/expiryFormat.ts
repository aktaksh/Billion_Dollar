export function formatExpiryDate(expiry: string | null | undefined): string {
  if (!expiry) return "—";
  const raw = expiry.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  if (/^\d{8}$/.test(raw)) {
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
  }
  return raw;
}

export function dteFromExpiry(expiry: string): number {
  const iso = formatExpiryDate(expiry);
  const ms = new Date(`${iso}T00:00:00Z`).getTime() - Date.now();
  if (!Number.isFinite(ms)) return 0;
  return Math.max(0, Math.ceil(ms / 86_400_000));
}
