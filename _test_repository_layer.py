"""Test repository_layer SupabaseBackend upsert and get."""
import sys
from repository_layer import SupabaseBackend, Repository, make_stable_id

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

backend = SupabaseBackend()

sid = make_stable_id("repo", "test-repo-layer")
repo = Repository(
    stable_id=sid,
    name="Repository Layer Test",
    country="IT",
    website_url="https://example.org",
    authority_score=0.7,
)

print("Upserting repository...")
r = backend.upsert_repository(repo)
print("Result:", r)

if "error" in r:
    print("FAILED")
    sys.exit(1)

print("\nFetching repository...")
results = backend._get("archive.repositories", f"stable_id=eq.{sid}&limit=1")
print("Found:", len(results))
if results:
    print("Name:", results[0]["name"])

print("\nRepository layer OK")
