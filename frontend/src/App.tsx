import { useEffect, useCallback, useState } from 'react';
import type { AnalyzeResponse, MoveAnalysis } from './lib/types';
import { CLASSIFICATION_META } from './lib/classificationMeta';
import { analyzeGame } from './api/analyze';
import ThemeToggle from './components/ThemeToggle';
import PgnInput from './components/PgnInput';
import GameSummary from './components/GameSummary';
import ChessBoard from './components/ChessBoard';
import EvalBar from './components/EvalBar';
import EvalGraph from './components/EvalGraph';
import MoveList from './components/MoveList';
import GameOverview from './components/GameOverview';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function useTheme() {
  const [dark, setDark] = useState<boolean>(() => {
    const stored = localStorage.getItem('theme');
    if (stored) return stored === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  return { dark, toggle: () => setDark((d) => !d) };
}

export default function App() {
  const { dark, toggle } = useTheme();

  const [pgn, setPgn] = useState('');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  // 'overview' shows the GameOverview panel; 'analysis' shows the eval graph + move list.
  const [viewMode, setViewMode] = useState<'overview' | 'analysis'>('overview');

  const handleAnalyze = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedIndex(null);
    setViewMode('overview');
    try {
      const data = await analyzeGame(pgn);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed.');
    } finally {
      setLoading(false);
    }
  }, [pgn]);

  // Keyboard navigation through moves (only active during analysis view)
  useEffect(() => {
    if (!result || viewMode !== 'analysis') return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        setSelectedIndex((i) => Math.min((i ?? -1) + 1, result.moves.length - 1));
      } else if (e.key === 'ArrowLeft') {
        setSelectedIndex((i) => (i === null || i === 0 ? null : i - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(null);
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(result.moves.length - 1);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [result, viewMode]);

  const selectedMove: MoveAnalysis | null =
    result && selectedIndex !== null ? result.moves[selectedIndex] : null;

  const displayFen = selectedMove?.fen_after ?? STARTING_FEN;

  // Square highlight for the destination square of the selected move
  const destSquare = selectedMove?.uci.slice(2, 4);
  const squareStyles: Record<string, React.CSSProperties> =
    destSquare && selectedMove?.classification
      ? { [destSquare]: { backgroundColor: CLASSIFICATION_META[selectedMove.classification].squareRgba } }
      : {};

  // Eval shown on the bar — 0 when no move is selected (starting position)
  const displayEval = selectedMove?.eval_after ?? 0;

  const hasResult = result !== null;

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-950 text-gray-900 dark:text-gray-100 transition-colors duration-200">
      {/* ── Header ── */}
      <header className="sticky top-0 z-20 bg-white/90 dark:bg-gray-900/80 backdrop-blur border-b border-gray-300 dark:border-gray-800 shadow-sm dark:shadow-none">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">♟</span>
            <span className="font-bold text-gray-900 dark:text-white tracking-tight">Chess Analyzer</span>
          </div>
          <ThemeToggle dark={dark} onToggle={toggle} />
        </div>
      </header>

      {/* ── Main ── */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {!hasResult ? (
          /* ── Landing: centered PGN input ── */
          <div className="max-w-xl mx-auto pt-12">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold text-gray-900 dark:text-white tracking-tight mb-2">
                Analyze your game
              </h1>
              <p className="text-gray-500 dark:text-gray-400">
                Paste a PGN and get Stockfish-powered move analysis with centipawn evaluation.
              </p>
            </div>
            <div className="bg-white dark:bg-gray-900 rounded-2xl border-2 border-gray-300 dark:border-gray-800 p-6 shadow-md dark:shadow-none">
              <PgnInput pgn={pgn} loading={loading} onChange={setPgn} onAnalyze={handleAnalyze} />
              {error && (
                <div className="mt-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-700 dark:text-red-400">
                  {error}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* ── Analysis view ── */
          <div className="flex flex-col gap-4">
            {/* Back + summary bar */}
            <div className="flex items-start gap-3">
              <button
                onClick={() => { setResult(null); setSelectedIndex(null); setViewMode('overview'); }}
                className="flex-shrink-0 mt-0.5 flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                  <path fillRule="evenodd" d="M17 10a.75.75 0 0 1-.75.75H5.612l4.158 3.96a.75.75 0 1 1-1.04 1.08l-5.5-5.25a.75.75 0 0 1 0-1.08l5.5-5.25a.75.75 0 1 1 1.04 1.08L5.612 9.25H16.25A.75.75 0 0 1 17 10Z" clipRule="evenodd" />
                </svg>
                New game
              </button>
              <div className="flex-1 min-w-0">
                <GameSummary result={result} />
              </div>
            </div>

            {/* Content grid: left col wider, right col fixed narrower */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4 lg:gap-5 items-start">

              {/* ── Left column: eval bar + board + info bar ── */}
              <div className="flex flex-col gap-2">
                {/* Eval bar alongside the board — same height via items-stretch */}
                <div className="flex gap-2 items-stretch">
                  {/* Eval bar: narrow fixed width, stretches to board height */}
                  <div className="w-7 flex-shrink-0">
                    <EvalBar evalCp={displayEval} />
                  </div>
                  {/* Board fills remaining width */}
                  <div className="flex-1 min-w-0">
                    <ChessBoard fen={displayFen} squareStyles={squareStyles} />
                  </div>
                </div>

                {/* Move info bar — spans the full width below the board row */}
                <BoardInfoBar selectedMove={selectedMove} />

                {/* Mobile: collapsed new-game input */}
                <details className="lg:hidden group">
                  <summary className="text-sm text-gray-500 dark:text-gray-400 cursor-pointer select-none list-none flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"
                      className="w-4 h-4 rotate-0 group-open:rotate-90 transition-transform">
                      <path fillRule="evenodd" d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
                    </svg>
                    Analyze another game
                  </summary>
                  <div className="mt-3 bg-white dark:bg-gray-900 rounded-xl border-2 border-gray-300 dark:border-gray-800 p-4 shadow-sm dark:shadow-none">
                    <PgnInput pgn={pgn} loading={loading} onChange={setPgn} onAnalyze={handleAnalyze} />
                  </div>
                </details>
              </div>

              {/* ── Right column: overview OR graph + move list ── */}
              <div className="flex flex-col gap-4 lg:sticky lg:top-20">
                {viewMode === 'overview' ? (
                  <GameOverview result={result} onStart={() => setViewMode('analysis')} />
                ) : (
                  <>
                    <div className="bg-white dark:bg-gray-900 rounded-xl border-2 border-gray-300 dark:border-gray-700 p-4 shadow-md dark:shadow-none">
                      <EvalGraph
                        moves={result.moves}
                        selectedIndex={selectedIndex}
                        onSelectMove={setSelectedIndex}
                      />
                    </div>
                    <div
                      className="bg-white dark:bg-gray-900 rounded-xl border-2 border-gray-300 dark:border-gray-700 p-4 flex flex-col shadow-md dark:shadow-none"
                      style={{ maxHeight: '420px' }}
                    >
                      <MoveList
                        moves={result.moves}
                        selectedIndex={selectedIndex}
                        onSelectMove={setSelectedIndex}
                      />
                    </div>
                    <p className="text-center text-xs text-gray-400 dark:text-gray-600">
                      ← → step · ↑ start · ↓ end · click move or graph to jump
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/* ── Board info bar ────────────────────────────────────────────────────────── */

function BoardInfoBar({ selectedMove }: { selectedMove: MoveAnalysis | null }) {
  if (!selectedMove) {
    return (
      <p className="text-center text-xs text-gray-400 dark:text-gray-600 py-1">
        Starting position · select a move to navigate
      </p>
    );
  }

  const cls = selectedMove.classification;
  const meta = cls ? CLASSIFICATION_META[cls] : null;

  return (
    <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-white dark:bg-gray-800 border-2 border-gray-200 dark:border-gray-700 shadow-sm dark:shadow-none text-sm">
      <span className="font-mono font-semibold text-gray-800 dark:text-gray-200">
        {selectedMove.move_number}.{selectedMove.color === 'black' ? '..' : ''}&nbsp;{selectedMove.san}
      </span>
      <div className="flex items-center gap-3">
        {selectedMove.eval_after !== null && <EvalPill value={selectedMove.eval_after} />}
        {meta && <span className={`font-semibold ${meta.color}`}>{meta.label}</span>}
        {selectedMove.cp_loss !== null && selectedMove.cp_loss > 0 && (
          <span className="text-gray-400 dark:text-gray-500 text-xs tabular-nums">
            −{selectedMove.cp_loss} cp
          </span>
        )}
      </div>
    </div>
  );
}

function EvalPill({ value }: { value: number }) {
  const capped = Math.max(-1000, Math.min(1000, value));
  const isWhiteAhead = capped >= 0;
  const display =
    Math.abs(capped) >= 1000
      ? isWhiteAhead ? '+M' : '-M'
      : isWhiteAhead
        ? `+${(capped / 100).toFixed(1)}`
        : (capped / 100).toFixed(1);

  return (
    <span className={`text-xs font-mono font-bold px-1.5 py-0.5 rounded ${
      isWhiteAhead
        ? 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
        : 'bg-gray-700 dark:bg-gray-200 text-gray-100 dark:text-gray-900'
    }`}>
      {display}
    </span>
  );
}
