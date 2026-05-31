/**
 * Performance Estimate section — single-game Elo prediction from the
 * trained regression model on the backend.
 *
 * Renders null if both estimates are missing, so missing-model and
 * missing-data cases hide the section gracefully instead of showing "N/A".
 */

interface Props {
  whiteElo: number | null;
  blackElo: number | null;
}

// Typical single-game uncertainty (model test MAE rounded to a friendly
// number). Surfaced in copy so users don't read the estimate as precise.
const TYPICAL_UNCERTAINTY = 300;

export default function EloEstimate({ whiteElo, blackElo }: Props) {
  if (whiteElo === null && blackElo === null) return null;

  let stronger: 'white' | 'black' | null = null;
  if (whiteElo !== null && blackElo !== null) {
    if (whiteElo > blackElo)      stronger = 'white';
    else if (whiteElo < blackElo) stronger = 'black';
  }

  return (
    <section
      className="px-4 py-3 border-t-2 border-gray-200 dark:border-gray-800"
      aria-label="Elo performance estimate"
    >
      {/* Header */}
      <header className="flex items-center justify-between mb-2.5">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Performance Estimate
        </h3>
        <span
          className="text-gray-400 dark:text-gray-600 cursor-help"
          title={
            `Predicted Elo from this game's moves alone. ` +
            `Single-game estimates typically vary by ±${TYPICAL_UNCERTAINTY} Elo, ` +
            `and reflect performance in this game — not a player's true rating.`
          }
          aria-label="About this estimate"
        >
          <InfoIcon />
        </span>
      </header>

      {/* Two estimate cards */}
      <div className="grid grid-cols-2 gap-2">
        <EstimateCard color="white" elo={whiteElo} highlighted={stronger === 'white'} />
        <EstimateCard color="black" elo={blackElo} highlighted={stronger === 'black'} />
      </div>

      {/* Caveat */}
      <p className="mt-2.5 text-[10.5px] leading-snug text-center text-gray-400 dark:text-gray-500">
        Reflects performance in this game · not a true skill rating
      </p>
    </section>
  );
}

/* ── EstimateCard ─────────────────────────────────────────────────────── */

function EstimateCard({
  color,
  elo,
  highlighted,
}: {
  color: 'white' | 'black';
  elo: number | null;
  highlighted: boolean;
}) {
  const baseLayout = 'relative px-3 py-2.5 rounded-lg border transition-colors duration-150';

  const surface = highlighted
    ? 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-700/40'
    : 'bg-gray-50 dark:bg-gray-800/40 border-transparent';

  return (
    <div className={`${baseLayout} ${surface}`}>
      {/* Top row: color swatch + label + (optional) up indicator */}
      <div className="flex items-center gap-1.5 mb-1">
        <span
          className={`w-2.5 h-2.5 rounded-sm flex-shrink-0 border ${
            color === 'white'
              ? 'bg-gray-100 border-gray-400 dark:bg-gray-200 dark:border-gray-500'
              : 'bg-gray-800 border-gray-600 dark:bg-gray-900 dark:border-gray-600'
          }`}
        />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {color}
        </span>
        {highlighted && (
          <span
            className="ml-auto text-indigo-600 dark:text-indigo-400"
            aria-label="Stronger performance"
            title="Stronger performance in this game"
          >
            <ChevronUpIcon />
          </span>
        )}
      </div>

      {/* Estimate value */}
      {elo === null ? (
        <p className="text-2xl font-bold tabular-nums text-gray-300 dark:text-gray-600">
          —
        </p>
      ) : (
        <p
          className={`text-2xl font-bold tabular-nums ${
            highlighted
              ? 'text-indigo-700 dark:text-indigo-300'
              : 'text-gray-800 dark:text-gray-200'
          }`}
        >
          {elo}
          <span className="ml-1 text-[10px] font-normal tracking-normal text-gray-400 dark:text-gray-500">
            ±{TYPICAL_UNCERTAINTY}
          </span>
        </p>
      )}

      <p className="text-[10px] uppercase tracking-wider text-gray-400 dark:text-gray-500">
        Approx. Elo
      </p>
    </div>
  );
}

/* ── Icons ────────────────────────────────────────────────────────────── */

function InfoIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="w-3.5 h-3.5"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M18 10A8 8 0 1 1 2 10a8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ChevronUpIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="w-3.5 h-3.5"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M14.77 12.79a.75.75 0 0 1-1.06-.02L10 8.832 6.29 12.77a.75.75 0 1 1-1.08-1.04l4.25-4.5a.75.75 0 0 1 1.08 0l4.25 4.5a.75.75 0 0 1-.02 1.06Z"
        clipRule="evenodd"
      />
    </svg>
  );
}
