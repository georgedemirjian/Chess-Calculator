import type { MoveClassification } from './types';

export interface ClassificationMeta {
  label: string;
  color: string;   // Tailwind text color class
  dot: string;     // Tailwind bg color class (for the dot in move list)
  squareRgba: string; // RGBA for the board square highlight
}

export const CLASSIFICATION_META: Record<MoveClassification, ClassificationMeta> = {
  best:       { label: 'Best',       color: 'text-emerald-600 dark:text-emerald-400', dot: 'bg-emerald-600 dark:bg-emerald-400', squareRgba: 'rgba(5, 150, 105, 0.45)'  },
  excellent:  { label: 'Excellent',  color: 'text-green-600 dark:text-green-400',     dot: 'bg-green-600 dark:bg-green-400',     squareRgba: 'rgba(22, 163, 74, 0.45)'   },
  good:       { label: 'Good',       color: 'text-lime-600 dark:text-lime-400',       dot: 'bg-lime-500 dark:bg-lime-400',       squareRgba: 'rgba(101, 163, 13, 0.45)'  },
  inaccuracy: { label: 'Inaccuracy', color: 'text-yellow-600 dark:text-yellow-400',   dot: 'bg-yellow-500 dark:bg-yellow-400',   squareRgba: 'rgba(202, 138, 4, 0.45)'   },
  mistake:    { label: 'Mistake',    color: 'text-orange-600 dark:text-orange-400',   dot: 'bg-orange-500 dark:bg-orange-400',   squareRgba: 'rgba(234, 88, 12, 0.45)'   },
  blunder:    { label: 'Blunder',    color: 'text-red-600 dark:text-red-500',         dot: 'bg-red-600 dark:bg-red-500',         squareRgba: 'rgba(220, 38, 38, 0.45)'   },
  forced:     { label: 'Forced',     color: 'text-gray-500 dark:text-gray-400',       dot: 'bg-gray-400 dark:bg-gray-500',       squareRgba: 'rgba(156, 163, 175, 0.3)'  },
};
