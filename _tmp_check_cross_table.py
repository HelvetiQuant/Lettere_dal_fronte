"""Check cross-table matches for the 5 names and what military fields each table has."""
import sqlite3, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

db = sqlite3.connect('imi_internati.db')
db.row_factory = sqlite3.Row

names = [
    ("PASTRE", "LUIGI GIOVANNI", "lebi_records"),
    ("MAVONE", "LUIGI", "internati"),
    ("BURBA", "LUIGI DI GIACOMO", "caduti_ministero"),
    ("LIMBERTI", "FRANCESCO", "caduti_albooro"),
    ("ERRERA", "MARIO", "decorati_nastroazzurro"),
]

# Check all person tables for each name
person_tables = [
    ("lebi_records", "cognome", "nome"),
    ("internati", "cognome", "nome"),
    ("caduti_ministero", "cognome", "nome"),
    ("caduti_albooro", "nominativo", None),
    ("decorati_nastroazzurro", "cognome", "nome"),
]

for cognome, nome, src_table in names:
    print(f"\n{'='*80}")
    print(f"Target: {cognome} {nome} (originally from {src_table})")
    print(f"{'='*80}")
    
    for table, ccol, ncol in person_tables:
        if ncol:
            rows = db.execute(f"SELECT * FROM {table} WHERE {ccol} = ? AND nome LIKE ? LIMIT 2", (cognome, f"%{nome[:4]}%")).fetchall()
        else:
            rows = db.execute(f"SELECT * FROM {table} WHERE {ccol} LIKE ? LIMIT 2", (f"%{cognome}%",)).fetchall()
        
        if rows:
            print(f"\n  Found in {table}: {len(rows)} rows")
            for r in rows:
                # Print military-relevant fields
                military_fields = []
                for k in r.keys():
                    if k in ('grado', 'reparto', 'military_unit', 'unit', 'arma', 'luogo_cattura', 'data_cattura', 'luogo_internamento', 'matricola', 'arbeitskommando', 'mansione', 'sorte', 'data_decesso', 'nazione_decesso', 'luogo_morte', 'causa_morte', 'anno_morte', 'luogo_sepoltura', 'decorazione', 'anno_decorazione') and r[k]:
                        military_fields.append(f"    {k} = {r[k]}")
                if military_fields:
                    print(f"    Military data:")
                    for mf in military_fields:
                        print(mf)
                else:
                    # Print all non-empty fields
                    all_fields = [f"    {k} = {r[k]}" for k in r.keys() if r[k] and k not in ('id','source_id','elaborato_il','raw_text','documenti')]
                    print(f"    All non-empty fields:")
                    for af in all_fields[:10]:
                        print(af)

# Check what military fields each table schema maps
print(f"\n{'='*80}")
print("TABLE MILITARY FIELD AVAILABILITY")
print(f"{'='*80}")

for table, ccol, ncol in person_tables:
    cols = [r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
    military_cols = [c for c in cols if c in ('grado','reparto','military_unit','unit','arma','luogo_cattura','data_cattura','luogo_internamento','matricola','arbeitskommando','mansione','sorte','data','data_decesso','nazione_decesso','luogo_morte','causa_morte','anno_morte','luogo_sepoltura','decorazione','anno_decorazione','tipo_decorazione','military_branch','decoration_type','decoration_year')]
    print(f"  {table}: military fields = {military_cols}")

db.close()
