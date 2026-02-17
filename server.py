"""
server — FastAPI backend for the kanban board web UI.

Serves a REST API backed by board.kanban.md and the built Vite frontend.
Dependencies (fastapi, uvicorn) are imported lazily so the rest of the CLI
works fine without them.
"""

import os
import threading
import time
import webbrowser

from .kanban import Board, Card, parse_board, write_board, KANBAN_PATH

WEB_DIST = os.path.join(os.path.dirname(__file__), "web", "dist")


def create_app():
    """Build the FastAPI app.  Imported lazily so fastapi stays optional."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from pydantic import BaseModel

    app = FastAPI(title="Kanban Board")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Pydantic models ──────────────────────────────────────────────────

    class CardModel(BaseModel):
        title: str
        meta: dict = {}
        body: str = ""

    class ColumnModel(BaseModel):
        name: str
        cards: list[CardModel]

    class BoardModel(BaseModel):
        columns: list[ColumnModel]

    class MovePayload(BaseModel):
        from_column: str
        from_index: int
        to_column: str
        to_index: int

    class AddPayload(BaseModel):
        column: str
        title: str
        meta: dict = {}
        body: str = ""

    class EditPayload(BaseModel):
        title: str
        meta: dict = {}
        body: str = ""

    class DeletePayload(BaseModel):
        column: str
        index: int

    # ── Helpers ───────────────────────────────────────────────────────────

    def _board_to_json(board: Board) -> dict:
        return {
            "columns": [
                {
                    "name": name,
                    "cards": [
                        {"title": c.title, "meta": c.meta, "body": c.body}
                        for c in cards
                    ],
                }
                for name, cards in board.columns
            ]
        }

    def _col_or_404(board, name):
        col = board.get_column(name)
        if col is None:
            raise HTTPException(404, f"Column '{name}' not found")
        return col

    # ── Routes ────────────────────────────────────────────────────────────

    @app.get("/api/board")
    def get_board():
        return _board_to_json(parse_board())

    @app.put("/api/board")
    def put_board(data: BoardModel):
        """Full-board update (reorder after drag-and-drop)."""
        columns = []
        for col in data.columns:
            cards = [Card(c.title, dict(c.meta), c.body) for c in col.cards]
            columns.append((col.name, cards))
        write_board(Board(columns))
        return {"ok": True}

    @app.post("/api/cards")
    def add_card(payload: AddPayload):
        board = parse_board()
        col = _col_or_404(board, payload.column)
        col.append(Card(payload.title, dict(payload.meta), payload.body))
        write_board(board)
        return _board_to_json(board)

    @app.put("/api/cards/move")
    def move_card(payload: MovePayload):
        board = parse_board()
        src = _col_or_404(board, payload.from_column)
        dst = _col_or_404(board, payload.to_column)
        if payload.from_index < 0 or payload.from_index >= len(src):
            raise HTTPException(400, "from_index out of range")
        card = src.pop(payload.from_index)
        dst.insert(min(payload.to_index, len(dst)), card)
        write_board(board)
        return _board_to_json(board)

    @app.put("/api/cards/{column}/{index}")
    def edit_card(column: str, index: int, payload: EditPayload):
        board = parse_board()
        col = _col_or_404(board, column)
        if index < 0 or index >= len(col):
            raise HTTPException(400, "index out of range")
        card = col[index]
        card.title = payload.title
        card.meta = dict(payload.meta)
        card.body = payload.body
        write_board(board)
        return _board_to_json(board)

    @app.delete("/api/cards/{column}/{index}")
    def delete_card(column: str, index: int):
        board = parse_board()
        col = _col_or_404(board, column)
        if index < 0 or index >= len(col):
            raise HTTPException(400, "index out of range")
        col.pop(index)
        write_board(board)
        return _board_to_json(board)

    # ── Serve built frontend ─────────────────────────────────────────────

    if os.path.isdir(WEB_DIST):
        from fastapi.staticfiles import StaticFiles
        # Assets first, then SPA fallback
        if os.path.isdir(os.path.join(WEB_DIST, "assets")):
            app.mount(
                "/assets",
                StaticFiles(directory=os.path.join(WEB_DIST, "assets")),
                name="assets",
            )

        @app.get("/{path:path}")
        def spa_fallback(path: str = ""):
            fp = os.path.join(WEB_DIST, path)
            if os.path.isfile(fp):
                return FileResponse(fp)
            return FileResponse(os.path.join(WEB_DIST, "index.html"))

    return app


# ═════════════════════════════════════════════════════════════════════════════
# LAUNCHER
# ═════════════════════════════════════════════════════════════════════════════

def start(port: int = 3333, open_browser: bool = True):
    """Start the kanban web server."""
    import uvicorn

    app = create_app()

    if open_browser:
        def _open():
            time.sleep(0.8)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  📋 Kanban board → http://localhost:{port}")
    print(f"  Press Ctrl+C to stop\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
