import asyncio

from fastapi import APIRouter, HTTPException, Request

from models.schemas import AnalyzeRequest, AnalyzeResponse, GameInfo, MoveAnalysis
from services import classifier, pgn_parser

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_game(request: AnalyzeRequest, http_request: Request) -> AnalyzeResponse:
    """
    Analyze a chess game from a PGN string.

    Pipeline:
        1. Parse PGN → game metadata + per-move data    ✅
        2. Evaluate each position with Stockfish         ✅
        3. Classify moves and compute ACPL               ✅
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

    white_cp_losses: list[int] = []
    black_cp_losses: list[int] = []
    moves: list[MoveAnalysis] = []

    for m in enriched:
        label = classifier.classify_move(
            cp_loss=m["cp_loss"],
            is_best_move=m["is_best_move"],
            is_forced=m["is_forced"],
        )

        if m["color"] == "white":
            white_cp_losses.append(m["cp_loss"])
        else:
            black_cp_losses.append(m["cp_loss"])

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
        acpl_white=classifier.compute_acpl(white_cp_losses),
        acpl_black=classifier.compute_acpl(black_cp_losses),
        total_moves=game["total_moves"],
    )
