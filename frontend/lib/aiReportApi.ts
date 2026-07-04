const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function generateAiReport(symbol?: string): Promise<Record<string, unknown>> {
  const body = symbol ? JSON.stringify({ symbol }) : "{}";
  const res = await fetch(`${BASE}/api/ai-report/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  if (!res.ok) throw new Error(`AI Report generation failed: ${res.status}`);
  return res.json();
}

export function downloadAiReportUrl(format: "json" | "md"): string {
  return `${BASE}/api/ai-report/download/${format}`;
}
