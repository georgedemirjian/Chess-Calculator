import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import type { MoveAnalysis } from '../lib/types';

interface Props {
  moves: MoveAnalysis[];
  selectedIndex: number | null;
  onSelectMove: (index: number) => void;
  flipped?: boolean;
}

const CAP = 1000; // display cap in centipawns

function capEval(val: number | null): number {
  if (val === null) return 0;
  return Math.max(-CAP, Math.min(CAP, val));
}

function formatEval(cp: number): string {
  if (Math.abs(cp) >= CAP) return cp > 0 ? '+M' : '-M';
  const pawns = cp / 100;
  return pawns >= 0 ? `+${pawns.toFixed(1)}` : pawns.toFixed(1);
}

interface DataPoint {
  ply: number;
  label: string;
  eval: number;
  rawEval: number;
}

export default function EvalGraph({ moves, selectedIndex, onSelectMove, flipped = false }: Props) {
  const sign = flipped ? -1 : 1;
  const data: DataPoint[] = moves.map((m, i) => ({
    ply: i,
    label: `${m.move_number}${m.color === 'black' ? '…' : '.'} ${m.san}`,
    eval: sign * capEval(m.eval_after),
    rawEval: sign * (m.eval_after ?? 0),
  }));

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleClick = (state: any) => {
    const index = state?.activeTooltipIndex;
    if (typeof index === 'number') {
      onSelectMove(index);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-500 uppercase tracking-wide px-1">
        Evaluation · {flipped ? "Black's" : "White's"} perspective
      </p>
      <div className="h-36 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
            onClick={handleClick}
            style={{ cursor: 'pointer' }}
          >
            <defs>
              <linearGradient id="evalGradientWhite" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="evalGradientBlack" x1="0" y1="1" x2="0" y2="0">
                <stop offset="5%"  stopColor="#374151" stopOpacity={0.5} />
                <stop offset="95%" stopColor="#374151" stopOpacity={0.05} />
              </linearGradient>
            </defs>

            <XAxis dataKey="ply" hide />
            <YAxis domain={[-CAP, CAP]} hide />

            <ReferenceLine y={0} stroke="#6b7280" strokeOpacity={0.4} strokeWidth={1} />

            {/* Highlight selected ply */}
            {selectedIndex !== null && (
              <ReferenceLine
                x={selectedIndex}
                stroke="#6366f1"
                strokeWidth={1.5}
                strokeOpacity={0.8}
              />
            )}

            <Tooltip
              content={<CustomTooltip />}
              cursor={{ stroke: '#6366f1', strokeWidth: 1, strokeOpacity: 0.5 }}
            />

            {/* Positive half — whose advantage this represents swaps when flipped */}
            <Area
              type="monotone"
              dataKey="eval"
              stroke={flipped ? '#374151' : '#6366f1'}
              strokeWidth={1.5}
              fill={flipped ? 'url(#evalGradientBlack)' : 'url(#evalGradientWhite)'}
              dot={false}
              activeDot={{ r: 3, fill: flipped ? '#374151' : '#6366f1' }}
              baseValue={0}
              data={data.map((d) => ({ ...d, eval: Math.max(0, d.eval) }))}
            />

            {/* Negative half */}
            <Area
              type="monotone"
              dataKey="eval"
              stroke={flipped ? '#6366f1' : '#374151'}
              strokeWidth={1.5}
              fill={flipped ? 'url(#evalGradientWhite)' : 'url(#evalGradientBlack)'}
              dot={false}
              activeDot={{ r: 3, fill: flipped ? '#6366f1' : '#374151' }}
              baseValue={0}
              data={data.map((d) => ({ ...d, eval: Math.min(0, d.eval) }))}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function CustomTooltip({ active, payload }: {
  active?: boolean;
  payload?: { payload: DataPoint }[];
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 shadow-lg text-xs">
      <p className="font-medium text-gray-700 dark:text-gray-300 mb-0.5">{d.label}</p>
      <p className="font-mono text-primary-500">{formatEval(d.rawEval)}</p>
    </div>
  );
}
