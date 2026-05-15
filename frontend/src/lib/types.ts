export type MoveClassification =
  | 'best'
  | 'excellent'
  | 'good'
  | 'inaccuracy'
  | 'mistake'
  | 'blunder'
  | 'forced';

export interface MoveAnalysis {
  move_number: number;
  color: 'white' | 'black';
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  piece_moved: string;
  is_capture: boolean;
  is_en_passant: boolean;
  is_castling: boolean;
  is_check: boolean;
  is_checkmate: boolean;
  promotion: string | null;
  eval_before: number | null;
  eval_after: number | null;
  cp_loss: number | null;
  classification: MoveClassification | null;
}

export interface GameInfo {
  event: string;
  site: string;
  date: string;
  result: string;
  eco: string | null;
  opening: string | null;
}

export interface AnalyzeResponse {
  player_white: string;
  player_black: string;
  game_info: GameInfo;
  moves: MoveAnalysis[];
  acpl_white: number;
  acpl_black: number;
  total_moves: number;
}
