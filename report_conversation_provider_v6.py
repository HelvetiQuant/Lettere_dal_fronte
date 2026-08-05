"""Report Conversation Provider V6 — structured output + multi-level validation.

Key changes from V4/V5:
- Uses factory pattern to select provider (OpenAI, Mistral, LM Studio, deterministic)
- Model returns structured JSON (answer + supported_statement_groups)
- Renderer converts suggested_action_ids to discursive text via catalog
- Multi-level validation (schema, semantic, grounding, render, conversation)
- No internal tokens visible to user
- Provider class, contract version, and schema version in every response
- Fallback to deterministic if any validation level fails
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

from ai_output_validator_v6 import validate_v6, generate_deterministic_v6
from next_step_catalog import NextStepCatalog

log = logging.getLogger(__name__)


@dataclass
class ConversationMessageV6:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    validation_state: str = "pending"  # pending|valid|invalid|fallback
    validation_details: Dict[str, Any] = field(default_factory=dict)
    cited_claim_ids: List[str] = field(default_factory=list)
    cited_source_ids: List[str] = field(default_factory=list)
    provider_class: str = ""
    provider_contract_version: str = ""
    snapshot_schema_version: str = ""
    renderer_version: str = ""
    validator_version: str = ""
    requires_new_research: bool = False


@dataclass
class ConversationV6:
    conversation_id: str
    report_id: str
    snapshot_id: str
    snapshot_hash: str
    provider: str
    model: str
    messages: List[ConversationMessageV6] = field(default_factory=list)
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


class ReportConversationProviderV6:
    """V6 conversational report provider with structured output and multi-level validation."""

    PROVIDER_CLASS = "ReportConversationProviderV6"
    CONTRACT_VERSION = "6.0"
    RENDERER_VERSION = "6.0"
    VALIDATOR_VERSION = "6.0"

    def __init__(self, provider_name: str = "openai", model: str = ""):
        self.provider_name = provider_name
        self.model = model
        self._db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "research_conversations_v6.db"
        )
        self._init_db()
        self._catalog = NextStepCatalog()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations_v6 (
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
            CREATE TABLE IF NOT EXISTS conversation_messages_v6 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                validation_state TEXT DEFAULT 'pending',
                validation_details TEXT,
                cited_claim_ids TEXT,
                cited_source_ids TEXT,
                provider_class TEXT,
                provider_contract_version TEXT,
                snapshot_schema_version TEXT,
                renderer_version TEXT,
                validator_version TEXT,
                requires_new_research INTEGER DEFAULT 0,
                FOREIGN KEY (conversation_id) REFERENCES conversations_v6(conversation_id)
            )
        """)
        conn.commit()
        conn.close()

    def create_conversation(self, report_id: str, snapshot_dict: dict) -> ConversationV6:
        snap_id = snapshot_dict.get("snapshot_id", "")
        conversation_id = f"conv_v6_{hashlib.sha256(f'{report_id}_{snap_id}'.encode()).hexdigest()[:12]}"

        conv = ConversationV6(
            conversation_id=conversation_id,
            report_id=report_id,
            snapshot_id=snap_id,
            snapshot_hash=snapshot_dict.get("snapshot_hash", ""),
            provider=self.provider_name,
            model=self.model,
        )

        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT OR REPLACE INTO conversations_v6 VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conv.conversation_id, conv.report_id, conv.snapshot_id,
             conv.snapshot_hash, conv.provider, conv.model,
             conv.created_at, conv.updated_at)
        )
        conn.commit()
        conn.close()

        return conv

    def send_message(
        self,
        conversation: ConversationV6,
        user_message: str,
        snapshot_dict: dict,
    ) -> ConversationMessageV6:
        """Send a user message and get an AI response.

        The model returns structured JSON. The renderer converts it to
        discursive text. The validator checks all levels.
        If any level fails, fallback to deterministic.
        """
        # Build conversational context from snapshot
        from evidence_snapshot_v6 import EvidenceSnapshotV6
        try:
            snap = EvidenceSnapshotV6.from_dict(snapshot_dict)
            context = snap.to_conversational_context()
        except Exception:
            context = json.dumps(snapshot_dict, ensure_ascii=False, indent=2)

        # Build conversation history
        history = ""
        for msg in conversation.messages[-6:]:
            history += f"\n{msg.role}: {msg.content[:200]}\n"

        # Try provider
        msg = self._try_provider(context, user_message, history, snapshot_dict, conversation)

        # Store messages
        user_msg = ConversationMessageV6(
            role="user",
            content=user_message,
            validation_state="valid",
            provider_class=self.PROVIDER_CLASS,
            provider_contract_version=self.CONTRACT_VERSION,
            snapshot_schema_version=snapshot_dict.get("schema_version", "6"),
            renderer_version=self.RENDERER_VERSION,
            validator_version=self.VALIDATOR_VERSION,
        )
        conversation.messages.append(user_msg)
        conversation.messages.append(msg)

        self._persist_messages(conversation, user_msg, msg)
        return msg

    def _try_provider(
        self,
        context: str,
        question: str,
        history: str,
        snapshot_dict: dict,
        conversation: ConversationV6,
    ) -> ConversationMessageV6:
        """Try the configured provider, with fallback to deterministic."""

        # Try OpenAI
        if self.provider_name == "openai" and os.environ.get("OPENAI_API_KEY"):
            try:
                from openai_responses_adapter import OpenAIResponsesAdapter
                adapter = OpenAIResponsesAdapter()
                if adapter.available:
                    result = adapter.generate_conversation(context, question, history)
                    if result.success and result.report_json:
                        return self._render_and_validate(
                            result.report_json, snapshot_dict, question, history,
                            conversation, result.model or "gpt-4o-mini",
                        )
            except Exception as e:
                log.warning("OpenAI provider failed: %s", str(e)[:100])

        # Try Mistral / LM Studio via ai_runtime
        try:
            from ai_runtime import get_adapter
            adapter = get_adapter()
            health = adapter.health()
            if health.healthy:
                system_prompt = self._build_system_prompt()
                result = adapter.generate(
                    system=system_prompt,
                    user=json.dumps({
                        "snapshot_context": context,
                        "history": history,
                        "question": question,
                    }, ensure_ascii=False),
                    max_tokens=2048,
                    temperature=0.2,
                    task_type="conversational_report",
                    timeout=60,
                )
                if result.ok and result.text:
                    # Try to parse as JSON (structured output)
                    report_json = None
                    try:
                        report_json = json.loads(result.text)
                    except json.JSONDecodeError:
                        # Not JSON — treat as plain text
                        report_json = {"answer": result.text, "supported_statement_groups": [], "requires_new_research": False}

                    return self._render_and_validate(
                        report_json, snapshot_dict, question, history,
                        conversation, health.model or "mistral",
                    )
        except Exception as e:
            log.warning("Mistral/local provider failed: %s", str(e)[:100])

        # Fallback to deterministic
        return self._deterministic_response(question, snapshot_dict, conversation)

    def _build_system_prompt(self) -> str:
        return (
            "Sei l'Assistente della ricerca storico-archivistica. "
            "Rispondi ESCLUSIVAMENTE in base ai dati dello snapshot fornito. "
            "NON inventare dati, nomi, date, archivi, fondi o URL. "
            "NON negare l'esistenza di record verificati presenti nello snapshot. "
            "Se una domanda richiede nuove fonti, imposta requires_new_research=true. "
            "Ogni affermazione fattuale deve essere supportata da un claim accettato. "
            "Rispondi in italiano in modo discorsivo e naturale. "
            "Il campo 'answer' deve contenere SOLO testo conversazionale in italiano, NON JSON o markdown. "
            "Restituisci un JSON con i campi: answer, supported_statement_groups, "
            "uncertainties, rejected_hypotheses, suggested_action_ids, requires_new_research."
        )

    @staticmethod
    def _strip_markdown_json(text: str) -> str:
        """If the AI wrapped the answer in markdown JSON fences, extract the inner answer."""
        if not text:
            return text
        text = text.strip()
        # Check for ```json...``` or ```...``` wrapping
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's just ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            inner = "\n".join(lines).strip()
            # Try to parse as JSON and extract the answer field
            try:
                inner_json = json.loads(inner)
                if isinstance(inner_json, dict) and "answer" in inner_json:
                    return inner_json["answer"]
            except (json.JSONDecodeError, TypeError):
                pass
            return inner
        return text

    def _render_and_validate(
        self,
        report_json: dict,
        snapshot_dict: dict,
        question: str,
        history: str,
        conversation: ConversationV6,
        model: str,
    ) -> ConversationMessageV6:
        """Render structured JSON to discursive text and validate."""

        # Extract answer — strip markdown fences if AI wrapped it
        answer = report_json.get("answer", "")
        answer = self._strip_markdown_json(answer)
        supported_groups = report_json.get("supported_statement_groups", [])
        suggested_action_ids = report_json.get("suggested_action_ids", [])
        requires_new_research = report_json.get("requires_new_research", False)

        # Clean claim_id from supported groups (internal token)
        for group in supported_groups:
            if isinstance(group, dict):
                group.pop("claim_id", None)
                for stmt in group.get("statements", []):
                    if isinstance(stmt, dict):
                        stmt.pop("claim_id", None)

        # Render suggested_action_ids to discursive text via catalog
        rendered_actions = []
        for action_id in suggested_action_ids:
            entry = self._catalog.get(action_id)
            if entry:
                rendered_actions.append(f"- {entry.description} (archivio: {entry.archive}, accesso: {entry.access_mode})")
            else:
                # Unknown action ID — do not expose it
                log.warning("Unknown suggested_action_id: %s", action_id)

        # Build final content
        content = answer
        if rendered_actions:
            content += "\n\nProssimi passi suggeriti:\n" + "\n".join(rendered_actions)

        if requires_new_research:
            content += "\n\nQuesta domanda richiede una nuova ricerca per essere risposta in modo completo."

        # Extract cited claim IDs
        cited_claims = []
        for group in supported_groups:
            cited_claims.extend(group.get("claim_ids", []))

        # Validate
        conv_history = [{"role": m.role, "content": m.content} for m in conversation.messages[-4:]]
        validation = validate_v6(
            content,
            snapshot_dict,
            is_structured=False,  # We already extracted the answer
            conversation_history=conv_history,
        )

        if not validation.responses_valid:
            # Fallback to deterministic
            log.warning("Validation failed: %s — using deterministic fallback", validation.violations)
            log.warning("AI raw answer (rejected): %s", content[:500])
            log.warning("AI raw JSON: %s", json.dumps(report_json, ensure_ascii=False)[:500])
            det = self._deterministic_response(question, snapshot_dict, conversation)
            det.validation_details = {
                "fallback_used": True,
                "reason": "ai_validation_failed",
                "violations": validation.violations,
                "ai_raw_answer": content[:1000],
                "ai_raw_json": json.dumps(report_json, ensure_ascii=False)[:1000],
                "ai_model": model,
            }
            return det

        self.model = model
        return ConversationMessageV6(
            role="assistant",
            content=content,
            validation_state="valid",
            validation_details=validation.to_dict(),
            cited_claim_ids=cited_claims,
            provider_class=self.PROVIDER_CLASS,
            provider_contract_version=self.CONTRACT_VERSION,
            snapshot_schema_version=snapshot_dict.get("schema_version", "6"),
            renderer_version=self.RENDERER_VERSION,
            validator_version=self.VALIDATOR_VERSION,
            requires_new_research=requires_new_research,
        )

    def _deterministic_response(
        self,
        question: str,
        snapshot_dict: dict,
        conversation: ConversationV6,
    ) -> ConversationMessageV6:
        """Generate deterministic fallback response."""
        content = generate_deterministic_v6(snapshot_dict, question)
        return ConversationMessageV6(
            role="assistant",
            content=content,
            validation_state="fallback",
            validation_details={"fallback_used": True, "reason": "ai_provider_unavailable_or_invalid"},
            provider_class=self.PROVIDER_CLASS,
            provider_contract_version=self.CONTRACT_VERSION,
            snapshot_schema_version=snapshot_dict.get("schema_version", "6"),
            renderer_version=self.RENDERER_VERSION,
            validator_version=self.VALIDATOR_VERSION,
        )

    def _persist_messages(self, conv: ConversationV6, user_msg: ConversationMessageV6, ai_msg: ConversationMessageV6):
        conn = sqlite3.connect(self._db_path)
        for msg in [user_msg, ai_msg]:
            conn.execute(
                """INSERT INTO conversation_messages_v6
                (conversation_id, role, content, timestamp, validation_state,
                 validation_details, cited_claim_ids, cited_source_ids,
                 provider_class, provider_contract_version, snapshot_schema_version,
                 renderer_version, validator_version, requires_new_research)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (conv.conversation_id, msg.role, msg.content, msg.timestamp,
                 msg.validation_state, json.dumps(msg.validation_details),
                 json.dumps(msg.cited_claim_ids), json.dumps(msg.cited_source_ids),
                 msg.provider_class, msg.provider_contract_version,
                 msg.snapshot_schema_version, msg.renderer_version,
                 msg.validator_version, 1 if msg.requires_new_research else 0)
            )
        conn.execute(
            "UPDATE conversations_v6 SET updated_at = ? WHERE conversation_id = ?",
            (datetime.now().isoformat(), conv.conversation_id)
        )
        conn.commit()
        conn.close()

    def get_conversation(self, conversation_id: str) -> Optional[ConversationV6]:
        conn = sqlite3.connect(self._db_path)
        row = conn.execute(
            "SELECT * FROM conversations_v6 WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        if not row:
            conn.close()
            return None

        conv = ConversationV6(
            conversation_id=row[0], report_id=row[1], snapshot_id=row[2],
            snapshot_hash=row[3], provider=row[4], model=row[5],
            created_at=row[6], updated_at=row[7],
        )

        msgs = conn.execute(
            "SELECT role, content, timestamp, validation_state, validation_details, "
            "cited_claim_ids, cited_source_ids, provider_class, provider_contract_version, "
            "snapshot_schema_version, renderer_version, validator_version, requires_new_research "
            "FROM conversation_messages_v6 WHERE conversation_id = ? ORDER BY id",
            (conversation_id,)
        ).fetchall()

        for m in msgs:
            conv.messages.append(ConversationMessageV6(
                role=m[0], content=m[1], timestamp=m[2],
                validation_state=m[3],
                validation_details=json.loads(m[4]) if m[4] else {},
                cited_claim_ids=json.loads(m[5]) if m[5] else [],
                cited_source_ids=json.loads(m[6]) if m[6] else [],
                provider_class=m[7] or "",
                provider_contract_version=m[8] or "",
                snapshot_schema_version=m[9] or "",
                renderer_version=m[10] or "",
                validator_version=m[11] or "",
                requires_new_research=bool(m[12]),
            ))

        conn.close()
        return conv


# ─── Factory ─────────────────────────────────────────────────────────────────

def create_provider_v6(preferred: str = "openai") -> ReportConversationProviderV6:
    """Factory: create the best available V6 provider.

    Priority: OpenAI > Mistral > LM Studio > deterministic
    """
    # Check OpenAI
    if preferred == "openai" and os.environ.get("OPENAI_API_KEY"):
        try:
            from openai_responses_adapter import OpenAIResponsesAdapter
            adapter = OpenAIResponsesAdapter()
            if adapter.available:
                return ReportConversationProviderV6(provider_name="openai", model="gpt-4o-mini")
        except Exception:
            pass

    # Check Mistral / LM Studio
    try:
        from ai_runtime import get_adapter
        adapter = get_adapter()
        health = adapter.health()
        if health.healthy:
            return ReportConversationProviderV6(provider_name=health.provider or "mistral", model=health.model or "")
    except Exception:
        pass

    # Fallback: deterministic only
    return ReportConversationProviderV6(provider_name="deterministic", model="deterministic-v6")
