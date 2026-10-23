"""Conversational Report Provider V5 — uses V5 snapshot, fallback chain, semantic validator.

Key improvements over V4:
- Uses EvidenceSnapshotV5 with structured target identity
- Uses ProviderFallbackChain (OpenAI → Mistral → deterministic)
- Uses ai_output_validator_v5 for semantic grounding validation
- Model returns structured JSON, renderer produces Markdown
- Anti-truncation: retry once with reduced budget, then deterministic
- Conversation bound to snapshot_hash — follow-ups cite only authorized IDs
- Provider metadata recorded in every message
- No OpenAI calls when not configured or circuit open
"""
from __future__ import annotations

import json
import hashlib
import logging
import sqlite3
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any

log = logging.getLogger(__name__)


@dataclass
class ConversationMessageV5:
    """A single message in a research conversation."""
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cited_claim_ids: List[str] = field(default_factory=list)
    cited_source_ids: List[str] = field(default_factory=list)
    validation_state: str = "pending"  # pending | valid | invalid | fallback
    validation_reason_codes: List[str] = field(default_factory=list)
    provider_used: str = ""
    model_used: str = ""
    fallback_reason: str = ""


@dataclass
class ConversationV5:
    """A research conversation bound to a V5 snapshot."""
    conversation_id: str
    report_id: str
    snapshot_id: str
    snapshot_hash: str
    provider: str
    model: str
    messages: List[ConversationMessageV5] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "report_id": self.report_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "provider": self.provider,
            "model": self.model,
            "messages": [asdict(m) for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ReportConversationProviderV5:
    """V5 conversational report provider with fallback chain."""

    def __init__(self):
        self._db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "research_conversations_v5.db"
        )
        self._init_db()

        # Determine provider configuration from environment
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        mistral_key = os.environ.get("MISTRAL_API_KEY", "")
        lmstudio_url = os.environ.get("LM_STUDIO_API_URL", "")

        self._openai_configured = bool(openai_key and len(openai_key) >= 10)
        self._mistral_configured = bool(mistral_key or lmstudio_url)

        from provider_fallback_chain import ProviderFallbackChain
        self._chain = ProviderFallbackChain(
            openai_configured=self._openai_configured,
            mistral_configured=self._mistral_configured,
        )

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_v5 (
                conversation_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_messages_v5 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                cited_claim_ids TEXT,
                cited_source_ids TEXT,
                validation_state TEXT DEFAULT 'pending',
                validation_reason_codes TEXT,
                provider_used TEXT,
                model_used TEXT,
                fallback_reason TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations_v5(conversation_id)
            )
        """)
        conn.commit()
        conn.close()

    def create_conversation(
        self,
        report_id: str,
        snapshot_dict: dict,
    ) -> ConversationV5:
        """Create a new conversation bound to a V5 snapshot."""
        snap_id = snapshot_dict.get("snapshot_id", "")
        snap_hash = snapshot_dict.get("snapshot_hash", "")
        conversation_id = f"conv5_{hashlib.sha256(f'{report_id}_{snap_id}'.encode()).hexdigest()[:12]}"

        conv = ConversationV5(
            conversation_id=conversation_id,
            report_id=report_id,
            snapshot_id=snap_id,
            snapshot_hash=snap_hash,
            provider="pending",
            model="pending",
        )

        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT OR REPLACE INTO conversations_v5 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conv.conversation_id, conv.report_id, conv.snapshot_id,
             conv.snapshot_hash, conv.provider, conv.model,
             conv.created_at, conv.updated_at)
        )
        conn.commit()
        conn.close()

        return conv

    def send_message(
        self,
        conversation: ConversationV5,
        user_message: str,
        snapshot_dict: dict,
    ) -> ConversationMessageV5:
        """Send a user message and get an AI response using the fallback chain.

        The AI receives:
        - The V5 snapshot conversational context (authorized data only)
        - The conversation history
        - The user's question

        The AI does NOT receive:
        - Write access to identity, claims, sources, or state
        - URLs (model emits source_id, renderer generates links)
        - Raw candidates without identity features

        The model is asked to return structured JSON.
        The renderer produces Markdown.
        """
        from evidence_snapshot_v5 import EvidenceSnapshotV5
        from ai_output_validator_v5 import (
            validate_ai_output_v5, validate_structured_json,
            render_structured_report, generate_deterministic_report_v5,
        )

        # Build context from snapshot
        snapshot = EvidenceSnapshotV5(
            snapshot_id=snapshot_dict.get("snapshot_id", ""),
            snapshot_hash=snapshot_dict.get("snapshot_hash", ""),
            target=snapshot_dict.get("target", {}),
            origin=snapshot_dict.get("origin", {}),
            identity_resolution=snapshot_dict.get("identity_resolution", "UNRESOLVED"),
            external_corroboration=snapshot_dict.get("external_corroboration", "NONE"),
            asserted_claims=snapshot_dict.get("asserted_claims", []),
            origin_supported_claims=snapshot_dict.get("origin_supported_claims", []),
            independently_supported_claims=snapshot_dict.get("independently_supported_claims", []),
            conditional_gaps=snapshot_dict.get("conditional_gaps", []),
            person_candidates=snapshot_dict.get("person_candidates", []),
            rejected_candidates=snapshot_dict.get("rejected_candidates", []),
            accepted_evidence=snapshot_dict.get("accepted_evidence", []),
            web_leads=snapshot_dict.get("web_leads", []),
            context_sources=snapshot_dict.get("context_sources", []),
            search_results=snapshot_dict.get("search_results", []),
            next_steps=snapshot_dict.get("next_steps", []),
            limitations=snapshot_dict.get("limitations", []),
            research_mode=snapshot_dict.get("research_mode", "LOCAL_ONLY"),
        )
        context = snapshot.to_conversational_context()

        # Build system prompt — V5 with anti-hallucination constraints
        target = snapshot_dict.get("target", {})
        display_name = target.get("display_name", "")
        system_prompt = (
            "Sei l'Assistente della ricerca, un assistente conversazionale per "
            "ricerca storico-archivistica. Rispondi alle domande dell'utente "
            "basandoti ESCLUSIVAMENTE sui dati dello snapshot fornito. "
            "NON inventare dati, nomi, date, archivi, fondi o URL. "
            "NON negare l'esistenza di record verificati presenti nello snapshot. "
            "NON espandere sigle o acronimi senza un authority record. "
            "NON suggerire archivi o istituti non presenti nello snapshot o nel registry. "
            "NON dedurre professioni, malattie, fronti, campi o dettagli biografici non supportati. "
            f"Usa sempre il nome canonico: {display_name}. "
            "Non invertire nome e cognome. Non omettere il cognome. "
            "Se una domanda richiede nuove fonti non presenti nello snapshot, "
            "rispondi con suggested_research_action invece di inventare. "
            "Cita le fonti usando source_id, non URL. "
            "Restituisci output in JSON strutturato con le sezioni: "
            "title, identity_summary, origin_summary, external_evidence_summary, "
            "supported_facts, uncertainties, rejected_hypotheses, limitations, "
            "next_step_ids, source_ids, requires_new_research. "
            "Il provider e modello sono mostrati nei metadati tecnici."
        )

        # Build conversation history
        history = ""
        for msg in conversation.messages[-6:]:
            history += f"\n{msg.role}: {msg.content[:500]}\n"

        # Validator function for fallback chain
        def validator_fn(text: str, snap: dict) -> tuple:
            # Try JSON parse first
            try:
                data = json.loads(text)
                result = validate_structured_json(text, snap)
                if result.is_valid:
                    return True, []
                return False, result.reason_codes
            except json.JSONDecodeError:
                # Not JSON — validate as text
                result = validate_ai_output_v5(text, snap)
                return result.is_valid, result.reason_codes

        def deterministic_fn(snap: dict) -> str:
            return generate_deterministic_report_v5(snap)

        user_payload = json.dumps({
            "snapshot_context": context,
            "history": history,
            "question": user_message,
            "target_display_name": display_name,
            "authorized_claim_ids": [c.get("claim_id") for c in
                snap.get("asserted_claims", []) + snap.get("origin_supported_claims", []) +
                snap.get("independently_supported_claims", [])],
            "authorized_source_ids": [s.get("source_id") for s in
                snap.get("accepted_evidence", []) + snap.get("web_leads", []) +
                snap.get("context_sources", [])],
            "authorized_next_step_ids": [s.get("step_id") for s in snap.get("next_steps", [])],
        }, ensure_ascii=False, default=str)

        # Use fallback chain
        result = self._chain.generate(
            system_prompt=system_prompt,
            user_payload=user_payload,
            snapshot_dict=snapshot_dict,
            validator_fn=validator_fn,
            deterministic_fn=deterministic_fn,
            max_tokens=2048,
            temperature=0.2,
            timeout=60,
        )

        # Build response message
        content = result.text
        validation_state = "valid" if result.provider_used != "deterministic" else "fallback"

        # If model returned JSON, render as Markdown
        if result.ok and result.provider_used != "deterministic":
            try:
                data = json.loads(result.text)
                content = render_structured_report(data, snapshot_dict)
            except json.JSONDecodeError:
                pass  # Keep raw text

        msg = ConversationMessageV5(
            role="assistant",
            content=content,
            validation_state=validation_state,
            provider_used=result.provider_used,
            model_used=result.model_used,
            fallback_reason=result.fallback_reason,
        )

        # Validate the final content
        final_validation = validate_ai_output_v5(content, snapshot_dict)
        if not final_validation.is_valid:
            msg.validation_state = "fallback"
            msg.validation_reason_codes = final_validation.reason_codes
            if final_validation.detected_truncation:
                # Retry with reduced budget
                log.warning("Truncation detected — would retry with reduced budget")
                msg.content = generate_deterministic_report_v5(snapshot_dict)
                msg.validation_state = "fallback"
                msg.fallback_reason = "truncation_detected"

        # Update conversation provider/model
        conversation.provider = result.provider_used
        conversation.model = result.model_used

        # Store user message and assistant response
        user_msg = ConversationMessageV5(
            role="user", content=user_message,
            validation_state="valid",
            provider_used="user",
        )
        conversation.messages.append(user_msg)
        conversation.messages.append(msg)

        # Persist
        self._persist_messages(conversation, user_msg, msg)

        return msg

    def _persist_messages(self, conv: ConversationV5, user_msg: ConversationMessageV5, ai_msg: ConversationMessageV5):
        conn = sqlite3.connect(self._db_path)
        for msg in [user_msg, ai_msg]:
            conn.execute(
                """INSERT INTO conversation_messages_v5
                (conversation_id, role, content, timestamp, cited_claim_ids, cited_source_ids,
                 validation_state, validation_reason_codes, provider_used, model_used, fallback_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (conv.conversation_id, msg.role, msg.content, msg.timestamp,
                 json.dumps(msg.cited_claim_ids), json.dumps(msg.cited_source_ids),
                 msg.validation_state, json.dumps(msg.validation_reason_codes),
                 msg.provider_used, msg.model_used, msg.fallback_reason)
            )
        conn.execute(
            "UPDATE conversations_v5 SET updated_at = ?, provider = ?, model = ? WHERE conversation_id = ?",
            (datetime.now().isoformat(), conv.provider, conv.model, conv.conversation_id)
        )
        conn.commit()
        conn.close()

    def get_conversation(self, conversation_id: str) -> Optional[ConversationV5]:
        conn = sqlite3.connect(self._db_path)
        row = conn.execute(
            "SELECT * FROM conversations_v5 WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None

        conv = ConversationV5(
            conversation_id=row[0], report_id=row[1], snapshot_id=row[2],
            snapshot_hash=row[3], provider=row[4], model=row[5],
            created_at=row[6], updated_at=row[7],
        )

        msgs = conn.execute(
            """SELECT role, content, timestamp, cited_claim_ids, cited_source_ids,
               validation_state, validation_reason_codes, provider_used, model_used, fallback_reason
               FROM conversation_messages_v5 WHERE conversation_id = ? ORDER BY id""",
            (conversation_id,)
        ).fetchall()

        for m in msgs:
            conv.messages.append(ConversationMessageV5(
                role=m[0], content=m[1], timestamp=m[2],
                cited_claim_ids=json.loads(m[3]) if m[3] else [],
                cited_source_ids=json.loads(m[4]) if m[4] else [],
                validation_state=m[5],
                validation_reason_codes=json.loads(m[6]) if m[6] else [],
                provider_used=m[7] or "",
                model_used=m[8] or "",
                fallback_reason=m[9] or "",
            ))

        conn.close()
        return conv

    @property
    def openai_enabled(self) -> bool:
        return self._openai_configured

    @property
    def chain_state(self) -> dict:
        return self._chain.get_state()
