import type { NewsSignalLabel, ProviderStatus } from "@/types/newsIntelligence";

type Props = {
  label: NewsSignalLabel | string;
  kind?: "signal" | "provider";
};

const SIGNAL_CLASS: Record<string, string> = {
  Bullish: "ni-badge-bullish",
  Bearish: "ni-badge-bearish",
  Neutral: "ni-badge-neutral",
  Unavailable: "ni-badge-unavailable",
};

const PROVIDER_CLASS: Record<string, string> = {
  Online: "ni-badge-bullish",
  Partial: "ni-badge-neutral",
  Error: "ni-badge-bearish",
};

export default function NewsStatusBadge({ label, kind = "signal" }: Props) {
  const cls =
    kind === "provider"
      ? PROVIDER_CLASS[label] ?? "ni-badge-unavailable"
      : SIGNAL_CLASS[label] ?? "ni-badge-unavailable";

  return <span className={`ni-badge ${cls}`}>{label}</span>;
}

export function providerStatusClass(status: ProviderStatus): string {
  return PROVIDER_CLASS[status] ?? "ni-badge-unavailable";
}
