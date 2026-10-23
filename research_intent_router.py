"""ResearchIntentRouter — deterministic intent classification.

Classifies user queries into one of:
- PERSON_LOOKUP: uses identity pipeline
- EVENT_LOOKUP: uses event ontology + temporal gates
- AGGREGATE_QUERY: uses deterministic SQL/provenance-aware queries
- SOURCE_LOOKUP: searches archival resources, not persons
- CONVERSATIONAL_FOLLOWUP: bound to existing snapshot

The router is deterministic: no LLM calls, no probability.
It uses keyword matching, structural cues, and context state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class IntentResult:
    intent: str
    confidence: float
    extracted_entities: Dict[str, str] = field(default_factory=dict)
    reason: str = ""


class ResearchIntentRouter:
    """Deterministic intent router for research queries."""

    PERSON_KEYWORDS = [
        "chi era", "chi è", "soldato", "internato", "decorato", "caduto",
        "militare", "sottufficiale", "ufficiale", "maresciallo",
        "sergente", "caporale", "soldato semplice", "tenente", "capitano",
        "maggiore", "colonnello", "generale",
        "cognome", "nome", "paternità", "matricola", "grado",
        "reparto", "unità", "reggimento", "brigata", "divisione",
        "luogo di nascita", "data di nascita",
        "omonimo", "omonimi", "disambiguare",
    ]

    EVENT_KEYWORDS = [
        "battaglia", "offensiva", "ritirata", "avanzata",
        "caporetto", "isonzo", "carso", "piave", "grappa",
        "fronte", "settore", "teatro", "campagna",
        "operazione", "azione di guerra", "combattimento",
        "quando", "dove si svolse", "quante battaglie",
        "data inizio", "data fine", "durata",
    ]

    AGGREGATE_KEYWORDS = [
        "quanti", "totale", "numero di", "statistica",
        "mortalità", "deceduti", "percentuale",
        "distribuzione", "conteggio", "quante",
        "media", "somma", "elenco", "lista",
        "tutti i", "tutte le",
    ]

    SOURCE_KEYWORDS = [
        "archivio", "fondo", "sezione", "serie",
        "documento", "fonte", "diario di guerra", "ruolo matricolare",
        "foglio matricolare", "atto di concessione",
        "registro", "elenco nominativo",
        "dove si trova", "dove posso trovare",
        "come consultare", "accesso",
    ]

    FOLLOWUP_KEYWORDS = [
        "e poi", "e allora", "ma", "però", "invece",
        "approfondisci", "continua", "dimmi di più",
        "cioè", "quindi", "perché",
        "e questo", "e quello", "e lei", "e lui",
    ]

    # ── Public API ──

    def classify(
        self,
        query: str,
        has_snapshot: bool = False,
        conversation_history: Optional[List[dict]] = None,
    ) -> IntentResult:
        q_lower = query.lower().strip()

        # If we have a snapshot and the query is a short follow-up
        if has_snapshot and conversation_history:
            if self._is_followup(q_lower, conversation_history):
                return IntentResult(
                    intent="CONVERSATIONAL_FOLLOWUP",
                    confidence=0.9,
                    reason="short_followup_with_snapshot",
                )

        # Check aggregate first (before person, since "quanti soldati" is aggregate)
        agg_score = self._score_keywords(q_lower, self.AGGREGATE_KEYWORDS)
        if agg_score >= 2 or any(kw in q_lower for kw in ["quanti", "totale", "numero di"]):
            entities = self._extract_aggregate_entities(query)
            return IntentResult(
                intent="AGGREGATE_QUERY",
                confidence=0.85,
                extracted_entities=entities,
                reason="aggregate_keywords_matched",
            )

        # Check source lookup
        src_score = self._score_keywords(q_lower, self.SOURCE_KEYWORDS)
        if src_score >= 2:
            return IntentResult(
                intent="SOURCE_LOOKUP",
                confidence=0.8,
                extracted_entities={"query_text": query},
                reason="source_keywords_matched",
            )

        # Check event
        evt_score = self._score_keywords(q_lower, self.EVENT_KEYWORDS)
        if evt_score >= 2:
            entities = self._extract_event_entities(query)
            return IntentResult(
                intent="EVENT_LOOKUP",
                confidence=0.8,
                extracted_entities=entities,
                reason="event_keywords_matched",
            )

        # Check person
        person_score = self._score_keywords(q_lower, self.PERSON_KEYWORDS)
        if person_score >= 1:
            entities = self._extract_person_entities(query)
            return IntentResult(
                intent="PERSON_LOOKUP",
                confidence=0.75,
                extracted_entities=entities,
                reason="person_keywords_matched",
            )

        # Default: person lookup (most common case in this system)
        return IntentResult(
            intent="PERSON_LOOKUP",
            confidence=0.4,
            extracted_entities={"raw_query": query},
            reason="default_fallback",
        )

    # ── Internal helpers ──

    def _score_keywords(self, text: str, keywords: List[str]) -> int:
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        return score

    def _is_followup(self, q_lower: str, history: List[dict]) -> bool:
        if len(history) < 2:
            return False
        # Short query that starts with followup connector
        if len(q_lower) < 80:
            for kw in self.FOLLOWUP_KEYWORDS:
                if q_lower.startswith(kw):
                    return True
        # Very short query (likely pronoun reference)
        if len(q_lower) < 30 and not any(c.isdigit() for c in q_lower):
            return True
        return False

    def _extract_person_entities(self, query: str) -> Dict[str, str]:
        entities = {}
        # Try to extract a name pattern: UPPERCASE SURNAME + optional name
        name_match = re.search(r'\b([A-Z][A-Z\.\-]+(?:\s+[A-Z][a-z]+)?)\b', query)
        if name_match:
            entities["candidate_name"] = name_match.group(1)
        # Extract year
        year_match = re.search(r'\b(18[5-9]\d|19[0-4]\d)\b', query)
        if year_match:
            entities["birth_year"] = year_match.group(1)
        # Extract place after "di" or "a"
        place_match = re.search(r'(?:di|a|da)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', query)
        if place_match:
            entities["candidate_place"] = place_match.group(1)
        return entities

    def _extract_event_entities(self, query: str) -> Dict[str, str]:
        entities = {}
        # Extract event name (capitalized words)
        event_match = re.search(r'(Battaglia|Offensiva|Ritirata|Campagna)\s+(di\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', query)
        if event_match:
            entities["event_name"] = event_match.group(0)
        # Extract year
        year_match = re.search(r'\b(19[0-1]\d)\b', query)
        if year_match:
            entities["event_year"] = year_match.group(1)
        return entities

    def _extract_aggregate_entities(self, query: str) -> Dict[str, str]:
        entities = {"raw_query": query}
        # Extract conflict
        if "ww1" in query.lower() or "wwi" in query.lower() or "prima guerra" in query.lower() or "grande guerra" in query.lower():
            entities["conflict"] = "WWI"
        elif "ww2" in query.lower() or "wwii" in query.lower() or "seconda guerra" in query.lower():
            entities["conflict"] = "WWII"
        # Extract category
        if "decedut" in query.lower() or "mort" in query.lower():
            entities["category"] = "deaths"
        elif "decorat" in query.lower():
            entities["category"] = "decorations"
        elif "affond" in query.lower() or "nav" in query.lower():
            entities["category"] = "naval"
        elif "internat" in query.lower() or "prigion" in query.lower():
            entities["category"] = "internment"
        return entities
