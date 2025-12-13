import csv
import os
from functools import lru_cache
from typing import Dict, List, Optional
from django.conf import settings


def _resolve_id_key(fieldnames: List[str]) -> str:
    # Prefer configured ID column; if missing, try common names, else fall back to first column
    preferred = settings.FIFA20_ID_COLUMN
    if preferred in fieldnames:
        return preferred
    for candidate in ("id", "ID", "sofifa_id", "card_id"):
        if candidate in fieldnames:
            return candidate
    return fieldnames[0]


@lru_cache(maxsize=1)
def load_cards() -> List[Dict[str, str]]:
    path = settings.FIFA20_CSV_PATH
    if not os.path.exists(path):
        return []
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows: List[Dict[str, str]] = []
        for row in reader:
            # Normalize keys to strings and values to strings
            normalized = {str(k): ("" if v is None else str(v)) for k, v in row.items()}
            rows.append(normalized)
        return rows


def get_id_column(cards: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    if cards is None:
        cards = load_cards()
    if not cards:
        return None
    return _resolve_id_key(list(cards[0].keys()))


def get_card_by_id(item_id: str) -> Optional[Dict[str, str]]:
    cards = load_cards()
    if not cards:
        return None
    id_col = get_id_column(cards)
    if id_col is None:
        return None
    item_id = str(item_id)
    for row in cards:
        if str(row.get(id_col, "")) == item_id:
            return row
    return None
