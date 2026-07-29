"""
CLI per la pipeline di acquisizione fonti.

Comandi:
    python -m source_pipeline.cli sync-providers    — sync provider registry to Supabase
    python -m source_pipeline.cli enqueue            — enqueue a discovery job
    python -m source_pipeline.cli worker             — start the worker
    python -m source_pipeline.cli status             — show queue status
    python -m source_pipeline.cli cancel <job_id>    — cancel a job
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("source_pipeline.cli")


def _get_db_conn():
    from database import get_conn
    return get_conn()


def _get_supabase():
    try:
        from supabase_client import execute_sql
        return execute_sql
    except Exception:
        return None


def cmd_sync_providers(args):
    from source_pipeline.registry import load_providers, sync_to_supabase

    yaml_path = Path(__file__).parent.parent / "config" / "archive_providers.yml"
    providers = load_providers(yaml_path)
    print(f"Loaded {len(providers)} providers from {yaml_path}")

    sb = _get_supabase()
    if not sb:
        print("WARNING: Supabase client not available. Dry-run only.")
        for code, cfg in providers.items():
            print(f"  {code}: {cfg.display_name} ({cfg.authority_class}, {cfg.access_mode})")
        return

    count = sync_to_supabase(providers, sb)
    print(f"Synced {count}/{len(providers)} providers to Supabase archive.providers")


def cmd_enqueue(args):
    conn = _get_db_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        idempotency_key = f"{args.provider}:{args.type}:{args.query or ''}:{args.external_id or ''}"
        import hashlib
        idem_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]

        existing = conn.execute(
            "SELECT id FROM ops_job_queue WHERE idempotency_key = ? AND status IN ('queued', 'pending', 'running', 'retry_wait')",
            (idem_hash,),
        ).fetchone()
        if existing:
            print(f"Job already queued (id={existing[0]}) with idempotency key {idem_hash}")
            return

        payload = {
            "query": args.query or "",
            "external_id": args.external_id or "",
        }
        conn.execute(
            """
            INSERT INTO ops_job_queue
                (job_type, provider_code, query_payload, payload_json, idempotency_key,
                 status, priority, max_attempts, created_at)
            VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (
                args.type,
                args.provider,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                idem_hash,
                args.priority,
                args.max_attempts,
                now,
            ),
        )
        conn.commit()
        print(f"Enqueued job: type={args.type} provider={args.provider} query='{args.query}'")
    finally:
        conn.close()


def cmd_worker(args):
    from source_pipeline.worker import JobQueueWorker, WorkerConfig
    from source_pipeline.registry import load_providers

    yaml_path = Path(__file__).parent.parent / "config" / "archive_providers.yml"
    provider_configs = load_providers(yaml_path)

    # For now, use empty adapter dict — actual adapters are registered separately
    # The worker will fail gracefully on jobs for providers without adapters
    adapters = {}

    config = WorkerConfig(
        max_concurrent_per_provider=args.concurrency,
        poll_interval_seconds=args.poll_interval,
        max_attempts=args.max_attempts,
    )

    worker = JobQueueWorker(
        config=config,
        providers=adapters,
        db_conn_func=_get_db_conn,
        supabase_client=_get_supabase(),
    )

    print(f"Worker started (max_iterations={args.max_iterations}, poll={args.poll_interval}s)")
    print("Press Ctrl+C to stop.")
    try:
        worker.run(max_iterations=args.max_iterations)
    except KeyboardInterrupt:
        print("\nStopping worker...")
        worker.stop()

    metrics = worker.metrics()
    print("\nWorker metrics:")
    print(f"  succeeded: {metrics.jobs_succeeded}")
    print(f"  failed: {metrics.jobs_failed}")
    print(f"  retried: {metrics.jobs_retried}")
    print(f"  dead_lettered: {metrics.jobs_dead_lettered}")
    print(f"  items_ingested: {metrics.items_ingested}")


def cmd_status(args):
    conn = _get_db_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM ops_job_queue").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as n FROM ops_job_queue GROUP BY status ORDER BY n DESC"
        ).fetchall()
        by_provider = conn.execute(
            "SELECT COALESCE(provider_code, 'unknown') as p, COUNT(*) as n FROM ops_job_queue GROUP BY p ORDER BY n DESC"
        ).fetchall()

        print(f"Total jobs: {total}")
        print("\nBy status:")
        for r in by_status:
            print(f"  {r[0]:20s}  {r[1]}")
        print("\nBy provider:")
        for r in by_provider:
            print(f"  {r[0]:20s}  {r[1]}")
    finally:
        conn.close()


def cmd_cancel(args):
    conn = _get_db_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = conn.execute(
            "UPDATE ops_job_queue SET status = 'cancelled', completed_at = ? WHERE id = ? AND status NOT IN ('succeeded', 'failed', 'cancelled')",
            (now, args.job_id),
        )
        conn.commit()
        if result.rowcount > 0:
            print(f"Job {args.job_id} cancelled.")
        else:
            print(f"Job {args.job_id} not found or already completed.")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Source pipeline CLI — acquisition of historical sources"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("sync-providers", help="Sync provider registry to Supabase")

    enq = sub.add_parser("enqueue", help="Enqueue a job")
    enq.add_argument("--type", required=True, choices=["discovery", "fetch_metadata", "fetch_representations"])
    enq.add_argument("--provider", required=True, help="Provider code")
    enq.add_argument("--query", default="", help="Search query (for discovery)")
    enq.add_argument("--external-id", default="", help="External item ID (for fetch)")
    enq.add_argument("--priority", type=int, default=5)
    enq.add_argument("--max-attempts", type=int, default=5)

    wrk = sub.add_parser("worker", help="Start the worker")
    wrk.add_argument("--max-iterations", type=int, default=0, help="0 = run forever")
    wrk.add_argument("--poll-interval", type=float, default=5.0)
    wrk.add_argument("--concurrency", type=int, default=1)
    wrk.add_argument("--max-attempts", type=int, default=5)

    sub.add_parser("status", help="Show queue status")

    cnl = sub.add_parser("cancel", help="Cancel a job")
    cnl.add_argument("job_id", type=int)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.command == "sync-providers":
        cmd_sync_providers(args)
    elif args.command == "enqueue":
        cmd_enqueue(args)
    elif args.command == "worker":
        cmd_worker(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "cancel":
        cmd_cancel(args)


if __name__ == "__main__":
    main()
