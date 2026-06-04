import type { AnalyzeResponse } from '../lib/types';

// Backend URL. Set VITE_API_BASE at build time (Vercel env var) to point at
// the deployed API. Defaults to the local FastAPI dev server.
const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';

export async function analyzeGame(pgn: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pgn }),
  });

  const data = await res.json();

  if (!res.ok) {
    // FastAPI error responses use { detail: string }
    throw new Error(data.detail ?? `Request failed with status ${res.status}`);
  }

  return data as AnalyzeResponse;
}
