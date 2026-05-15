import { Chessboard } from 'react-chessboard';

interface Props {
  fen: string;
  squareStyles?: Record<string, React.CSSProperties>;
}

const LIGHT_SQUARE = '#f0d9b5';
const DARK_SQUARE  = '#b58863';

export default function ChessBoard({ fen, squareStyles = {} }: Props) {
  return (
    <div className="rounded-xl overflow-hidden shadow-lg ring-1 ring-black/10 dark:ring-0 aspect-square w-full">
      <Chessboard
        options={{
          position: fen,
          allowDragging: false,
          lightSquareStyle: { backgroundColor: LIGHT_SQUARE },
          darkSquareStyle:  { backgroundColor: DARK_SQUARE },
          squareStyles,
        }}
      />
    </div>
  );
}
