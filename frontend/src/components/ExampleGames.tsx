import { useState } from 'react';
import { loadExampleGame } from '../api/examples';
import { playButtonClick } from '../lib/sounds';
import type { AnalyzeResponse } from '../lib/types';

// Curated demo games — slug must match a file in /public/examples/<slug>.json.
// To add more: drop a .pgn into backend/scripts/example_pgns/, rerun
// `python scripts/generate_examples.py`, then add an entry here.
interface Example {
  slug:     string;
  title:    string;
  subtitle: string;
}

const EXAMPLES: Example[] = [
  {
    slug:     'kasparov-topalov-1999',
    title:    "Kasparov's Immortal",
    subtitle: 'Kasparov vs Topalov · 1999',
  },
  {
    slug:     'botvinnik-capablanca-1938',
    title:    "Botvinnik's Masterpiece",
    subtitle: 'Botvinnik vs Capablanca · 1938',
  },
  {
    slug:     'spassky-fischer-1972',
    title:    'Match of the Century',
    subtitle: 'Spassky vs Fischer · 1972',
  },
  {
    slug:     'aronian-carlsen-2017',
    title:    "Aronian's Rxa3",
    subtitle: 'Aronian vs Carlsen · 2017',
  },
  {
    slug:     'gelfand-nakamura-2010',
    title:    "Nakamura's Brilliancy",
    subtitle: 'Gelfand vs Nakamura · 2010',
  },
];

interface Props {
  disabled: boolean;
  onLoad:  (result: AnalyzeResponse) => void;
  onError: (message: string) => void;
}

export default function ExampleGames({ disabled, onLoad, onError }: Props) {
  // Tracks which chip is mid-fetch so we can show a subtle disabled state
  // without disabling the whole row (visitors expect instant feedback here).
  const [loadingSlug, setLoadingSlug] = useState<string | null>(null);

  const load = async (slug: string) => {
    playButtonClick();
    setLoadingSlug(slug);
    try {
      const data = await loadExampleGame(slug);
      onLoad(data);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Could not load example.');
    } finally {
      setLoadingSlug(null);
    }
  };

  const pickRandom = () => {
    const choice = EXAMPLES[Math.floor(Math.random() * EXAMPLES.length)];
    load(choice.slug);
  };

  const isDisabled = disabled || loadingSlug !== null;

  return (
    <div className="mt-6">
      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-px bg-gray-200 dark:bg-gray-800" />
        <span className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
          No PGN handy? Try a famous game
        </span>
        <div className="flex-1 h-px bg-gray-200 dark:bg-gray-800" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {EXAMPLES.map((g) => (
          <Chip
            key={g.slug}
            title={g.title}
            subtitle={g.subtitle}
            loading={loadingSlug === g.slug}
            disabled={isDisabled}
            onClick={() => load(g.slug)}
          />
        ))}
        <Chip
          title="Surprise me"
          subtitle="Pick one for me"
          loading={loadingSlug === '__random__'}
          disabled={isDisabled}
          onClick={pickRandom}
          accent
        />
      </div>
    </div>
  );
}

function Chip({
  title,
  subtitle,
  loading,
  disabled,
  onClick,
  accent = false,
}: {
  title:    string;
  subtitle: string;
  loading:  boolean;
  disabled: boolean;
  onClick:  () => void;
  accent?:  boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        text-left px-4 py-2.5 rounded-lg border-2
        transition-colors duration-150
        disabled:opacity-60 disabled:cursor-not-allowed
        ${accent
          ? 'border-primary-500/50 bg-primary-500/5 hover:border-primary-500 hover:bg-primary-500/15'
          : 'border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-primary-500 dark:hover:border-primary-500'}
      `}
    >
      <div className={`text-sm font-semibold ${
        accent
          ? 'text-primary-600 dark:text-primary-400'
          : 'text-gray-900 dark:text-gray-100'
      }`}>
        {loading ? 'Loading…' : title}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
        {subtitle}
      </div>
    </button>
  );
}
