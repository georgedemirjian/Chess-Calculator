import { useEffect, useRef } from 'react';
import type { MoveAnalysis } from '../lib/types';
import { CLASSIFICATION_META } from '../lib/classificationMeta';

interface Props {
  moves: MoveAnalysis[];
  selectedIndex: number | null;
  onSelectMove: (index: number) => void;
}

export default function MoveList({ moves, selectedIndex, onSelectMove }: Props) {
  const selectedRef = useRef<HTMLButtonElement>(null);

  // Scroll the selected move into view when it changes
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [selectedIndex]);

  // Group into full-move rows: [[white_ply, black_ply?], ...]
  const rows: Array<[MoveAnalysis, MoveAnalysis | undefined]> = [];
  for (let i = 0; i < moves.length; i += 2) {
    rows.push([moves[i], moves[i + 1]]);
  }

  return (
    <div className="flex flex-col min-h-0">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-500 uppercase tracking-wide px-1 mb-1 flex-shrink-0">
        Move List
      </p>
      <div className="overflow-y-auto scrollbar-thin flex-1 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
        <table className="w-full text-sm border-collapse">
          <tbody>
            {rows.map(([white, black], rowIdx) => (
              <tr
                key={rowIdx}
                className="border-b border-gray-100 dark:border-gray-800 last:border-0"
              >
                {/* Move number */}
                <td className="pl-3 pr-2 py-1.5 text-xs text-gray-400 dark:text-gray-600 select-none w-8 font-mono">
                  {white.move_number}.
                </td>

                {/* White move */}
                <td className="py-1 pr-1 w-1/2">
                  <MoveCell
                    move={white}
                    index={white.move_number * 2 - 2}
                    selected={selectedIndex === white.move_number * 2 - 2}
                    onSelect={onSelectMove}
                    ref={selectedIndex === white.move_number * 2 - 2 ? selectedRef : null}
                  />
                </td>

                {/* Black move */}
                <td className="py-1 pl-1 pr-2 w-1/2">
                  {black ? (
                    <MoveCell
                      move={black}
                      index={black.move_number * 2 - 1}
                      selected={selectedIndex === black.move_number * 2 - 1}
                      onSelect={onSelectMove}
                      ref={selectedIndex === black.move_number * 2 - 1 ? selectedRef : null}
                    />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface MoveCellProps {
  move: MoveAnalysis;
  index: number;
  selected: boolean;
  onSelect: (index: number) => void;
  ref: React.Ref<HTMLButtonElement> | null;
}

const MoveCell = function MoveCell({ move, index, selected, onSelect, ref }: MoveCellProps) {
  const cls = move.classification;
  const meta = cls ? CLASSIFICATION_META[cls] : null;

  return (
    <button
      ref={ref}
      onClick={() => onSelect(index)}
      className={`
        w-full text-left px-2 py-1 rounded-lg flex items-center justify-between gap-1 group
        transition-colors duration-100
        ${selected
          ? 'bg-primary-500 text-white'
          : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-800 dark:text-gray-200'}
      `}
    >
      {/* SAN */}
      <span className="font-medium font-mono text-sm truncate">{move.san}</span>

      <div className="flex items-center gap-1.5 flex-shrink-0">
        {/* Centipawn loss badge */}
        {move.cp_loss !== null && move.cp_loss > 0 && (
          <span
            className={`
              text-xs font-mono
              ${selected ? 'text-white/70' : 'text-gray-400 dark:text-gray-500'}
            `}
          >
            −{move.cp_loss}
          </span>
        )}

        {/* Classification dot */}
        {meta && (
          <span
            title={meta.label}
            className={`
              w-2 h-2 rounded-full flex-shrink-0
              ${selected ? 'bg-white/80' : meta.dot}
            `}
          />
        )}
      </div>
    </button>
  );
};
