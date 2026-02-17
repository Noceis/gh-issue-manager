import type { BoardData, CardData } from "./types";

const BASE = "/api";

export async function fetchBoard(): Promise<BoardData> {
  const res = await fetch(`${BASE}/board`);
  if (!res.ok) throw new Error(`GET /board failed: ${res.status}`);
  return res.json();
}

export async function saveBoard(board: BoardData): Promise<BoardData> {
  const res = await fetch(`${BASE}/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(board),
  });
  if (!res.ok) throw new Error(`PUT /board failed: ${res.status}`);
  return fetchBoard();
}

export async function moveCard(
  fromColumn: string,
  fromIndex: number,
  toColumn: string,
  toIndex: number,
): Promise<BoardData> {
  const res = await fetch(`${BASE}/cards/move`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      from_column: fromColumn,
      from_index: fromIndex,
      to_column: toColumn,
      to_index: toIndex,
    }),
  });
  if (!res.ok) throw new Error(`PUT /cards/move failed: ${res.status}`);
  return res.json();
}

export async function addCard(
  column: string,
  title: string,
  meta: Record<string, string> = {},
  body: string = "",
): Promise<BoardData> {
  const res = await fetch(`${BASE}/cards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ column, title, meta, body }),
  });
  if (!res.ok) throw new Error(`POST /cards failed: ${res.status}`);
  return res.json();
}

export async function editCard(
  column: string,
  index: number,
  data: CardData,
): Promise<BoardData> {
  const res = await fetch(`${BASE}/cards/${encodeURIComponent(column)}/${index}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`PUT /cards/${column}/${index} failed: ${res.status}`);
  return res.json();
}

export async function deleteCard(
  column: string,
  index: number,
): Promise<BoardData> {
  const res = await fetch(`${BASE}/cards/${encodeURIComponent(column)}/${index}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`DELETE /cards/${column}/${index} failed: ${res.status}`);
  return res.json();
}
