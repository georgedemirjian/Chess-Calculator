import type { AnalyzeResponse } from '../lib/types';

// Pre-analyzed example games are shipped as static JSON in /public/examples/.
// Fetching them is a same-origin static read — no backend hop, no Stockfish wait.
export async function loadExampleGame(slug: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${import.meta.env.BASE_URL}examples/${slug}.json`);
  if (!res.ok) {
    throw new Error(`Could not load example "${slug}" (HTTP ${res.status}).`);
  }
  return (await res.json()) as AnalyzeResponse;
}
