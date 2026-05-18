interface Props {
  pgn: string;
  loading: boolean;
  onChange: (pgn: string) => void;
  onAnalyze: () => void;
}

const EXAMPLE_PGN = `[Event "Casual game"]
[White "Magnus"]
[Black "Hikaru"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6
8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 1-0`;

import { playButtonClick } from '../lib/sounds';

export default function PgnInput({ pgn, loading, onChange, onAnalyze }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <label className="text-sm font-medium text-gray-600 dark:text-gray-400 uppercase tracking-wide">
        Paste PGN
      </label>
      <textarea
        value={pgn}
        onChange={(e) => onChange(e.target.value)}
        placeholder={EXAMPLE_PGN}
        rows={8}
        spellCheck={false}
        className="
          w-full resize-none rounded-xl border border-gray-200 dark:border-gray-700
          bg-white dark:bg-gray-900
          text-gray-900 dark:text-gray-100
          placeholder-gray-300 dark:placeholder-gray-700
          text-sm font-mono leading-relaxed
          px-4 py-3
          focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
          transition-colors duration-150
          scrollbar-thin
        "
      />
      <button
        onClick={() => { playButtonClick(); onAnalyze(); }}
        disabled={loading || !pgn.trim()}
        className="
          w-full py-3 px-6 rounded-xl font-semibold text-sm tracking-wide
          bg-primary-600 hover:bg-primary-500 active:bg-primary-600
          disabled:opacity-90 disabled:cursor-not-allowed
          text-white
          transition-all duration-150
          flex items-center justify-center gap-2
          shadow-md shadow-primary-600/20
        "
      >
        {loading ? (
          <>
            <Spinner />
            Analyzing…
          </>
        ) : (
          'Analyze Game'
        )}
      </button>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
