"""Conversational Report Provider — provider-agnostic interface.

Implements the chat requested without OpenAI:
- POST /research/reports/{report_id}/conversations
- POST /research/conversations/{conversation_id}/messages
- GET  /research/conversations/{conversation_id}

Uses Mistral or local model already configured.
OpenAI adapter is optional, disabled by default, and not tested live.

Key rules:
- A conversation is bound to an immutable snapshot version
- The backend re-sends to Mistral/local only authorized snapshot, instructions, and history
- The model has no write tools on identity, claims, sources, or state
- A question requiring new sources produces suggested_research_action, not invented answers
- "Approfondisci la ricerca" starts a new evidence cycle and a new snapshot version
- The deterministic report and chat remain available even if Mistral fails
- Provider and model are shown correctly in metadata
- No OpenAI calls when adapter is disabled
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
class ConversationMessage:
    """A single message in a research conversation."""
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cited_claim_ids: List[str] = field(default_factory=list)
    cited_source_ids: List[str] = field(default_factory=list)
    validation_state: str = "pending"  # pending | valid | invalid | fallback


@dataclass
class Conversation:
    """A research conversation bound to a snapshot."""
    conversation_id: str
    report_id: str
    snapshot_id: str
    snapshot_hash: str
    provider: str
    model: str
    messages: List[ConversationMessage] = field(default_factory=list)
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
            "messages": [asdict(m) if isinstance(m, ConversationMessage) else m for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ReportConversationProvider:
    """Provider-agnostic conversational report interface.

    Default provider: Mistral/local (already configured).
    OpenAI adapter: optional, disabled by default.
    """

    def __init__(self, provider: str = "mistral", model: str = ""):
        self.provider = provider
        self.model = model
        self._openai_enabled = False  # Hardcoded: OpenAI disabled
        self._db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "research_conversations.db"
        )
        self._init_db()

    def _init_db(self):
        """Initialize SQLite storage for conversations."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
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
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                cited_claim_ids TEXT,
                cited_source_ids TEXT,
                validation_state TEXT DEFAULT 'pending',
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)
        conn.commit()
        conn.close()

    def create_conversation(
        self,
        report_id: str,
        snapshot_dict: dict,
    ) -> Conversation:
        """Create a new conversation bound to a snapshot."""
        snap_id = snapshot_dict.get("snapshot_id", "")
        conversation_id = f"conv_{hashlib.sha256(f'{report_id}_{snap_id}'.encode()).hexdigest()[:12]}"

        conv = Conversation(
            conversation_id=conversation_id,
            report_id=report_id,
            snapshot_id=snapshot_dict.get("snapshot_id", ""),
            snapshot_hash=snapshot_dict.get("snapshot_hash", ""),
            provider=self.provider,
            model=self.model,
        )

        # Persist
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT OR REPLACE INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conv.conversation_id, conv.report_id, conv.snapshot_id,
             conv.snapshot_hash, conv.provider, conv.model,
             conv.created_at, conv.updated_at)
        )
        conn.commit()
        conn.close()

        return conv

    def send_message(
        self,
        conversation: Conversation,
        user_message: str,
        snapshot_dict: dict,
    ) -> ConversationMessage:
        """Send a user message and get an AI response.

        The AI receives:
        - The snapshot conversational context (authorized data only)
        - The conversation history
        - The user's question

        The AI does NOT receive:
        - Write access to identity, claims, sources, or state
        - URLs to render (model emits source_id, renderer generates links)
        - Raw candidates with confidence 0.1

        If the question requires new sources, the response includes
        suggested_research_action instead of invented answers.
        """
        # Build context from snapshot
        from evidence_snapshot_v4 import EvidenceSnapshotV4
        snapshot = EvidenceSnapshotV4(
            snapshot_id=snapshot_dict.get("snapshot_id", ""),
            snapshot_hash=snapshot_dict.get("snapshot_hash", ""),
            target_id=snapshot_dict.get("target_id", ""),
            target_hash=snapshot_dict.get("target_hash", ""),
            resolution_state=snapshot_dict.get("resolution_state", "UNRESOLVED"),
            origin_record_state=snapshot_dict.get("origin_record_state", "ABSENT"),
            accepted_claims=snapshot_dict.get("accepted_claims", []),
            missing_claims=snapshot_dict.get("missing_claims", []),
            rejected_candidates=snapshot_dict.get("rejected_candidates", []),
            accepted_origin_evidence_sources=snapshot_dict.get("accepted_origin_evidence_sources", []),
            research_limitations=snapshot_dict.get("research_limitations", []),
            reconciliation=snapshot_dict.get("reconciliation", {}),
        )
        context = snapshot.to_conversational_context()

        # Build system prompt
        system_prompt = (
            "Sei l'Assistente della ricerca, un assistente conversazionale per "
            "ricerca storico-archivistica. Rispondi alle domande dell'utente "
            "basandoti ESCLUSIVAMENTE sui dati dello snapshot fornito. "
            "NON inventare dati, nomi, date, archivi, fondi o URL. "
            "NON negare l'esistenza di record verificati presenti nello snapshot. "
            "Se una domanda richiede nuove fonti non presenti nello snapshot, "
            "rispondi con suggested_research_action invece di inventare. "
            "Cita le fonti usando source_id, non URL. "
            "Il provider e modello sono mostrati nei metadati tecnici."
        )

        # Build conversation history
        history = ""
        for msg in conversation.messages[-6:]:  # Last 6 messages for context
            history += f"\n{msg.role}: {msg.content}\n"

        # Try Mistral/local
        try:
            from ai_runtime import get_adapter
            adapter = get_adapter()
            health = adapter.health()

            if not health.healthy:
                # Fallback to deterministic
                return self._deterministic_response(
                    conversation, user_message, snapshot_dict
                )

            full_prompt = f"{system_prompt}\n\n{context}\n\n{history}\nuser: {user_message}\n"

            result = adapter.generate(
                system=system_prompt,
                user=json.dumps({
                    "snapshot_context": context,
                    "history": history,
                    "question": user_message,
                }, ensure_ascii=False),
                max_tokens=2048,
                temperature=0.2,
                task_type="conversational_report",
                timeout=60,
            )

            if result.ok and result.text:
                # Validate output
                from ai_output_validator import validate_ai_output
                validation = validate_ai_output(result.text, snapshot_dict)

                msg = ConversationMessage(
                    role="assistant",
                    content=result.text if validation.is_valid else
                        self._deterministic_content(user_message, snapshot_dict),
                    validation_state="valid" if validation.is_valid else "fallback",
                )

                if not validation.is_valid:
                    msg.content = self._deterministic_content(user_message, snapshot_dict)
                    msg.validation_state = "fallback"

                # Update model name
                self.model = health.model
            else:
                # AI generation failed — deterministic fallback
                msg = self._deterministic_response(
                    conversation, user_message, snapshot_dict
                )

        except Exception as e:
            log.warning("Conversational report: AI failed — %s, using deterministic", e)
            msg = self._deterministic_response(
                conversation, user_message, snapshot_dict
            )

        # Store user message and assistant response
        user_msg = ConversationMessage(role="user", content=user_message, validation_state="valid")
        conversation.messages.append(user_msg)
        conversation.messages.append(msg)

        # Persist
        self._persist_messages(conversation, user_msg, msg)

        return msg

    def _deterministic_response(
        self,
        conversation: Conversation,
        user_message: str,
        snapshot_dict: dict,
    ) -> ConversationMessage:
        """Generate a deterministic response when AI is unavailable."""
        content = self._deterministic_content(user_message, snapshot_dict)
        return ConversationMessage(
            role="assistant",
            content=content,
            validation_state="fallback",
        )

    def _deterministic_content(self, question: str, snapshot_dict: dict) -> str:
        """Generate deterministic content for a question."""
        from ai_output_validator import generate_deterministic_report
        return generate_deterministic_report(snapshot_dict)

    def _persist_messages(self, conv: Conversation, user_msg: ConversationMessage, ai_msg: ConversationMessage):
        """Persist messages to SQLite."""
        conn = sqlite3.connect(self._db_path)
        for msg in [user_msg, ai_msg]:
            conn.execute(
                "INSERT INTO conversation_messages (conversation_id, role, content, timestamp, cited_claim_ids, cited_source_ids, validation_state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conv.conversation_id, msg.role, msg.content, msg.timestamp,
                 json.dumps(msg.cited_claim_ids), json.dumps(msg.cited_source_ids),
                 msg.validation_state)
            )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
            (datetime.now().isoformat(), conv.conversation_id)
        )
        conn.commit()
        conn.close()

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Retrieve a conversation by ID."""
        conn = sqlite3.connect(self._db_path)
        row = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None

        conv = Conversation(
            conversation_id=row[0], report_id=row[1], snapshot_id=row[2],
            snapshot_hash=row[3], provider=row[4], model=row[5],
            created_at=row[6], updated_at=row[7],
        )

        msgs = conn.execute(
            "SELECT role, content, timestamp, cited_claim_ids, cited_source_ids, validation_state FROM conversation_messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,)
        ).fetchall()

        for m in msgs:
            conv.messages.append(ConversationMessage(
                role=m[0], content=m[1], timestamp=m[2],
                cited_claim_ids=json.loads(m[3]) if m[3] else [],
                cited_source_ids=json.loads(m[4]) if m[4] else [],
                validation_state=m[5],
            ))

        conn.close()
        return conv

    @property
    def openai_enabled(self) -> bool:
        """OpenAI is always disabled in this environment."""
        return self._openai_enabled
