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
  effective_cp_loss: number | null;
  wp_before: number | null;
  wp_after: number | null;
  wp_loss: number | null;
  // Mate distance after this move from White's POV: positive=white mates, negative=black mates, 0=checkmate occurred.
  mate_after: number | null;
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
  acpl_white: number;           // raw ACPL — for ML analytics
  acpl_black: number;
  acpl_white_effective: number; // capped ACPL — for human display
  acpl_black_effective: number;
  avg_wp_loss_white: number;    // primary accuracy signal [0.0–1.0]
  avg_wp_loss_black: number;
  total_moves: number;
}
