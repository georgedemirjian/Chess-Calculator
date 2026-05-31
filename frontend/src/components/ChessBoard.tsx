import { Chessboard } from 'react-chessboard';

// Matches react-chessboard's Arrow type (its dist/types isn't exported).
export interface BoardArrow {
  startSquare: string;
  endSquare:   string;
  color:       string;
}

interface Props {
  fen: string;
  squareStyles?: Record<string, React.CSSProperties>;
  flipped?: boolean;
  arrows?: BoardArrow[];
}

const LIGHT_SQUARE = '#f0d9b5';
const DARK_SQUARE  = '#b58863';

export default function ChessBoard({
  fen,
  squareStyles = {},
  flipped = false,
  arrows = [],
}: Props) {
  return (
    <div className="rounded-xl overflow-hidden shadow-lg ring-1 ring-black/10 dark:ring-0 aspect-square w-full">
      <Chessboard
        options={{
          position: fen,
          allowDragging: false,
          boardOrientation: flipped ? 'black' : 'white',
          lightSquareStyle: { backgroundColor: LIGHT_SQUARE },
          darkSquareStyle:  { backgroundColor: DARK_SQUARE },
          squareStyles,
          arrows,
        }}
      />
    </div>
  );
}
