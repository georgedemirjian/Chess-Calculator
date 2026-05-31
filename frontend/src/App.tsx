import { useEffect, useCallback, useState } from 'react';
import type { AnalyzeResponse, MoveAnalysis } from './lib/types';
import { CLASSIFICATION_META } from './lib/classificationMeta';
import { analyzeGame } from './api/analyze';
import {
  setMuted as setSoundMuted,
  playButtonClick,
  playMove,
  playBest,
  playBlunder,
  playCheckmate,
} from './lib/sounds';
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
  const [viewMode, setViewMode] = useState<'overview' | 'analysis'>('overview');
  const [boardFlipped, setBoardFlipped] = useState(false);
  const [muted, setMuted] = useState<boolean>(() => localStorage.getItem('muted') === 'true');
  // Best-move arrow overlay — defaults ON so first-time users see the feature.
  const [showBestMove, setShowBestMove] = useState<boolean>(
    () => localStorage.getItem('show_best_move') !== 'false',
  );

  useEffect(() => {
    localStorage.setItem('show_best_move', String(showBestMove));
  }, [showBestMove]);

  // Keep the sounds module and localStorage in sync with React muted state.
  useEffect(() => {
    setSoundMuted(muted);
    localStorage.setItem('muted', String(muted));
  }, [muted]);

  const toggleMuted = useCallback(() => {
    const next = !muted;
    setSoundMuted(next);
    if (!next) playButtonClick(); // audible confirm when turning sound back on
    setMuted(next);
  }, [muted]);

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

  // Play a classification-appropriate sound each time the viewed move changes.
  useEffect(() => {
    if (!selectedMove) return;
    if (selectedMove.is_checkmate) { playCheckmate(); return; }
    if (selectedMove.classification === 'best') { playBest(); return; }
    if (selectedMove.classification === 'blunder') { playBlunder(); return; }
    playMove();
  }, [selectedMove]);

  const displayFen = selectedMove?.fen_after ?? STARTING_FEN;

  // Square highlight for the destination square of the selected move
  const destSquare = selectedMove?.uci.slice(2, 4);
  const squareStyles: Record<string, React.CSSProperties> =
    destSquare && selectedMove?.classification
      ? { [destSquare]: { backgroundColor: CLASSIFICATION_META[selectedMove.classification].squareRgba } }
      : {};

  // Eval shown on the bar — 0 when no move is selected (starting position)
  const displayEval = selectedMove?.eval_after ?? 0;

  // Best-move arrow for the displayed position. We deliberately skip when no
  // move is selected (starting position) — there's no game-flow context yet.
  // Skipped when the toggle is off, or when the position is terminal (the
  // engine returns null best move on checkmate / stalemate).
  const bestMoveUci = selectedMove?.best_move_next_uci ?? null;
  const bestMoveArrows =
    showBestMove && bestMoveUci
      ? [{
          startSquare: bestMoveUci.slice(0, 2),
          endSquare:   bestMoveUci.slice(2, 4),
          color:       'rgba(34, 197, 94, 0.55)',  // tailwind green-500 @ 55%
        }]
      : [];

  const hasResult = result !== null;

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-950 text-gray-900 dark:text-gray-100 transition-colors duration-200">
      {/* ── Header ── */}
      <header className="sticky top-0 z-20 bg-white/90 dark:bg-gray-900/80 backdrop-blur border-b border-gray-300 dark:border-gray-800 shadow-sm dark:shadow-none">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">♟</span>
            <span className="font-bold text-gray-900 dark:text-white tracking-tight">Elo Heaven - Chess Analyzer & Elo Estimator</span>
          </div>
          <div className="flex items-center gap-1">
            <BestMoveButton
              enabled={showBestMove}
              onToggle={() => { playButtonClick(); setShowBestMove((v) => !v); }}
            />
            <MuteButton muted={muted} onToggle={toggleMuted} />
            <ThemeToggle dark={dark} onToggle={toggle} />
          </div>
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
                onClick={() => { playButtonClick(); setResult(null); setSelectedIndex(null); setViewMode('overview'); }}
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

            {/* Content grid: board fills available space, right col fixed at 500px */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_500px] gap-4 lg:gap-5 items-start">

              {/* ── Left column: eval bar + board + info bar ── */}
              <div className="flex flex-col gap-2">
                {/* Eval bar alongside the board — same height via items-stretch */}
                <div className="flex gap-2 items-stretch">
                  {/* Eval bar: narrow fixed width, stretches to board height */}
                  <div className="w-7 flex-shrink-0">
                    <EvalBar evalCp={displayEval} mateAfter={selectedMove?.mate_after} />
                  </div>
                  {/* Board fills remaining width */}
                  <div className="flex-1 min-w-0">
                    <ChessBoard
                      fen={displayFen}
                      squareStyles={squareStyles}
                      flipped={boardFlipped}
                      arrows={bestMoveArrows}
                    />
                  </div>
                </div>

                {/* Move info bar + flip button */}
                <BoardInfoBar
                  selectedMove={selectedMove}
                  onFlip={() => { playButtonClick(); setBoardFlipped((f) => !f); }}
                />

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
                      <div className="flex justify-end mb-2">
                        <button
                          onClick={() => { playButtonClick(); setViewMode('overview'); }}
                          title="View game summary (your current move is kept)"
                          className="flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 px-2 py-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5" aria-hidden="true">
                            <path fillRule="evenodd" d="M11.78 5.22a.75.75 0 0 1 0 1.06L8.06 10l3.72 3.72a.75.75 0 1 1-1.06 1.06l-4.25-4.25a.75.75 0 0 1 0-1.06l4.25-4.25a.75.75 0 0 1 1.06 0Z" clipRule="evenodd" />
                          </svg>
                          Overview
                        </button>
                      </div>
                      <EvalGraph
                        moves={result.moves}
                        selectedIndex={selectedIndex}
                        onSelectMove={setSelectedIndex}
                        flipped={boardFlipped}
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

/* ── Best-move arrow toggle ────────────────────────────────────────────────── */

function BestMoveButton({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      aria-label={enabled ? 'Hide best-move arrow' : 'Show best-move arrow'}
      title={enabled ? 'Hide best-move arrow' : 'Show best-move arrow'}
      className={`w-9 h-9 flex items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors duration-150 ${
        enabled
          ? 'text-emerald-600 dark:text-emerald-400'
          : 'text-gray-500 dark:text-gray-400'
      }`}
    >
      {enabled ? (
        /* Diagonal arrow — best move indicator visible */
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
          <path fillRule="evenodd" d="M5.22 14.78a.75.75 0 0 0 1.06 0l7.22-7.22v3.69a.75.75 0 0 0 1.5 0v-5.5a.75.75 0 0 0-.75-.75h-5.5a.75.75 0 0 0 0 1.5h3.69L5.22 13.72a.75.75 0 0 0 0 1.06Z" clipRule="evenodd" />
        </svg>
      ) : (
        /* Diagonal arrow with slash — hidden */
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
          <path fillRule="evenodd" d="M5.22 14.78a.75.75 0 0 0 1.06 0l7.22-7.22v3.69a.75.75 0 0 0 1.5 0v-5.5a.75.75 0 0 0-.75-.75h-5.5a.75.75 0 0 0 0 1.5h3.69L5.22 13.72a.75.75 0 0 0 0 1.06Z" clipRule="evenodd" />
          <path d="M2.97 2.97a.75.75 0 0 1 1.06 0l13 13a.75.75 0 1 1-1.06 1.06l-13-13a.75.75 0 0 1 0-1.06Z" />
        </svg>
      )}
    </button>
  );
}

/* ── Mute button ───────────────────────────────────────────────────────────── */

function MuteButton({ muted, onToggle }: { muted: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      aria-label={muted ? 'Unmute sounds' : 'Mute sounds'}
      className="w-9 h-9 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors duration-150"
    >
      {muted ? (
        /* Speaker X — muted */
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
          <path d="M10 3.75a.75.75 0 0 0-1.264-.546L4.703 7H3.167a.75.75 0 0 0-.7.495A6.001 6.001 0 0 0 2.5 10c0 .85.174 1.65.467 2.383a.75.75 0 0 0 .7.617H4.7l4.038 3.796A.75.75 0 0 0 10 16.25V3.75Z" />
          <path d="M13.28 7.22a.75.75 0 0 0-1.06 1.06L13.44 9.5l-1.22 1.22a.75.75 0 1 0 1.06 1.06L14.5 10.56l1.22 1.22a.75.75 0 1 0 1.06-1.06L15.56 9.5l1.22-1.22a.75.75 0 0 0-1.06-1.06L14.5 8.44l-1.22-1.22Z" />
        </svg>
      ) : (
        /* Speaker wave — unmuted */
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
          <path d="M10 3.75a.75.75 0 0 0-1.264-.546L4.703 7H3.167a.75.75 0 0 0-.7.495A6.001 6.001 0 0 0 2.5 10c0 .85.174 1.65.467 2.383a.75.75 0 0 0 .7.617H4.7l4.038 3.796A.75.75 0 0 0 10 16.25V3.75Z" />
          <path d="M15.95 5.05a.75.75 0 0 0-1.06 1.06A6.5 6.5 0 0 1 16.5 10a6.5 6.5 0 0 1-1.61 4.39.75.75 0 0 0 1.06 1.06A8 8 0 0 0 18 10a8 8 0 0 0-2.05-4.95Z" />
          <path d="M13.5 7.5a.75.75 0 0 0-1.06 1.06A3.5 3.5 0 0 1 13.5 10a3.5 3.5 0 0 1-1.06 1.94.75.75 0 0 0 1.06 1.06A5 5 0 0 0 15 10a5 5 0 0 0-1.5-2.5Z" />
        </svg>
      )}
    </button>
  );
}

/* ── Board info bar ────────────────────────────────────────────────────────── */

function BoardInfoBar({
  selectedMove,
  onFlip,
}: {
  selectedMove: MoveAnalysis | null;
  onFlip: () => void;
}) {
  const flipBtn = (
    <button
      onClick={onFlip}
      title="Flip board"
      className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
    >
      {/* arrows-up-down */}
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
        <path fillRule="evenodd" d="M2.24 6.8a.75.75 0 0 0 1.06-.04l1.95-2.1v8.59a.75.75 0 0 0 1.5 0V4.66l1.95 2.1a.75.75 0 1 0 1.1-1.02l-3.25-3.5a.75.75 0 0 0-1.1 0L2.2 5.74a.75.75 0 0 0 .04 1.06Zm8 6.4a.75.75 0 0 0-.04 1.06l3.25 3.5a.75.75 0 0 0 1.1 0l3.25-3.5a.75.75 0 1 0-1.1-1.02l-1.95 2.1V6.75a.75.75 0 0 0-1.5 0v8.59l-1.95-2.1a.75.75 0 0 0-1.06-.04Z" clipRule="evenodd" />
      </svg>
    </button>
  );

  if (!selectedMove) {
    return (
      <div className="flex items-center justify-between px-3 py-1">
        <p className="text-xs text-gray-400 dark:text-gray-600">
          Starting position · select a move to navigate
        </p>
        {flipBtn}
      </div>
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
        {selectedMove.eval_after !== null && (
          <EvalPill value={selectedMove.eval_after} mateAfter={selectedMove.mate_after} />
        )}
        {meta && <span className={`font-semibold ${meta.color}`}>{meta.label}</span>}
        {selectedMove.cp_loss !== null && selectedMove.cp_loss > 0 && (
          <span className="text-gray-400 dark:text-gray-500 text-xs tabular-nums">
            −{selectedMove.cp_loss} cp
          </span>
        )}
        {flipBtn}
      </div>
    </div>
  );
}

function EvalPill({ value, mateAfter }: { value: number; mateAfter?: number | null }) {
  const capped = Math.max(-1000, Math.min(1000, value));
  const isWhiteAhead = capped >= 0;
  const hasMate = mateAfter !== undefined && mateAfter !== null;
  const display = hasMate
    ? (isWhiteAhead ? '+' : '-') + (mateAfter === 0 ? 'M' : `M${Math.abs(mateAfter)}`)
    : Math.abs(capped) >= 1000
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
