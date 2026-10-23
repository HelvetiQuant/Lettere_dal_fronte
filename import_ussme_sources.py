"""import_ussme_sources.py — Importa metadati fonti USSME (Ufficio Storico Stato Maggiore Esercito).

Fonti importate:
1. L'Esercito Italiano nella Grande Guerra 1915-1918 — 37 tomi su issuu.com
   (metadati curati, deep link per ogni tomo)
2. Dall'Isonzo al Piave — Commissione d'Inchiesta Caporetto (3 voll., 1919)
   su Internet Archive (full text disponibile)
3. Inventario Fondo H-4 (PDF difesa.it)
4. I Reparti d'Assalto (Internet Archive)
5. La Grande Guerra Segreta (musei.difesa.it)
6. Esercito Italiano 1961 (Internet Archive)
7. Archivio Fotografico USSME (esercito.difesa.it)
8. Fondo H-4 archivistico (AUSSME Roma)

Solo metadati e deep link. Nessun file binario viene scaricato.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from typing import Any, Dict, List

from database import get_conn
from archivio_documenti import create_schema, upsert_documenti, SOURCES

# ─── 1. L'Esercito Italiano nella Grande Guerra — 37 tomi su issuu.com ──────

_EIGG_TOMI = [
    # Vol. I — Le forze belligeranti
    {"vol": "I", "tomo": "", "title": "L'Esercito Italiano nella Grande Guerra — Vol. I (Narrazione)",
     "url": "https://issuu.com/rivista.militare1/docs/vol-i_narrazione_doppio-testo_low",
     "desc": "Le forze belligeranti. Narrazione e documenti."},
    {"vol": "I", "tomo": "bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. I tomo bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol-i_narrazione_doppio-testo_low",
     "desc": "Le forze belligeranti. Documenti e tabelle."},
    {"vol": "I", "tomo": "cartine", "title": "L'Esercito Italiano nella Grande Guerra — Vol. I (14 Cartine)",
     "url": "https://issuu.com/rivista.militare1/docs/vol-i_narrazione_doppio-testo_low",
     "desc": "Le forze belligeranti. Cartine e tavole."},
    # Vol. II — Operazioni 1915
    {"vol": "II", "tomo": "1", "title": "L'Esercito Italiano nella Grande Guerra — Vol. II Tomo 1",
     "url": "https://issuu.com/rivista.militare1/docs/vol_ii_tomo_1",
     "desc": "Le operazioni del 1915. Narrazione."},
    {"vol": "II", "tomo": "1 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. II Tomo 1 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_ii_tomo_1_bis",
     "desc": "Le operazioni del 1915. Documenti."},
    {"vol": "II", "tomo": "1 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. II Tomo 1 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_ii_tomo_1_ter",
     "desc": "Le operazioni del 1915. Cartine e tavole."},
    # Vol. III — Operazioni 1916
    {"vol": "III", "tomo": "1", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 1",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_1",
     "desc": "Le operazioni del 1916. Narrazione."},
    {"vol": "III", "tomo": "1 cartine", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 1 (Cartine)",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_1_cartine",
     "desc": "Le operazioni del 1916. Cartine."},
    {"vol": "III", "tomo": "2", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 2",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_2",
     "desc": "Le operazioni del 1916. Narrazione (parte 2)."},
    {"vol": "III", "tomo": "2 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 2 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_2_bis",
     "desc": "Le operazioni del 1916. Documenti."},
    {"vol": "III", "tomo": "2 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 2 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_2_ter",
     "desc": "Le operazioni del 1916. Cartine e tavole."},
    {"vol": "III", "tomo": "3", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 3",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_3",
     "desc": "Le operazioni del 1916. Narrazione (parte 3)."},
    {"vol": "III", "tomo": "3 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 3 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_3_bis",
     "desc": "Le operazioni del 1916. Documenti."},
    {"vol": "III", "tomo": "3 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. III Tomo 3 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iii_tomo_3_ter",
     "desc": "Le operazioni del 1916. Cartine e tavole."},
    # Vol. IV — Operazioni 1917 (CAPORETTO) — 9 tomi
    {"vol": "IV", "tomo": "1", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 1",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_1",
     "desc": "Le operazioni del 1917. Narrazione — dall'Isonzo a Caporetto."},
    {"vol": "IV", "tomo": "1 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 1 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_1_bis",
     "desc": "Le operazioni del 1917. Documenti."},
    {"vol": "IV", "tomo": "1 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 1 ter (Cartine)",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_1_ter_cartine_tavole",
     "desc": "Le operazioni del 1917. Cartine e tavole."},
    {"vol": "IV", "tomo": "2", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 2",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_2",
     "desc": "Le operazioni del 1917. Narrazione — Caporetto e ripiegamento."},
    {"vol": "IV", "tomo": "2 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 2 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_2_bis",
     "desc": "Le operazioni del 1917. Documenti — Caporetto."},
    {"vol": "IV", "tomo": "2 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 2 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_2_ter",
     "desc": "Le operazioni del 1917. Cartine — Caporetto e ripiegamento."},
    {"vol": "IV", "tomo": "3", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 3",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_3",
     "desc": "Le operazioni del 1917. Narrazione — fine del ripiegamento, linea del Piave."},
    {"vol": "IV", "tomo": "3 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 3 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_3_bis",
     "desc": "Le operazioni del 1917. Documenti — linea del Piave."},
    {"vol": "IV", "tomo": "3 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. IV Tomo 3 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_iv_tomo_3_ter",
     "desc": "Le operazioni del 1917. Cartine — Piave e Grappa."},
    # Vol. V — Operazioni 1918
    {"vol": "V", "tomo": "1", "title": "L'Esercito Italiano nella Grande Guerra — Vol. V Tomo 1",
     "url": "https://issuu.com/rivista.militare1/docs/vol_v_tomo_1_narrazione-testo-low",
     "desc": "Le operazioni del 1918. Gli avvenimenti dal gennaio al giugno."},
    {"vol": "V", "tomo": "1 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. V Tomo 1 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_v_tomo_1_bis",
     "desc": "Le operazioni del 1918. Documenti (gen-giu)."},
    {"vol": "V", "tomo": "1 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. V Tomo 1 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_v_tomo_1_ter",
     "desc": "Le operazioni del 1918. Cartine (gen-giu)."},
    {"vol": "V", "tomo": "2", "title": "L'Esercito Italiano nella Grande Guerra — Vol. V Tomo 2",
     "url": "https://issuu.com/rivista.militare1/docs/vol_v_tomo_2",
     "desc": "Le operazioni del 1918. Gli avvenimenti da luglio a dicembre."},
    {"vol": "V", "tomo": "2 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. V Tomo 2 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_v_tomo_2_bis",
     "desc": "Le operazioni del 1918. Documenti (lug-dic)."},
    {"vol": "V", "tomo": "2 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. V Tomo 2 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_v_tomo_2_ter",
     "desc": "Le operazioni del 1918. Cartine (lug-dic)."},
    # Vol. VI — Istruzioni tattiche
    {"vol": "VI", "tomo": "1", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VI Tomo 1",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vi_tomo_1",
     "desc": "Istruzioni tattiche. Narrazione."},
    {"vol": "VI", "tomo": "2", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VI Tomo 2",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vi_tomo_2",
     "desc": "Istruzioni tattiche. Documenti."},
    {"vol": "VI", "tomo": "appendice", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VI Appendice",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vi_appendice",
     "desc": "Istruzioni tattiche. Appendice."},
    # Vol. VII — Operazioni fuori dal territorio nazionale
    {"vol": "VII", "tomo": "1", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 1",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_1",
     "desc": "Operazioni fuori dal territorio nazionale. Albania, Macedonia, Medio Oriente."},
    {"vol": "VII", "tomo": "2", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 2",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_2",
     "desc": "Operazioni fuori dal territorio nazionale. Documenti."},
    {"vol": "VII", "tomo": "2 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 2 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_2_bis",
     "desc": "Operazioni fuori dal territorio nazionale. Documenti (parte 2)."},
    {"vol": "VII", "tomo": "2 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 2 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_2_ter",
     "desc": "Operazioni fuori dal territorio nazionale. Cartine."},
    {"vol": "VII", "tomo": "3", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 3",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_3",
     "desc": "Operazioni fuori dal territorio nazionale. Narrazione (parte 3)."},
    {"vol": "VII", "tomo": "3 bis", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 3 bis",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_3_bis",
     "desc": "Operazioni fuori dal territorio nazionale. Documenti (parte 3)."},
    {"vol": "VII", "tomo": "3 ter", "title": "L'Esercito Italiano nella Grande Guerra — Vol. VII Tomo 3 ter",
     "url": "https://issuu.com/rivista.militare1/docs/vol_vii_tomo_3_ter",
     "desc": "Operazioni fuori dal territorio nazionale. Cartine (parte 3)."},
]

# ─── 2. Dall'Isonzo al Piave — Commissione d'Inchiesta (Internet Archive) ──

_COMMISSIONE_RECORDS = [
    {
        "title": "Dall'Isonzo al Piave — Vol. II (Relazione Commissione d'Inchiesta, 1919)",
        "url": "https://archive.org/details/dallisonzoalpiav02ital",
        "desc": "Volume II della Relazione della Commissione d'Inchiesta (R.D. 12 gennaio 1918 n. 35). "
                "Analisi delle cause del ripiegamento e individuazione delle responsabilità militari. "
                "Full text disponibile (OCR).",
        "year_start": 1919, "year_end": 1919,
    },
    {
        "title": "Inventario del fondo H-4 — Commissione d'Inchiesta Caporetto (2015)",
        "url": "https://archive.org/details/50-inventario-del-fondo-h-4",
        "desc": "Inventario analitico del fondo archivistico H-4. A cura di Alessandro Gionfrida (USSME). "
                "Pubblicato dall'Ufficio Storico del Stato Maggiore della Difesa in collaborazione con USSME. "
                "ISBN: 9788898185191.",
        "year_start": 2015, "year_end": 2015,
    },
]

# ─── 3. Altre pubblicazioni USSME (Internet Archive + musei.difesa.it) ──────

_OTHER_USSME = [
    {
        "title": "I Reparti d'Assalto Italiani nella Grande Guerra (1915-18)",
        "url": "https://archive.org/details/i-reparti-d-assalto-italiani-nella-grande-guerra-1915-18",
        "desc": "Studio USSME di Basilio Di Martino e Filippo Cappellano (2007). "
                "Arditi, Fiamme Nere/Verdi/Cremisi. Da Caporetto a Vittorio Veneto. "
                "Internet Archive (streaming).",
        "year_start": 2007, "year_end": 2007,
        "creator": "Basilio Di Martino, Filippo Cappellano",
    },
    {
        "title": "L'Esercito Italiano dal Tricolore al 1° Centenario (1961)",
        "url": "https://archive.org/details/EsercitoItaliano1961",
        "desc": "Storia generale dell'Esercito Italiano 1861-1961. Cap. X: La Grande Guerra. "
                "Full text su Internet Archive.",
        "year_start": 1961, "year_end": 1961,
        "creator": "Ufficio Storico Stato Maggiore Esercito",
    },
    {
        "title": "La Grande Guerra segreta sul fronte Italiano (1915-1918) — Communication Intelligence",
        "url": "https://musei.difesa.it/allegati/La%20Grande%20Guerra%20segreta%20sul%20fronte%20Italiano%20(1915-1918)/",
        "desc": "Intercettazioni telefoniche, radio-telegrafiche, radiogoniometria. "
                "Previsioni dell'offensiva di Caporetto dal 7 ottobre 1917. "
                "Fonti: AUSSME fondo E-2, H-4. Consultabile su musei.difesa.it.",
        "year_start": 2014, "year_end": 2014,
        "creator": "Ufficio Storico Stato Maggiore della Difesa",
    },
    {
        "title": "Inventario del fondo H-4 — PDF (difesa.it)",
        "url": "https://www.difesa.it/assets/allegati/43015/50_inventario_del_fondo_h4.pdf",
        "desc": "PDF dell'inventario analitico del fondo H-4 Commissione d'Inchiesta Caporetto. "
                "ISBN: 9788898185191. Ministero della Difesa, 2015.",
        "year_start": 2015, "year_end": 2015,
        "creator": "Alessandro Gionfrida",
    },
]


def _build_eigg_rows() -> List[Dict[str, Any]]:
    """Build rows for L'Esercito Italiano nella Grande Guerra tomi."""
    rows = []
    for t in _EIGG_TOMI:
        vol_label = f"Vol. {t['vol']}"
        tomo_label = f"Tomo {t['tomo']}" if t["tomo"] else "Tomo unico"
        rows.append({
            "provider": "USSME",
            "external_id": f"eigg_vol{t['vol']}_tomo{t['tomo'] or '1'}",
            "doc_type": "pubblicazione_storica",
            "title": t["title"],
            "description": t["desc"],
            "source_url": t["url"],
            "rights": "Copyright USSME — consultazione online gratuita su issuu.com",
            "language": "it",
            "war": "WWI",
            "provider_collection": f"L'Esercito Italiano nella Grande Guerra — {vol_label}",
            "raw_json": json.dumps({"volume": t["vol"], "tomo": t["tomo"], "platform": "issuu"}, ensure_ascii=False),
        })
    return rows


def _build_commissione_rows() -> List[Dict[str, Any]]:
    """Build rows for Commissione d'Inchiesta records."""
    rows = []
    for r in _COMMISSIONE_RECORDS:
        rows.append({
            "provider": "USSME",
            "external_id": r["url"],
            "doc_type": "relazione_ufficiale",
            "title": r["title"],
            "description": r["desc"],
            "source_url": r["url"],
            "rights": "Pubblico dominio (1919)" if r["year_start"] == 1919 else "Copyright Ministero della Difesa",
            "language": "it",
            "war": "WWI",
            "year_start": r.get("year_start"),
            "year_end": r.get("year_end"),
            "provider_collection": "Commissione d'Inchiesta Caporetto — Fondo H-4",
            "raw_json": json.dumps({"source": "internet_archive", "type": "commissione_inchiesta"}, ensure_ascii=False),
        })
    return rows


def _build_other_rows() -> List[Dict[str, Any]]:
    """Build rows for other USSME publications."""
    rows = []
    for r in _OTHER_USSME:
        rows.append({
            "provider": "USSME" if "musei.difesa" not in r["url"] and "difesa.it" not in r["url"] else "USSME-SMD",
            "external_id": r["url"],
            "doc_type": "monografia",
            "title": r["title"],
            "description": r["desc"],
            "creator": r.get("creator"),
            "source_url": r["url"],
            "rights": "Copyright USSME" if r["year_start"] < 2010 else "Copyright Ministero della Difesa",
            "language": "it",
            "war": "WWI",
            "year_start": r.get("year_start"),
            "year_end": r.get("year_end"),
            "provider_collection": "Pubblicazioni USSME",
            "raw_json": json.dumps({"source": "internet_archive" if "archive.org" in r["url"] else "difesa.it"}, ensure_ascii=False),
        })
    return rows


def main() -> int:
    print("=" * 70)
    print("IMPORT USSME — Ufficio Storico Stato Maggiore Esercito")
    print("=" * 70)

    conn = get_conn()
    try:
        create_schema(conn)

        # 1. Seed collection-level SOURCES (includes USSME entries)
        print("\n[1/4] Seeding SOURCES (collection level)...")
        from archivio_documenti import seed_sources
        n_sources = seed_sources()
        print(f"   → {n_sources} collection-level records upserted")

        # 2. Import EIGG tomi (37 volumes)
        print("\n[2/4] Importing L'Esercito Italiano nella Grande Guerra (37 tomi)...")
        eigg_rows = _build_eigg_rows()
        n_eigg = upsert_documenti(conn, eigg_rows)
        print(f"   → {n_eigg} tomi upserted")

        # 3. Import Commissione d'Inchiesta records
        print("\n[3/4] Importing Commissione d'Inchiesta Caporetto records...")
        comm_rows = _build_commissione_rows()
        n_comm = upsert_documenti(conn, comm_rows)
        print(f"   → {n_comm} records upserted")

        # 4. Import other USSME publications
        print("\n[4/4] Importing other USSME publications...")
        other_rows = _build_other_rows()
        n_other = upsert_documenti(conn, other_rows)
        print(f"   → {n_other} records upserted")

        total = n_eigg + n_comm + n_other
        print(f"\n{'=' * 70}")
        print(f"TOTAL: {total} USSME document records upserted")
        print(f"{'=' * 70}")

        # Verify
        cursor = conn.execute(
            "SELECT COUNT(*) FROM archivio_documenti WHERE provider LIKE 'USSME%'"
        )
        count = cursor.fetchone()[0]
        print(f"\nVerification: {count} USSME records in archivio_documenti")

        # Show breakdown by doc_type
        cursor = conn.execute(
            "SELECT doc_type, COUNT(*) FROM archivio_documenti WHERE provider LIKE 'USSME%' "
            "GROUP BY doc_type ORDER BY COUNT(*) DESC"
        )
        print("\nBreakdown by doc_type:")
        for row in cursor:
            print(f"  {row[0]}: {row[1]}")

        return total
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
