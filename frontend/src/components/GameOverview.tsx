import type { AnalyzeResponse, MoveClassification } from '../lib/types';
import { CLASSIFICATION_META } from '../lib/classificationMeta';

// Lichess-inspired ACPL → accuracy mapping, clamped to [0, 100].
function acplToAccuracy(acpl: number): number {
  return Math.max(0, Math.min(100, 100 * Math.exp(-0.008 * acpl)));
}

const ROWS: MoveClassification[] = ['best', 'excellent', 'good', 'inaccuracy', 'mistake', 'blunder'];

function countClassifications(
  moves: AnalyzeResponse['moves'],
  color: 'white' | 'black',
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const m of moves) {
    if (m.color === color && m.classification && m.classification !== 'forced') {
      counts[m.classification] = (counts[m.classification] ?? 0) + 1;
    }
  }
  return counts;
}

interface Props {
  result: AnalyzeResponse;
  onStart: () => void;
}

export default function GameOverview({ result, onStart }: Props) {
  const whiteCounts = countClassifications(result.moves, 'white');
  const blackCounts = countClassifications(result.moves, 'black');
  const whiteAccuracy = acplToAccuracy(result.acpl_white);
  const blackAccuracy = acplToAccuracy(result.acpl_black);

  return (
    <div className="flex flex-col gap-0 bg-white dark:bg-gray-900 rounded-xl border-2 border-gray-300 dark:border-gray-700 shadow-md dark:shadow-none overflow-hidden">
      {/* Player header */}
      <div className="grid grid-cols-2 border-b-2 border-gray-200 dark:border-gray-800">
        <div className="flex items-center gap-2 px-4 py-3 border-r-2 border-gray-200 dark:border-gray-800">
          <span className="w-3.5 h-3.5 rounded-sm bg-gray-100 border border-gray-400 dark:bg-gray-200 dark:border-gray-500 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-bold text-gray-900 dark:text-gray-100 truncate leading-tight">
              {result.player_white}
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 leading-tight">White</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-4 py-3">
          <span className="w-3.5 h-3.5 rounded-sm bg-gray-800 border border-gray-600 dark:bg-gray-900 dark:border-gray-600 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-bold text-gray-900 dark:text-gray-100 truncate leading-tight">
              {result.player_black}
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 leading-tight">Black</p>
          </div>
        </div>
      </div>

      {/* Classification table */}
      <div className="px-3 py-3 flex flex-col gap-1">
        {ROWS.map((cls) => {
          const meta = CLASSIFICATION_META[cls];
          const wCount = whiteCounts[cls] ?? 0;
          const bCount = blackCounts[cls] ?? 0;
          return (
            <div key={cls} className="grid grid-cols-[2rem_1fr_2rem] items-center gap-1 text-sm">
              {/* White count */}
              <span className={`text-right font-bold tabular-nums ${wCount > 0 ? meta.color : 'text-gray-300 dark:text-gray-700'}`}>
                {wCount}
              </span>
              {/* Label + dot */}
              <div className="flex items-center justify-center gap-1.5">
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${meta.dot}`} />
                <span className="text-xs font-medium text-gray-600 dark:text-gray-400">{meta.label}</span>
              </div>
              {/* Black count */}
              <span className={`text-left font-bold tabular-nums ${bCount > 0 ? meta.color : 'text-gray-300 dark:text-gray-700'}`}>
                {bCount}
              </span>
            </div>
          );
        })}
      </div>

      {/* ACPL + Accuracy */}
      <div className="grid grid-cols-2 border-t-2 border-gray-200 dark:border-gray-800">
        <div className="px-4 py-3 border-r-2 border-gray-200 dark:border-gray-800 flex flex-col gap-1">
          <StatRow label="Avg. CP loss" value={Math.round(result.acpl_white).toString()} />
          <AccuracyRow accuracy={whiteAccuracy} />
        </div>
        <div className="px-4 py-3 flex flex-col gap-1">
          <StatRow label="Avg. CP loss" value={Math.round(result.acpl_black).toString()} />
          <AccuracyRow accuracy={blackAccuracy} />
        </div>
      </div>

      {/* Start button */}
      <div className="p-4 border-t-2 border-gray-200 dark:border-gray-800">
        <button
          onClick={onStart}
          className="
            w-full py-3 rounded-xl font-bold text-base tracking-wide
            bg-primary-600 hover:bg-primary-500 active:bg-primary-700
            text-white
            flex items-center justify-center gap-2.5
            transition-all duration-150
            shadow-md shadow-primary-600/25
          "
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
            <path d="M6.3 2.84A1.5 1.5 0 0 0 4 4.11v11.78a1.5 1.5 0 0 0 2.3 1.27l9.344-5.891a1.5 1.5 0 0 0 0-2.538L6.3 2.841Z" />
          </svg>
          Start Analysis
        </button>
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{label}</span>
      <span className="text-sm font-bold text-gray-800 dark:text-gray-200 tabular-nums">{value}</span>
    </div>
  );
}

function AccuracyRow({ accuracy }: { accuracy: number }) {
  const pct = accuracy.toFixed(1);
  // Color based on accuracy tier
  const color =
    accuracy >= 85 ? 'text-emerald-600 dark:text-emerald-400' :
    accuracy >= 70 ? 'text-green-600 dark:text-green-400' :
    accuracy >= 55 ? 'text-yellow-600 dark:text-yellow-400' :
    accuracy >= 40 ? 'text-orange-600 dark:text-orange-400' :
                     'text-red-600 dark:text-red-500';

  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-xs text-gray-400 dark:text-gray-500">Accuracy</span>
      <span className={`text-sm font-bold tabular-nums ${color}`}>{pct}%</span>
    </div>
  );
}
