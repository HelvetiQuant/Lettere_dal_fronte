"""OpenAI Responses API Adapter — web_search tool + structured outputs.

Uses the OpenAI Responses API (not Chat Completions) with:
- web_search tool for discovery
- Structured Outputs via text.format JSON Schema
- url_citation annotations normalized to ProviderObservation
- response_id and usage tracking

The adapter produces ProviderObservation records, not free text.
Free text from the model is never used as proof.

Security: API key is read from environment. Never logged or exposed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from provider_observation import ProviderObservation, CitationAnnotation, SearchAction
from query_manifest import QueryManifest

log = logging.getLogger(__name__)


# ─── Structured output schema for report generation ─────────────────────────

REPORT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Risposta discorsiva in italiano basata esclusivamente sullo snapshot"
        },
        "supported_statement_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "claim_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["text", "claim_ids"]
            }
        },
        "uncertainties": {
            "type": "array",
            "items": {"type": "string"}
        },
        "rejected_hypotheses": {
            "type": "array",
            "items": {"type": "string"}
        },
        "suggested_action_ids": {
            "type": "array",
            "items": {"type": "string"}
        },
        "requires_new_research": {
            "type": "boolean",
            "description": "True se la domanda richiede dati non presenti nello snapshot"
        }
    },
    "required": ["answer", "supported_statement_groups", "requires_new_research"],
    "additionalProperties": False
}


@dataclass
class OpenAIAdapterResult:
    observations: List[ProviderObservation] = field(default_factory=list)
    report_json: Optional[dict] = None
    response_id: str = ""
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    cost_estimate: float = 0.0
    error: str = ""
    success: bool = False


class OpenAIResponsesAdapter:
    """Adapter for OpenAI Responses API with web_search and structured outputs.

    Capabilities:
    - DISCOVERY_WEB: uses web_search tool, returns ProviderObservation list
    - REPORT_GENERATION: uses structured output with JSON schema
    - CONVERSATION: uses structured output bound to snapshot
    - CLAIM_EXTRACTION: uses structured output for claim extraction
    """

    PROVIDER_NAME = "openai"
    CONTRACT_VERSION = "6.0"

    def __init__(self):
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        self._client = None
        self._available = bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    @property
    def available(self) -> bool:
        return self._available

    def discover(
        self,
        manifest: QueryManifest,
        max_results: int = 20,
    ) -> List[ProviderObservation]:
        """Execute web search discovery using the Responses API.

        Returns ProviderObservation records, not free text.
        """
        if not self._available:
            return []

        observations: List[ProviderObservation] = []
        query_text = manifest.target.get("display_name", "")
        if not query_text and manifest.query_variants:
            query_text = manifest.query_variants[0]

        if not query_text:
            return []

        try:
            client = self._get_client()

            # Use Responses API with web_search tool
            response = client.responses.create(
                model="gpt-4o-mini",
                tools=[{"type": "web_search"}],
                input=f"Search for: {query_text}. Find historical records, archival sources, and biographical information. Return URLs and titles.",
                store=False,
            )

            # Extract web_search_call actions
            for item in response.output:
                if item.type == "web_search_call":
                    observations.append(ProviderObservation(
                        run_id=manifest.manifest_id,
                        manifest_hash=manifest.manifest_hash,
                        provider=self.PROVIDER_NAME,
                        provider_result_id=item.id,
                        provider_query_id=query_text,
                        capability="DISCOVERY_WEB",
                        title=f"Web search: {query_text}",
                        search_actions=[SearchAction(
                            action_type="web_search_call",
                            query_used=query_text,
                            provider_action_id=item.id,
                        )],
                        content_state="NOT_OPENED",
                        classification="SEARCH_RESULT",
                    ))

            # Extract url_citation annotations from the output text
            if hasattr(response, "output_text") and response.output_text:
                # Parse annotations from the response
                for ann in getattr(response, "annotations", []):
                    if ann.type == "url_citation":
                        observations.append(ProviderObservation(
                            run_id=manifest.manifest_id,
                            manifest_hash=manifest.manifest_hash,
                            provider=self.PROVIDER_NAME,
                            provider_result_id=ann.url,
                            capability="DISCOVERY_WEB",
                            title=ann.title or "",
                            url_raw=ann.url,
                            url_canonical=ann.url,
                            citation_annotations=[CitationAnnotation(
                                url=ann.url,
                                title=ann.title or "",
                                citation_index=getattr(ann, "start_citation_index", 0),
                            )],
                            content_state="NOT_OPENED",
                            classification="MODEL_LEAD",
                            reason_codes=["url_citation_not_opened"],
                        ))

            # Also extract from output items
            for item in response.output:
                if hasattr(item, "content") and item.content:
                    for content in item.content:
                        if hasattr(content, "annotations"):
                            for ann in content.annotations:
                                if ann.type == "url_citation":
                                    obs = ProviderObservation(
                                        run_id=manifest.manifest_id,
                                        manifest_hash=manifest.manifest_hash,
                                        provider=self.PROVIDER_NAME,
                                        provider_result_id=ann.url,
                                        capability="DISCOVERY_WEB",
                                        title=ann.title or "",
                                        url_raw=ann.url,
                                        url_canonical=ann.url,
                                        citation_annotations=[CitationAnnotation(
                                            url=ann.url,
                                            title=ann.title or "",
                                        )],
                                        content_state="NOT_OPENED",
                                        classification="MODEL_LEAD",
                                        reason_codes=["url_citation_not_opened"],
                                    )
                                    # Dedup by URL
                                    if not any(o.url_canonical == obs.url_canonical for o in observations):
                                        observations.append(obs)

            return observations[:max_results]

        except Exception as e:
            log.warning("OpenAI discover failed: %s", str(e)[:100])
            return []

    def generate_report(
        self,
        snapshot_context: str,
        question: str,
        conversation_history: str = "",
    ) -> OpenAIAdapterResult:
        """Generate a structured report using the Responses API.

        Returns OpenAIAdapterResult with report_json.
        """
        if not self._available:
            return OpenAIAdapterResult(error="OpenAI not available", success=False)

        try:
            client = self._get_client()

            system_prompt = (
                "Sei l'Assistente della ricerca storico-archivistica. "
                "Rispondi ESCLUSIVAMENTE in base ai dati dello snapshot fornito. "
                "NON inventare dati, nomi, date, archivi, fondi o URL. "
                "NON negare l'esistenza di record verificati presenti nello snapshot. "
                "Se una domanda richiede nuove fonti non presenti nello snapshot, "
                "imposta requires_new_research=true e spiega cosa serve. "
                "Ogni affermazione fattuale deve essere supportata da un claim_id accettato. "
                "Non usare token interni come suggested_research_action, claim_id, source_id nel testo della risposta. "
                "Rispondi in italiano in modo discorsivo e naturale. "
                "Il campo 'answer' deve contenere SOLO testo conversazionale in italiano, NON JSON o markdown."
            )

            user_content = json.dumps({
                "snapshot_context": snapshot_context,
                "conversation_history": conversation_history,
                "question": question,
            }, ensure_ascii=False)

            response = client.responses.create(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "historical_report",
                        "schema": REPORT_JSON_SCHEMA,
                        "strict": True,
                    }
                },
                store=False,
            )

            # Parse structured output
            output_text = response.output_text if hasattr(response, "output_text") else ""
            if output_text:
                try:
                    report_json = json.loads(output_text)
                    return OpenAIAdapterResult(
                        report_json=report_json,
                        response_id=response.id,
                        model=response.model,
                        usage={
                            "input_tokens": getattr(response.usage, "input_tokens", 0),
                            "output_tokens": getattr(response.usage, "output_tokens", 0),
                        },
                        success=True,
                    )
                except json.JSONDecodeError:
                    return OpenAIAdapterResult(
                        error="INVALID_JSON_OUTPUT",
                        success=False,
                    )
            else:
                return OpenAIAdapterResult(
                    error="EMPTY_OUTPUT",
                    success=False,
                )

        except Exception as e:
            log.warning("OpenAI generate_report failed: %s", str(e)[:100])
            return OpenAIAdapterResult(error=str(e)[:100], success=False)

    def generate_conversation(
        self,
        snapshot_context: str,
        question: str,
        conversation_history: str = "",
    ) -> OpenAIAdapterResult:
        """Generate a conversational response (same as report but with history)."""
        return self.generate_report(snapshot_context, question, conversation_history)
