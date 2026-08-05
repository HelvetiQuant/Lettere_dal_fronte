"""AggregateQueryResolver — deterministic SQL/provenance-aware queries.

For AGGREGATE_QUERY intent, the system does NOT use the LLM to compute totals.
Instead, it runs deterministic SQL against local/canonical databases and
records the query, table, and version in the result.

The LLM may explain the result but does not calculate it.
If no data is available, returns NO_AGGREGATE_DATA with explanation.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class AggregateResult:
    query_description: str
    result: Dict[str, Any] = field(default_factory=dict)
    query_sql: str = ""
    query_hash: str = ""
    table_name: str = ""
    table_version: str = ""
    row_count: int = 0
    has_data: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "query_description": self.query_description,
            "result": self.result,
            "query_hash": self.query_hash,
            "table_name": self.table_name,
            "table_version": self.table_version,
            "row_count": self.row_count,
            "has_data": self.has_data,
            "error": self.error,
        }


class AggregateQueryResolver:
    """Deterministic aggregate query resolver.

    Maps aggregate query descriptions to pre-defined SQL queries.
    No LLM computation. Results include provenance metadata.
    """

    DB_PATH = Path(__file__).parent / "imi_internati.db"

    # Pre-defined query catalog
    QUERY_CATALOG = {
        "IMI deceduti in Germania": {
            "sql": """
                SELECT
                    luogo_internamento AS campo,
                    COUNT(*) AS count
                FROM internati
                WHERE sorte = 'deceduto'
                  AND luogo_internamento IS NOT NULL
                  AND luogo_internamento != ''
                GROUP BY luogo_internamento
                ORDER BY count DESC
            """,
            "table": "internati",
            "description": "Conteggio IMI deceduti per campo di internamento",
        },
        "Decorati al Valor Militare WWI": {
            "sql": """
                SELECT
                    tipo_decorazione,
                    COUNT(*) AS count
                FROM decorati_nastroazzurro
                WHERE anno_decorazione IS NOT NULL
                  AND anno_decorazione != ''
                GROUP BY tipo_decorazione
                ORDER BY count DESC
            """,
            "table": "decorati_nastroazzurro",
            "description": "Conteggio decorazioni per tipo",
        },
        "Caduti per affondamento di nave": {
            "sql": """
                SELECT
                    causa_morte,
                    COUNT(*) AS count
                FROM caduti_albooro
                WHERE causa_morte LIKE '%affondamento%'
                   OR causa_morte LIKE '%nave%'
                GROUP BY causa_morte
                ORDER BY count DESC
            """,
            "table": "caduti_albooro",
            "description": "Conteggio caduti per affondamento di nave",
        },
    }

    def resolve(self, description: str, filters: Dict[str, Any] = None) -> AggregateResult:
        """Resolve an aggregate query deterministically.

        Args:
            description: The aggregate query description
            filters: Optional filters (conflict, category, etc.)

        Returns:
            AggregateResult with data and provenance
        """
        # Find matching query in catalog
        query_def = None
        for key, qdef in self.QUERY_CATALOG.items():
            if key.lower() in description.lower() or description.lower() in key.lower():
                query_def = qdef
                break

        if query_def is None:
            return AggregateResult(
                query_description=description,
                error="NO_AGGREGATE_DATA",
                has_data=False,
            )

        sql = query_def["sql"]
        table = query_def["table"]
        query_hash = hashlib.sha256(sql.encode()).hexdigest()[:16]

        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
            conn.close()

            result_data = {}
            total = 0
            for row in rows:
                row_dict = dict(row)
                campo = row_dict.get("campo") or row_dict.get("tipo_decorazione") or row_dict.get("causa_morte") or "unknown"
                count = row_dict.get("count", 0)
                result_data[str(campo)] = count
                total += count

            result_data["total"] = total

            return AggregateResult(
                query_description=query_def["description"],
                result=result_data,
                query_sql=sql,
                query_hash=query_hash,
                table_name=table,
                table_version="local_sqlite",
                row_count=len(rows),
                has_data=len(rows) > 0,
            )

        except Exception as e:
            return AggregateResult(
                query_description=description,
                error=f"QUERY_ERROR: {str(e)[:100]}",
                has_data=False,
            )

    def resolve_by_category(
        self,
        category: str,
        conflict: str = "UNKNOWN",
        filters: Dict[str, Any] = None,
    ) -> AggregateResult:
        """Resolve by extracted category from intent router."""
        category_map = {
            "deaths": "IMI deceduti in Germania",
            "decorations": "Decorati al Valor Militare WWI",
            "naval": "Caduti per affondamento di nave",
            "internment": "IMI deceduti in Germania",
        }
        desc = category_map.get(category, category)
        return self.resolve(desc, filters)
