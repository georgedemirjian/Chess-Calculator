import asyncio

from fastapi import APIRouter, HTTPException, Request

from models.schemas import AnalyzeRequest, AnalyzeResponse, GameInfo, MoveAnalysis
from services import centipawn_utils, classifier, pgn_parser
from services.probability_utils import compute_avg_wp_loss

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_game(request: AnalyzeRequest, http_request: Request) -> AnalyzeResponse:
    """
    Analyze a chess game from a PGN string.

    Pipeline:
        1. Parse PGN → game metadata + per-move data
        2. Evaluate each position with Stockfish (eval, WP, effective CPL, mate distance)
        3. Classify moves by WP loss; compute raw ACPL, effective ACPL, and avg WP loss
    """
    try:
        game = pgn_parser.parse(request.pgn)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Stockfish calls are blocking — offload to a thread pool so the event loop
    # remains responsive while the engine processes each position.
    stockfish = http_request.app.state.stockfish
    loop = asyncio.get_event_loop()
    try:
        enriched = await loop.run_in_executor(
            None, stockfish.analyse_game, game["moves"]
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stockfish analysis failed: {exc}")

    # Separate accumulators per color.
    # raw_cp_losses  → raw ACPL (for ML feature extraction)
    # eff_cp_losses  → effective/capped ACPL (for human-facing display)
    # wp_losses      → average WP loss (primary accuracy signal)
    white_raw_cp:  list[int]   = []
    black_raw_cp:  list[int]   = []
    white_eff_cp:  list[int]   = []
    black_eff_cp:  list[int]   = []
    white_wp_loss: list[float] = []
    black_wp_loss: list[float] = []

    moves: list[MoveAnalysis] = []

    for m in enriched:
        label = classifier.classify_move(
            wp_loss=m["wp_loss"],
            is_best_move=m["is_best_move"],
            is_forced=m["is_forced"],
        )

        if m["color"] == "white":
            white_raw_cp.append(m["cp_loss"])
            white_eff_cp.append(m["effective_cp_loss"])
            white_wp_loss.append(m["wp_loss"])
        else:
            black_raw_cp.append(m["cp_loss"])
            black_eff_cp.append(m["effective_cp_loss"])
            black_wp_loss.append(m["wp_loss"])

        moves.append(MoveAnalysis(
            move_number=m["move_number"],
            color=m["color"],
            san=m["san"],
            uci=m["uci"],
            fen_before=m["fen_before"],
            fen_after=m["fen_after"],
            piece_moved=m["piece_moved"],
            is_capture=m["is_capture"],
            is_en_passant=m["is_en_passant"],
            is_castling=m["is_castling"],
            is_check=m["is_check"],
            is_checkmate=m["is_checkmate"],
            promotion=m["promotion"],
            eval_before=m["eval_before"],
            eval_after=m["eval_after"],
            cp_loss=m["cp_loss"],
            effective_cp_loss=m["effective_cp_loss"],
            wp_before=m["wp_before"],
            wp_after=m["wp_after"],
            wp_loss=m["wp_loss"],
            mate_after=m["mate_after"],
            classification=label,
        ))

    return AnalyzeResponse(
        player_white=game["white"],
        player_black=game["black"],
        game_info=GameInfo(
            event=game["event"],
            site=game["site"],
            date=game["date"],
            result=game["result"],
            eco=game["eco"],
            opening=game["opening"],
        ),
        moves=moves,
        acpl_white=centipawn_utils.compute_acpl(white_raw_cp),
        acpl_black=centipawn_utils.compute_acpl(black_raw_cp),
        acpl_white_effective=centipawn_utils.compute_effective_acpl(white_eff_cp),
        acpl_black_effective=centipawn_utils.compute_effective_acpl(black_eff_cp),
        avg_wp_loss_white=compute_avg_wp_loss(white_wp_loss),
        avg_wp_loss_black=compute_avg_wp_loss(black_wp_loss),
        total_moves=game["total_moves"],
    )
