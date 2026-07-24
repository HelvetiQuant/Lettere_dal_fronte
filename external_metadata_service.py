"""Service per import incrementale di metadati da fonti esterne federate.

Gestisce:
- Import incrementale con checkpoint
- Deduplicazione via metadata_hash
- Aggiornamento di record esistenti
- Job riprendibili
- Lock per impedire import concorrenti dello stesso provider
- Registrazione errori
"""
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any

from database import get_conn
from sources_external_base import SourceAdapter, compute_metadata_hash
from sources_external_archimista import ArchimistaAdapter
from sources_external_lebi import LeBIAdapter


# ─── Registry adapter ───────────────────────────────────────────────────
_ADAPTERS: Dict[str, SourceAdapter] = {}

def get_adapter(provider: str) -> Optional[SourceAdapter]:
    if not _ADAPTERS:
        _ADAPTERS["cri_milano"] = ArchimistaAdapter()
        _ADAPTERS["lebi"] = LeBIAdapter()
    return _ADAPTERS.get(provider)

def list_providers() -> List[Dict[str, str]]:
    if not _ADAPTERS:
        _ADAPTERS["cri_milano"] = ArchimistaAdapter()
        _ADAPTERS["lebi"] = LeBIAdapter()
    return [{"provider_id": a.provider_id, "display_name": a.display_name,
             "archive_name": a.archive_name, "base_url": a.base_url}
            for a in _ADAPTERS.values()]


# ─── Progress tracking ──────────────────────────────────────────────────
_import_progress: Dict[str, Dict] = {}
_import_locks: Dict[str, threading.Lock] = {}


def get_import_progress(provider: str) -> Dict:
    return dict(_import_progress.get(provider, {"status": "idle"}))


def _set_progress(provider: str, **kwargs):
    if provider not in _import_progress:
        _import_progress[provider] = {"status": "idle"}
    _import_progress[provider].update(kwargs)


# ─── CRUD record ────────────────────────────────────────────────────────
def upsert_record(record_data: Dict[str, Any]) -> Dict[str, Any]:
    """Inserisce o aggiorna un record esterno. Idempotente via UNIQUE(provider, external_id)."""
    conn = get_conn()
    now = datetime.now().isoformat()
    provider = record_data["provider"]
    external_id = record_data["external_id"]

    # Check existing
    existing = conn.execute(
        "SELECT id, metadata_hash FROM external_source_records WHERE provider = ? AND external_id = ?",
        (provider, external_id)
    ).fetchone()

    if existing:
        # Update only if hash changed
        if existing["metadata_hash"] == record_data.get("metadata_hash"):
            # Just update last_verified_at
            conn.execute(
                "UPDATE external_source_records SET last_verified_at = ?, http_status = ?, updated_at = ? WHERE id = ?",
                (now, record_data.get("http_status"), now, existing["id"])
            )
            conn.commit()
            conn.close()
            return {"id": existing["id"], "action": "unchanged"}

        # Update
        record_data["updated_at"] = now
        record_data["last_verified_at"] = now
        fields = list(record_data.keys())
        set_clause = ", ".join(f"{f} = ?" for f in fields)
        values = list(record_data.values()) + [existing["id"]]
        conn.execute(
            f"UPDATE external_source_records SET {set_clause} WHERE id = ?",
            values
        )
        conn.commit()
        conn.close()
        return {"id": existing["id"], "action": "updated"}
    else:
        # Insert
        record_data["first_seen_at"] = now
        record_data["last_verified_at"] = now
        record_data["created_at"] = now
        record_data["updated_at"] = now
        fields = list(record_data.keys())
        placeholders = ", ".join(["?"] * len(fields))
        col_list = ", ".join(fields)
        cur = conn.execute(
            f"INSERT INTO external_source_records ({col_list}) VALUES ({placeholders})",
            list(record_data.values())
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return {"id": new_id, "action": "inserted"}


def save_person_mentions(record_id: int, mentions: List[Dict[str, Any]]) -> int:
    """Salva menzioni nominative. Sostituisce quelle esistenti per lo stesso record."""
    conn = get_conn()
    now = datetime.now().isoformat()

    # Delete existing mentions for this record
    conn.execute("DELETE FROM external_person_mentions WHERE external_source_record_id = ?", (record_id,))

    count = 0
    for m in mentions:
        m["external_source_record_id"] = record_id
        m["created_at"] = now
        m["updated_at"] = now
        fields = list(m.keys())
        placeholders = ", ".join(["?"] * len(fields))
        col_list = ", ".join(fields)
        conn.execute(
            f"INSERT INTO external_person_mentions ({col_list}) VALUES ({placeholders})",
            list(m.values())
        )
        count += 1

    conn.commit()
    conn.close()
    return count


def save_facts(record_id: int, facts: List[Dict[str, Any]]) -> int:
    """Salva fatti. Sostituisce quelli esistenti per lo stesso record."""
    conn = get_conn()
    now = datetime.now().isoformat()

    conn.execute("DELETE FROM external_source_facts WHERE external_source_record_id = ?", (record_id,))

    count = 0
    for f in facts:
        f["external_source_record_id"] = record_id
        f["created_at"] = now
        fields = list(f.keys())
        placeholders = ", ".join(["?"] * len(fields))
        col_list = ", ".join(fields)
        conn.execute(
            f"INSERT INTO external_source_facts ({col_list}) VALUES ({placeholders})",
            list(f.values())
        )
        count += 1

    conn.commit()
    conn.close()
    return count


def save_digital_objects(record_id: int, objects: List[Dict[str, Any]]) -> int:
    """Salva oggetti digitali. Sostituisce quelli esistenti per lo stesso record."""
    conn = get_conn()
    now = datetime.now().isoformat()

    conn.execute("DELETE FROM external_digital_objects WHERE external_source_record_id = ?", (record_id,))

    count = 0
    for o in objects:
        o["external_source_record_id"] = record_id
        o["created_at"] = now
        o["updated_at"] = now
        fields = list(o.keys())
        placeholders = ", ".join(["?"] * len(fields))
        col_list = ", ".join(fields)
        conn.execute(
            f"INSERT INTO external_digital_objects ({col_list}) VALUES ({placeholders})",
            list(o.values())
        )
        count += 1

    conn.commit()
    conn.close()
    return count


# ─── Import job ─────────────────────────────────────────────────────────
def run_import(provider: str, start_url: Optional[str] = None,
               max_records: int = 0, force_refresh: bool = False,
               resume: bool = False, batch_size: int = 50) -> Dict[str, Any]:
    """Esegue import incrementale da un provider.
    
    Thread-safe con lock per provider.
    Supporta checkpoint/resume: se resume=True, riprende dall'ultimo job incompleto.
    Per LeBI: start_url è il cognome da cercare (es. "Rossi").
    Per CRI Milano: start_url è l'URL del fondo archivistico.
    """
    # Lock per provider
    if provider not in _import_locks:
        _import_locks[provider] = threading.Lock()

    if not _import_locks[provider].acquire(blocking=False):
        return {"error": f"Import già in corso per provider {provider}"}

    try:
        adapter = get_adapter(provider)
        if not adapter:
            return {"error": f"Provider {provider} non trovato"}

        # Default start_url per provider specifici
        if not start_url:
            if provider == "lebi":
                start_url = ""  # LeBI usa discover con cognome vuoto = tutti
            else:
                start_url = adapter.base_url + "/fonds/10039"  # Fondo principale CRI Milano

        # Resume: cerca ultimo job incompleto
        resume_job_id = None
        processed_urls = set()
        if resume:
            conn = get_conn()
            last_job = conn.execute(
                "SELECT id, processed_records, total_records FROM external_import_jobs WHERE provider = ? AND status = 'running' ORDER BY id DESC LIMIT 1",
                (provider,)
            ).fetchone()
            if last_job:
                resume_job_id = last_job["id"]
                # Recupera URL già processati
                existing = conn.execute(
                    "SELECT canonical_record_url FROM external_source_records WHERE provider = ?",
                    (provider,)
                ).fetchall()
                processed_urls = {r["canonical_record_url"] for r in existing}
            conn.close()

        _set_progress(provider, status="running", processed=0, total=0, current=start_url, errors=0)

        # Crea o aggiorna job record
        conn = get_conn()
        now = datetime.now().isoformat()
        if resume_job_id:
            job_id = resume_job_id
            conn.execute(
                "UPDATE external_import_jobs SET status = ?, updated_at = ? WHERE id = ?",
                ("running", now, job_id)
            )
            conn.commit()
        else:
            cur = conn.execute(
                "INSERT INTO external_import_jobs (provider, job_type, status, started_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (provider, "full_import", "running", now, now, now)
            )
            job_id = cur.lastrowid
            conn.commit()
        conn.close()

        # Discover
        _set_progress(provider, status="discovering")
        resources = adapter.discover_resources(start_url, max_records)
        total = len(resources)
        _set_progress(provider, status="importing", processed=0, total=total, errors=0)

        processed = 0
        errors = 0
        inserted = 0
        updated = 0
        unchanged = 0
        skipped = 0

        for res in resources:
            url = res.get("canonical_record_url") or res.get("url", "")
            
            # Skip already processed if resuming
            if resume and url in processed_urls:
                skipped += 1
                processed += 1
                continue

            try:
                # Parse full record
                record_data = adapter.parse_record(url)
                if not record_data:
                    errors += 1
                    continue

                # Upsert
                result = upsert_record(record_data)
                record_id = result["id"]

                if result["action"] == "inserted":
                    inserted += 1
                elif result["action"] == "updated":
                    updated += 1
                else:
                    unchanged += 1

                # If inserted/updated, extract and save mentions, facts, digital objects
                if result["action"] in ("inserted", "updated") or force_refresh:
                    mentions = adapter.extract_person_mentions(record_data)
                    save_person_mentions(record_id, mentions)

                    facts = adapter.extract_facts(record_data, mentions)
                    save_facts(record_id, facts)

                    digital_objects = adapter.detect_digital_objects(record_data)
                    save_digital_objects(record_id, digital_objects)

                processed += 1
                _set_progress(provider, processed=processed, total=total, errors=errors,
                              current=url)

                # Update job periodically (every batch_size records)
                if processed % batch_size == 0:
                    conn = get_conn()
                    conn.execute(
                        "UPDATE external_import_jobs SET processed_records = ?, error_count = ?, updated_at = ? WHERE id = ?",
                        (processed, errors, datetime.now().isoformat(), job_id)
                    )
                    conn.commit()
                    conn.close()

            except Exception as e:
                errors += 1
                _set_progress(provider, errors=errors)
                # Log error but continue
                conn = get_conn()
                conn.execute(
                    "UPDATE external_import_jobs SET error_count = ?, last_error = ?, updated_at = ? WHERE id = ?",
                    (errors, str(e)[:500], datetime.now().isoformat(), job_id)
                )
                conn.commit()
                conn.close()

        # Finalize job
        now = datetime.now().isoformat()
        conn = get_conn()
        conn.execute(
            "UPDATE external_import_jobs SET status = ?, total_records = ?, processed_records = ?, error_count = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            ("completed", total, processed, errors, now, now, job_id)
        )
        conn.commit()
        conn.close()

        _set_progress(provider, status="completed", processed=processed, total=total, errors=errors)

        return {
            "job_id": job_id,
            "total": total,
            "processed": processed,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "skipped": skipped,
            "errors": errors,
        }

    except Exception as e:
        _set_progress(provider, status="error", error=str(e))
        conn = get_conn()
        conn.execute(
            "UPDATE external_import_jobs SET status = ?, last_error = ?, finished_at = ?, updated_at = ? WHERE id = ?",
            ("error", str(e)[:500], datetime.now().isoformat(), datetime.now().isoformat(),
             job_id if "job_id" in dir() else 0)
        )
        conn.commit()
        conn.close()
        return {"error": str(e)}

    finally:
        _import_locks[provider].release()


def refresh_single_record(record_id: int) -> Dict[str, Any]:
    """Aggiorna un singolo record esterno."""
    conn = get_conn()
    record = conn.execute(
        "SELECT * FROM external_source_records WHERE id = ?", (record_id,)
    ).fetchone()
    conn.close()

    if not record:
        return {"error": "Record non trovato"}

    adapter = get_adapter(record["provider"])
    if not adapter:
        return {"error": f"Provider {record['provider']} non disponibile"}

    record_data = adapter.parse_record(record["canonical_record_url"])
    if not record_data:
        return {"error": "Impossibile recuperare la pagina"}

    result = upsert_record(record_data)
    if result["action"] in ("inserted", "updated"):
        mentions = adapter.extract_person_mentions(record_data)
        save_person_mentions(record_id, mentions)
        facts = adapter.extract_facts(record_data, mentions)
        save_facts(record_id, facts)
        digital_objects = adapter.detect_digital_objects(record_data)
        save_digital_objects(record_id, digital_objects)

    return {"id": record_id, "action": result["action"]}


def verify_record_url(record_id: int) -> Dict[str, Any]:
    """Verifica raggiungibilità dell'URL canonico di un record."""
    conn = get_conn()
    record = conn.execute(
        "SELECT canonical_record_url, provider FROM external_source_records WHERE id = ?", (record_id,)
    ).fetchone()
    if not record:
        conn.close()
        return {"error": "Record non trovato"}

    adapter = get_adapter(record["provider"])
    if not adapter:
        conn.close()
        return {"error": "Provider non disponibile"}

    result = adapter.verify_url(record["canonical_record_url"])

    # Update record
    now = datetime.now().isoformat()
    status = "active" if result["reachable"] else "unreachable"
    if result["http_status"] == 404:
        status = "not_found"
    elif result["http_status"] in (301, 308):
        status = "moved"

    conn.execute(
        "UPDATE external_source_records SET http_status = ?, access_status = ?, last_verified_at = ?, updated_at = ? WHERE id = ?",
        (result["http_status"], status, now, now, record_id)
    )
    conn.commit()
    conn.close()

    return result


# ─── LeBI-specific import helpers ────────────────────────────────────────
def import_single_lebi_record(lebi_id: str) -> Dict[str, Any]:
    """Importa una singola scheda LeBI per ID.
    
    Esempio: import_single_lebi_record("24185")
    """
    adapter = get_adapter("lebi")
    if not adapter:
        return {"error": "Adapter LeBI non disponibile"}

    url = f"{adapter.base_url}/frontend_prodimi.php/caduti/show/{lebi_id}"
    record_data = adapter.parse_record(url)
    if not record_data:
        return {"error": f"Impossibile recuperare scheda LeBI #{lebi_id}"}

    result = upsert_record(record_data)
    record_id = result["id"]

    if result["action"] in ("inserted", "updated"):
        mentions = adapter.extract_person_mentions(record_data)
        save_person_mentions(record_id, mentions)
        facts = adapter.extract_facts(record_data, mentions)
        save_facts(record_id, facts)
        digital_objects = adapter.detect_digital_objects(record_data)
        save_digital_objects(record_id, digital_objects)

    return {"id": record_id, "action": result["action"], "lebi_id": lebi_id}


def import_lebi_by_surname(surname: str, max_records: int = 100) -> Dict[str, Any]:
    """Importa record LeBI cercando per cognome.
    
    Esempio: import_lebi_by_surname("Rossi", max_records=50)
    """
    return run_import("lebi", start_url=surname, max_records=max_records)
