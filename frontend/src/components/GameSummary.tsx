import type { AnalyzeResponse } from '../lib/types';

interface Props {
  result: AnalyzeResponse;
}

export default function GameSummary({ result }: Props) {
  const { game_info, player_white, player_black, acpl_white, acpl_black, total_moves } = result;

  return (
    <div className="rounded-xl border-2 border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden shadow-sm dark:shadow-none">
      {/* Players bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
        <PlayerChip name={player_white} color="white" acpl={acpl_white} />
        <span className="text-sm font-bold text-gray-700 dark:text-gray-300 tabular-nums">
          {game_info.result}
        </span>
        <PlayerChip name={player_black} color="black" acpl={acpl_black} />
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-2 text-xs text-gray-500 dark:text-gray-500 bg-gray-50 dark:bg-transparent">
        {game_info.opening && (
          <span className="font-medium text-gray-700 dark:text-gray-300">
            {game_info.eco ? `${game_info.eco} · ` : ''}{game_info.opening}
          </span>
        )}
        <span>{game_info.event}</span>
        <span>{game_info.date}</span>
        <span>{total_moves} plies</span>
      </div>
    </div>
  );
}

function PlayerChip({ name, color, acpl }: { name: string; color: 'white' | 'black'; acpl: number }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span
        className={`
          w-4 h-4 rounded-sm flex-shrink-0 border
          ${color === 'white'
            ? 'bg-gray-100 border-gray-300 dark:bg-gray-200 dark:border-gray-400'
            : 'bg-gray-800 border-gray-600 dark:bg-gray-900 dark:border-gray-700'}
        `}
      />
      <div className="min-w-0">
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate leading-tight">{name}</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 leading-tight">
          ACPL {Math.round(acpl)}
        </p>
      </div>
    </div>
  );
}
