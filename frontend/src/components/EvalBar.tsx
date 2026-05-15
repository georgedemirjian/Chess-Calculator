interface Props {
  evalCp: number; // centipawns from White's perspective (positive = White better)
}

export default function EvalBar({ evalCp }: Props) {
  // tanh compresses the infinite eval range smoothly to a fraction.
  // Dividing by 600 means ±600 cp ≈ ±76% — mates reach the extremes.
  const whiteFrac = Math.max(0.05, Math.min(0.95, 0.5 + 0.5 * Math.tanh(evalCp / 600)));
  const blackFrac = 1 - whiteFrac;

  const absValue = Math.abs(evalCp);
  const isMate = absValue >= 10_000;
  const scoreText = isMate ? 'M' : (absValue / 100).toFixed(1);

  const whiteWinning = evalCp > 0;
  const blackWinning = evalCp < 0;

  return (
    <div className="flex flex-col h-full w-full rounded-xl overflow-hidden border-2 border-gray-300 dark:border-gray-700 shadow-sm dark:shadow-none">
      {/* Black section — top of bar */}
      <div
        className="flex flex-col items-center justify-start pt-1.5 transition-[height] duration-500 ease-out"
        style={{ height: `${blackFrac * 100}%`, backgroundColor: '#1a1a1a' }}
      >
        {blackWinning && (
          <span className="text-[10px] font-bold font-mono leading-none select-none text-gray-200">
            {scoreText}
          </span>
        )}
      </div>

      {/* White section — bottom of bar */}
      <div
        className="flex flex-col items-center justify-end pb-1.5 transition-[height] duration-500 ease-out"
        style={{ height: `${whiteFrac * 100}%`, backgroundColor: '#f0f0f0' }}
      >
        {whiteWinning && (
          <span className="text-[10px] font-bold font-mono leading-none select-none text-gray-900">
            {scoreText}
          </span>
        )}
      </div>
    </div>
  );
}
