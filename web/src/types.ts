export interface CardData {
  title: string;
  meta: Record<string, string>;
  body: string;
}

export interface ColumnData {
  name: string;
  cards: CardData[];
}

export interface BoardData {
  columns: ColumnData[];
}
