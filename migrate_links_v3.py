"""V3 Idempotent Migration: Re-evaluate existing links with authority-aware logic.

This script:
1. Re-evaluates all existing record_links with the V3 LinkDecisionEngine.
2. Re-evaluates all existing event_links with the V3 LinkDecisionEngine.
3. Moves name-only links (no second identifier) to needs_review.
4. Rejects links with temporal conflicts on official dates.
5. Does NOT delete any data — only updates status, needs_review, and metadata.

Idempotent: can be run multiple times. Links already evaluated with the
current rule_version are skipped.

Usage:
    python migrate_links_v3.py --dry-run   # audit only
    python migrate_links_v3.py --execute   # apply changes
"""
import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _gen_record_links_v3 import run_re_evaluate as reeval_record_links
from _gen_event_links_v3 import run_re_evaluate as reeval_event_links


def main():
    parser = argparse.ArgumentParser(description="V3 Link Migration (idempotent)")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no changes")
    parser.add_argument("--execute", action="store_true", help="Apply changes to DB")
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 70)
    print("V3 LINK MIGRATION — AUTHORITY-AWARE RE-EVALUATION")
    print("=" * 70)
    print(f"Mode: {'DRY RUN (audit only)' if dry_run else 'EXECUTE (apply changes)'}")
    print()

    # ─── Step 1: Re-evaluate record_links ────────────────────────────────
    print("STEP 1: Re-evaluating record_links")
    print("-" * 40)
    t0 = time.time()
    reeval_record_links(dry_run=dry_run)
    print(f"  Elapsed: {time.time()-t0:.1f}s")

    # ─── Step 2: Re-evaluate event_links ─────────────────────────────────
    print("\nSTEP 2: Re-evaluating event_links")
    print("-" * 40)
    t0 = time.time()
    reeval_event_links(dry_run=dry_run)
    print(f"  Elapsed: {time.time()-t0:.1f}s")

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    if dry_run:
        print("This was a DRY RUN. To apply changes, run with --execute")
    else:
        print("Changes have been applied to the database.")
        print("No data was deleted. Links were only re-classified.")


if __name__ == "__main__":
    main()
