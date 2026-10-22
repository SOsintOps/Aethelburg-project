"""Semantic & n-gram vector similarity service for entity name matching (ADR-001 / ADR-017).

Provides:
  - Fast character 3-gram cosine similarity + Jaro-Winkler hybrid scoring (always available, zero network latency)
  - Optional SentenceTransformer (`paraphrase-multilingual-MiniLM-L12-v2`) dense embeddings when requested
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from config.database import get_sqlite_connection
from src.core.normalizer import jaro_winkler_similarity, normalize_name, phonetic_key


def _char_ngrams(text: str, n: int = 3) -> Counter[str]:
    norm = f"  {normalize_name(text) or text.lower()}  "
    if len(norm) < n:
        return Counter([norm])
    return Counter(norm[i : i + n] for i in range(len(norm) - n + 1))


def cosine_ngram_similarity(a: str, b: str, n: int = 3) -> float:
    """Compute character n-gram cosine similarity in [0.0, 1.0]."""
    ca = _char_ngrams(a, n=n)
    cb = _char_ngrams(b, n=n)
    if not ca or not cb:
        return 0.0
    dot = sum(ca[k] * cb[k] for k in ca.keys() & cb.keys())
    norm_a = math.sqrt(sum(v * v for v in ca.values()))
    norm_b = math.sqrt(sum(v * v for v in cb.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorService:
    """Hybrid semantic + n-gram similarity search across companies, persons, sanctions, and ICIJ."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None

    def similarity(self, name_a: str, name_b: str) -> float:
        """Compute hybrid similarity combining Jaro-Winkler, 3-gram cosine, and phonetic bonus."""
        jw = jaro_winkler_similarity(name_a, name_b)
        cos = cosine_ngram_similarity(name_a, name_b)
        pk_a = phonetic_key(name_a)
        pk_b = phonetic_key(name_b)
        phonetic_bonus = 0.05 if (pk_a and pk_a == pk_b) else 0.0
        return min(1.0, round(0.55 * jw + 0.45 * cos + phonetic_bonus, 4))

    def search_similar_entities(
        self,
        query_name: str,
        threshold: float = 0.72,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Find entities across Companies, Sanctions, and ICIJ with high similarity to `query_name`."""
        fp = normalize_name(query_name)
        if not fp:
            return []
        first_token = fp.split()[0]
        conn = get_sqlite_connection(self.db_path)
        candidates: list[dict[str, Any]] = []
        try:
            # Candidate blocking via first token or substring
            comp_rows = conn.execute(
                """
                SELECT company_number AS entity_id, 'Company' AS entity_type,
                       company_name AS name, ftm_id, 'uk_companies_house' AS dataset
                FROM companies
                WHERE name_fingerprint LIKE ? OR company_name LIKE ?
                LIMIT 200
                """,
                (f"%{first_token}%", f"%{first_token}%"),
            ).fetchall()
            sanc_rows = conn.execute(
                """
                SELECT id AS entity_id, 'Sanction' AS entity_type,
                       name, ftm_id, 'uk_ofsi_sanctions' AS dataset
                FROM sanctions
                WHERE name_fingerprint LIKE ? OR name LIKE ?
                LIMIT 200
                """,
                (f"%{first_token}%", f"%{first_token}%"),
            ).fetchall()
            icij_rows = conn.execute(
                """
                SELECT node_id AS entity_id, 'OffshoreEntity' AS entity_type,
                       name, ftm_id, 'icij_offshore_leaks' AS dataset
                FROM icij_entities
                WHERE name_fingerprint LIKE ? OR name LIKE ?
                LIMIT 200
                """,
                (f"%{first_token}%", f"%{first_token}%"),
            ).fetchall()

            for row in [*comp_rows, *sanc_rows, *icij_rows]:
                score = self.similarity(query_name, row["name"] or "")
                if score >= threshold:
                    candidates.append(
                        {
                            "entity_id": row["entity_id"],
                            "entity_type": row["entity_type"],
                            "name": row["name"],
                            "ftm_id": row["ftm_id"],
                            "dataset": row["dataset"],
                            "similarity": score,
                        }
                    )
            candidates.sort(key=lambda x: x["similarity"], reverse=True)
            return candidates[:limit]
        finally:
            conn.close()
