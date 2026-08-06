"""Check v2 relations, data_corrections, entity_variants counts."""
import sqlite3

conn = sqlite3.connect("imi_internati.db")
conn.row_factory = sqlite3.Row

print("=== V2 RELATIONS ===")
try:
    print("Total:", conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0])
    for r in conn.execute("SELECT status, COUNT(*) as n FROM relations GROUP BY status ORDER BY n DESC").fetchall():
        print(f"  {r['status']:20s} {r['n']:>8}")
    for r in conn.execute("SELECT relation_type, COUNT(*) as n FROM relations GROUP BY relation_type ORDER BY n DESC").fetchall():
        print(f"  {r['relation_type']:30s} {r['n']:>8}")
except Exception as e:
    print(f"Table not found: {e}")

print("\n=== RESOURCE_REGISTRY ===")
try:
    print("Total:", conn.execute("SELECT COUNT(*) FROM resource_registry").fetchone()[0])
    for r in conn.execute("SELECT resource_kind, COUNT(*) as n FROM resource_registry GROUP BY resource_kind ORDER BY n DESC").fetchall():
        print(f"  {r['resource_kind']:20s} {r['n']:>8}")
except Exception as e:
    print(f"Table not found: {e}")

print("\n=== DATA_CORRECTIONS ===")
try:
    print("Count:", conn.execute("SELECT COUNT(*) FROM data_corrections").fetchone()[0])
    for r in conn.execute("SELECT field_name, COUNT(*) as n FROM data_corrections GROUP BY field_name").fetchall():
        print(f"  {r['field_name']:20s} {r['n']:>8}")
except Exception as e:
    print(f"Table not found: {e}")

print("\n=== ENTITY_VARIANTS ===")
try:
    print("Count:", conn.execute("SELECT COUNT(*) FROM entity_variants").fetchone()[0])
except Exception as e:
    print(f"Table not found: {e}")

print("\n=== TABLE SIZES ===")
for t in ["internati", "caduti_albooro", "decorati_nastroazzurro", "caduti_cwgc", "caduti_ministero", "fonti_indice", "archivio_documenti"]:
    try:
        c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:30s} {c:>8}")
    except:
        print(f"  {t:30s} NOT FOUND")

print("\n=== PIPELINE_RUNS ===")
try:
    for r in conn.execute("SELECT pipeline_name, status, algorithm_version, COUNT(*) as n FROM pipeline_runs GROUP BY pipeline_name, status, algorithm_version").fetchall():
        print(f"  {r['pipeline_name']:20s} {r['status']:12s} v{r['algorithm_version']:10s} {r['n']:>4}")
except Exception as e:
    print(f"Table not found: {e}")

print("\n=== LEGACY_RELATION_QUARANTINE ===")
try:
    print("Count:", conn.execute("SELECT COUNT(*) FROM legacy_relation_quarantine").fetchone()[0])
except Exception as e:
    print(f"Table not found: {e}")

conn.close()
