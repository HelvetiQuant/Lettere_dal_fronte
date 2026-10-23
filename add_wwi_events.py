"""Aggiunge nuovi eventi WWI al database eventi_1gm.db.

Eventi mancanti identificati:
- Battaglie e operazioni: dall'entrata in guerra all'armistizio
- Spostamenti di truppe e ripiegamenti
- Internamento militare e civile (IMI WWI, prigionieri in Austria-Ungheria/Germania)
- Eventi geopolitici e territoriali

Idempotente: usa INSERT OR IGNORE su nome UNIQUE.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

EDB = Path(__file__).parent / "eventi_1gm.db"

NEW_EVENTS = [
    # --- Battaglie e operazioni ---
    {
        "nome": "Entrata in guerra dell'Italia",
        "data_inizio": "1915-05-24",
        "data_fine": "1915-05-24",
        "luogo": "Italia, confine italo-austriaco",
        "aliases": ["Dichiarazione di guerra", "24 maggio 1915", "Salto in guerra"],
        "keywords": ["entrata in guerra", "dichiarazione", "Triplice Alleanza", "Triplice Intesa", "neutralità", "Salandra", "Sonnino"],
        "descrizione": "L'Italia dichiara guerra all'Austria-Ungheria il 24 maggio 1915, abbandonando la Triplice Alleanza e unendosi alla Triplice Intesa. Inizio delle operazioni sul fronte italiano.",
        "conflict": "WWI",
        "event_type": "evento_politico_militare",
        "parent_event_id": None,
        "stable_id": "evt_0038",
    },
    {
        "nome": "Prima battaglia dell'Isonzo",
        "data_inizio": "1915-06-23",
        "data_fine": "1915-07-07",
        "luogo": "Fronte Isonzo, Carso",
        "aliases": ["Isonzo 1", "First Battle of the Isonzo"],
        "keywords": ["Isonzo", "Carso", "Gorizia", "Cadorna", "trincea", "offensiva"],
        "descrizione": "Prima delle dodici battaglie dell'Isonzo. Offensiva italiana contro le posizioni austro-ungariche sul fiume Isonzo e sul Carso. Esiti limitati nonostante la superiorità numerica.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0039",
    },
    {
        "nome": "Seconda battaglia dell'Isonzo",
        "data_inizio": "1915-07-18",
        "data_fine": "1915-08-03",
        "luogo": "Fronte Isonzo, Carso, Gorizia",
        "aliases": ["Isonzo 2", "Second Battle of the Isonzo"],
        "keywords": ["Isonzo", "Carso", "Gorizia", "Sabotino", "San Michele", "Cadorna"],
        "descrizione": "Seconda offensiva italiana sull'Isonzo. Attacchi sul Sabotino, San Michele e Carso. Conquiste territoriali minime, perdite elevate.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0040",
    },
    {
        "nome": "Terza battaglia dell'Isonzo",
        "data_inizio": "1915-10-18",
        "data_fine": "1915-11-04",
        "luogo": "Fronte Isonzo, Gorizia, Carso",
        "aliases": ["Isonzo 3", "Third Battle of the Isonzo"],
        "keywords": ["Isonzo", "Gorizia", "San Michele", "Oslavia", "Cadorna"],
        "descrizione": "Terza offensiva sull'Isonzo con obiettivo Gorizia. Attacchi frontali su San Michele e Oslavia. Progresso limitato, perdite significative.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0041",
    },
    {
        "nome": "Quarta battaglia dell'Isonzo",
        "data_inizio": "1915-11-10",
        "data_fine": "1915-12-02",
        "luogo": "Fronte Isonzo, Gorizia, Carso",
        "aliases": ["Isonzo 4", "Fourth Battle of the Isonzo"],
        "keywords": ["Isonzo", "Gorizia", "San Michele", "Cadorna", "inverno"],
        "descrizione": "Quarta offensiva sull'Isonzo, condotta in condizioni invernali. Attacchi su San Michele e quota 144. Esiti marginali.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0042",
    },
    {
        "nome": "Quinta battaglia dell'Isonzo",
        "data_inizio": "1916-03-09",
        "data_fine": "1916-03-16",
        "luogo": "Fronte Isonzo, Gorizia, Carso",
        "aliases": ["Isonzo 5", "Fifth Battle of the Isonzo"],
        "keywords": ["Isonzo", "Gorizia", "Sabotino", "Cadorna", "offensiva di primavera"],
        "descrizione": "Quinta offensiva sull'Isonzo, breve e inconcludente. Attacchi coordinati su Sabotino e San Michele. Sospesa per la necessità di rinforzare il fronte settentrionale.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0043",
    },
    {
        "nome": "Sesta battaglia dell'Isonzo",
        "data_inizio": "1916-08-06",
        "data_fine": "1916-08-17",
        "luogo": "Fronte Isonzo, Gorizia",
        "aliases": ["Isonzo 6", "Sixth Battle of the Isonzo", "Conquista di Gorizia"],
        "keywords": ["Isonzo", "Gorizia", "Sabotino", "San Michele", "conquista", "Cadorna"],
        "descrizione": "Sesta offensiva: conquista di Gorizia, primo successo territoriale significativo italiano. Attacchi coordinati su Sabotino, San Michele e Podgora. Perdite elevate ma guadagno strategico.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0044",
    },
    {
        "nome": "Settima battaglia dell'Isonzo",
        "data_inizio": "1916-09-14",
        "data_fine": "1916-09-17",
        "luogo": "Fronte Isonzo, Carso",
        "aliases": ["Isonzo 7", "Seventh Battle of the Isonzo"],
        "keywords": ["Isonzo", "Carso", "Nova Vas", "Cadorna"],
        "descrizione": "Settima offensiva, breve spinta sul Carso nei pressi di Nova Vas. Esiti limitati.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0045",
    },
    {
        "nome": "Ottava battaglia dell'Isonzo",
        "data_inizio": "1916-10-10",
        "data_fine": "1916-10-12",
        "luogo": "Fronte Isonzo, Carso",
        "aliases": ["Isonzo 8", "Eighth Battle of the Isonzo"],
        "keywords": ["Isonzo", "Carso", "Vallone", "Cadorna"],
        "descrizione": "Ottava offensiva sul Carso, attacchi verso il Vallone. Progresso minimo, perdite italiane e austro-ungariche elevate.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0046",
    },
    {
        "nome": "Nona battaglia dell'Isonzo",
        "data_inizio": "1916-11-01",
        "data_fine": "1916-11-04",
        "luogo": "Fronte Isonzo, Carso",
        "aliases": ["Isonzo 9", "Ninth Battle of the Isonzo"],
        "keywords": ["Isonzo", "Carso", "San Marco", "Cadorna"],
        "descrizione": "Nona offensiva sul Carso, ultimi scontri dell'anno 1916. Attacchi verso San Marco e quota 144. Esiti marginali.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0047",
    },
    {
        "nome": "Decima battaglia dell'Isonzo",
        "data_inizio": "1917-05-12",
        "data_fine": "1917-06-08",
        "luogo": "Fronte Isonzo, Carso, Bainsizza",
        "aliases": ["Isonzo 10", "Tenth Battle of the Isonzo"],
        "keywords": ["Isonzo", "Carso", "Bainsizza", "Jamiano", "Cadorna", "offensiva primaverile"],
        "descrizione": "Decima offensiva: attacchi su tutto il fronte Isonzo-Carso. Conquiste parziali sul Carso e verso Bainsizza. Uso intensivo di artiglieria. Perdite elevatissime.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0048",
    },
    {
        "nome": "Undicesima battaglia dell'Isonzo",
        "data_inizio": "1917-08-18",
        "data_fine": "1917-09-12",
        "luogo": "Fronte Isonzo, Bainsizza, Carso",
        "aliases": ["Isonzo 11", "Eleventh Battle of the Isonzo", "Bainsizza"],
        "keywords": ["Isonzo", "Bainsizza", "Santa Croce", "San Gabriele", "Cadorna", "Boroević"],
        "descrizione": "Undicesima offensiva: conquista dell'altopiano della Bainsizza e attacchi al Monte San Gabriele. Massimo sforzo offensivo italiano prima di Caporetto. Perdite enormi da entrambe le parti.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0017",
        "stable_id": "evt_0049",
    },
    {
        "nome": "Battaglia degli Altipiani",
        "data_inizio": "1916-05-15",
        "data_fine": "1916-06-16",
        "luogo": "Altopiano dei Sette Comuni, Trentino",
        "aliases": ["Offensiva di Primavera", "Strafexpedition", "Spedizione punitiva"],
        "keywords": ["Altipiani", "Asiago", "Trentino", "Strafexpedition", "Conrad", "Pasubio", "offensiva austro-ungarica"],
        "descrizione": "Offensiva austro-ungarica (Strafexpedition) dal Trentino verso gli Altipiani dei Sette Comuni. Obiettivo: sfondare il fronte italiano e isolare le armate sull'Isonzo. Fermata dall'esercito italiano dopo avanzata iniziale.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0021",
        "stable_id": "evt_0050",
    },
    {
        "nome": "Battaglia del Monte Ortigara",
        "data_inizio": "1917-06-10",
        "data_fine": "1917-06-25",
        "luogo": "Altopiano di Asiago, Monte Ortigara",
        "aliases": ["Ortigara", "Offensiva di giugno", "Monte Ortigara"],
        "keywords": ["Ortigara", "Asiago", "Altipiani", "contraffensiva", "Alpini", "Marmolada"],
        "descrizione": "Offensiva italiana sull'altopiano di Asiago per riconquistare posizioni perse nella Strafexpedition. Attacchi al Monte Ortigara con Alpini. Conquista temporanea, poi persa per contrattacco austro-ungarico.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0021",
        "stable_id": "evt_0051",
    },
    # --- Spostamenti e ripiegamenti ---
    {
        "nome": "Ripiegamento dal Carso al Piave",
        "data_inizio": "1917-10-24",
        "data_fine": "1917-11-12",
        "luogo": "Dal Carso al fiume Piave",
        "aliases": ["Ritirata dopo Caporetto", "Ripiegamento strategico", "Ritirata al Piave"],
        "keywords": ["ripiegamento", "ritirata", "Piave", "Caporetto", "Tagliamento", "Livenza"],
        "descrizione": "Ripiegamento generale dell'esercito italiano dal fronte Isonzo-Carso alla linea del Piave dopo la sfondamento di Caporetto. Ritirata di circa 150 km con perdite di uomini, materiali e territorio.",
        "conflict": "WWI",
        "event_type": "spostamento",
        "parent_event_id": "evt_0016",
        "stable_id": "evt_0052",
    },
    {
        "nome": "Riorganizzazione dell'esercito dopo Caporetto",
        "data_inizio": "1917-11-12",
        "data_fine": "1917-12-31",
        "luogo": "Linea del Piave, Montello, Grappa",
        "aliases": ["Riorganizzazione Diaz", "Sostituzione Cadorna", "Riassetto"],
        "keywords": ["Diaz", "Cadorna", "riorganizzazione", "Piave", "Grappa", "Montello", "morale", "comando"],
        "descrizione": "Dopo Caporetto, Diaz sostituisce Cadorna. Riorganizzazione del comando, ricostituzione delle unità disblocate, rafforzamento del morale e della disciplina. Preparazione alla difesa della linea Piave-Grappa.",
        "conflict": "WWI",
        "event_type": "riorganizzazione",
        "parent_event_id": "evt_0016",
        "stable_id": "evt_0053",
    },
    {
        "nome": "Prima battaglia del Piave",
        "data_inizio": "1917-11-13",
        "data_fine": "1917-11-23",
        "luogo": "Fiume Piave, Montello",
        "aliases": ["Piave 1", "Difesa del Piave", "Prima battaglia difensiva del Piave"],
        "keywords": ["Piave", "Montello", "Diaz", "difensiva", "Boroević", "alluvione"],
        "descrizione": "Prima battaglia difensiva del Piave. L'esercito austro-ungarico tenta di sfondare la linea del Piave dopo Caporetto. Resistenza italiana e piena del fiume fermano l'offensiva.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0019",
        "stable_id": "evt_0054",
    },
    {
        "nome": "Seconda battaglia del Piave",
        "data_inizio": "1918-06-15",
        "data_fine": "1918-06-23",
        "luogo": "Fiume Piave, Montello, Grappa",
        "aliases": ["Piave 2", "Battaglia del Solstizio", "Seconda battaglia difensiva del Piave"],
        "keywords": ["Piave", "Solstizio", "Montello", "Grappa", "Diaz", "Boroević", "contrattacco"],
        "descrizione": "Ultima grande offensiva austro-ungarica sul fronte italiano (Battaglia del Solstizio). Attacchi su Piave e Grappa fermati, poi contrattacco italiano. Punto di svolta: l'esercito italiano passa all'offensiva.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0019",
        "stable_id": "evt_0055",
    },
    # --- Internamento e prigionia WWI ---
    {
        "nome": "Internamento militari italiani in Austria-Ungheria (WWI)",
        "data_inizio": "1915-05-24",
        "data_fine": "1918-11-04",
        "luogo": "Campi di prigionia Austria-Ungheria, Germania",
        "aliases": ["Prigionia WWI", "Internati WWI", "Prigionieri di guerra italiani WWI"],
        "keywords": ["internamento", "prigionia", "campo", "Austria", "Ungheria", "Germania", "prigioniero", "WWI", "Rastatt", "Mauthausen", "Sigmundsherberg"],
        "descrizione": "Internamento dei soldati italiani catturati durante la Prima Guerra Mondiale. Circa 600.000 prigionieri di guerra italiani nei campi austro-ungarici e tedeschi. Condizioni durissime, mortalità elevata per fame, malattie e lavoro forzato.",
        "conflict": "WWI",
        "event_type": "internamento",
        "parent_event_id": "evt_0025",
        "stable_id": "evt_0056",
    },
    {
        "nome": "Internamento civile irredenti",
        "data_inizio": "1915-05-24",
        "data_fine": "1918-11-04",
        "luogo": "Trentino, Trieste, Istria, Dalmazia, campi internamento Austria",
        "aliases": ["Irredenti internati", "Internamento civile WWI", "Profughi irredenti"],
        "keywords": ["irredenti", "internamento civile", "Trentino", "Trieste", "Istria", "Katzenau", "Wagna", "profughi"],
        "descrizione": "Internamento di civili italiani dalle terre irredente (Trentino, Trieste, Istria) sospettati di irredentismo. Campi di internamento in Austria (Katzenau, Wagna). Decine di migliaia di internati civili.",
        "conflict": "WWI",
        "event_type": "internamento",
        "parent_event_id": "evt_0025",
        "stable_id": "evt_0057",
    },
    # --- Eventi geopolitici ---
    {
        "nome": "Patto di Londra",
        "data_inizio": "1915-04-26",
        "data_fine": "1915-04-26",
        "luogo": "Londra, Regno Unito",
        "aliases": ["Trattato di Londra", "London Pact", "Patto di Londra 1915"],
        "keywords": ["Londra", "trattato", "Triplice Intesa", "irredentismo", "Trento", "Trieste", "Dalmazia", "Salandra", "Sonnino"],
        "descrizione": "Trattato segreto con cui l'Italia si impegna a entrare in guerra a fianco della Triplice Intesa in cambio di territori (Trentino, Trieste, Istria, Dalmazia). Base diplomatica dell'entrata in guerra italiana.",
        "conflict": "WWI",
        "event_type": "evento_politico",
        "parent_event_id": None,
        "stable_id": "evt_0058",
    },
    {
        "nome": "Armistizio di Villa Giusti",
        "data_inizio": "1918-11-04",
        "data_fine": "1918-11-04",
        "luogo": "Padova, Villa Giusti",
        "aliases": ["Armistizio di Padova", "Villa Giusti", "4 novembre 1918"],
        "keywords": ["armistizio", "Villa Giusti", "Padova", "4 novembre", "Austria-Ungheria", "Diaz", "fine guerra"],
        "descrizione": "Armistizio tra Italia e Austria-Ungheria firmato a Villa Giusti (Padova) il 3 novembre, entrato in vigore il 4 novembre 1918. Fine delle ostilità sul fronte italiano. L'Austria-Ungheria cessa di esistere come potenza belligerante.",
        "conflict": "WWI",
        "event_type": "evento_politico_militare",
        "parent_event_id": None,
        "stable_id": "evt_0059",
    },
    {
        "nome": "Vittoria mutilata",
        "data_inizio": "1919-01-01",
        "data_fine": "1919-09-12",
        "luogo": "Parigi, Italia",
        "aliases": ["Vittoria mutilata", "Conferenza di pace di Parigi", "D'Annunzio", "Fiume"],
        "keywords": ["vittoria mutilata", "D'Annunzio", "Fiume", "Parigi", "Sonnino", "Orlando", "Trattato di Saint-Germain", "irredentismo"],
        "descrizione": "Scontento italiano per i risultati della Conferenza di pace di Parigi: nonostante il Patto di Londra, l'Italia non ottiene tutti i territori promessi (Dalmazia, Fiume). D'Annunzio definisce la 'vittoria mutilata'. Origine del nazionalismo post-bellico.",
        "conflict": "WWI",
        "event_type": "evento_politico",
        "parent_event_id": None,
        "stable_id": "evt_0060",
    },
    # --- Fronte settentrionale e alpino ---
    {
        "nome": "Guerra bianca",
        "data_inizio": "1915-06-23",
        "data_fine": "1918-11-04",
        "luogo": "Alpi, Ortles-Cevedale, Adamello, Marmolada",
        "aliases": ["Guerra in alta quota", "Guerra sui ghiacciai", "White War"],
        "keywords": ["Alpi", "ghiacciai", "Adamello", "Ortles", "Marmolada", "alpini", "alta quota", "gallerie", "ghiaccio"],
        "descrizione": "Guerra di montagna ad alta quota sulle Alpi tra Italia e Austria-Ungheria. Scontri su ghiacciai oltre i 3000m (Ortles-Cevedale, Adamello, Marmolada). Gallerie nel ghiaccio, condizioni estreme, più vittime del freddo che dei combattimenti.",
        "conflict": "WWI",
        "event_type": "fronte_montano",
        "parent_event_id": None,
        "stable_id": "evt_0061",
    },
    {
        "nome": "Fronte del Tonale",
        "data_inizio": "1915-06-23",
        "data_fine": "1918-11-04",
        "luogo": "Passo del Tonale, Adamello, Ortles-Cevedale",
        "aliases": ["Settore Tonale", "Fronte dell'Adamello"],
        "keywords": ["Tonale", "Adamello", "Ortles", "alpini", "ghiacciai", "artiglieria in montagna"],
        "descrizione": "Settore del fronte alpino tra il Passo del Tonale e il massiccio dell'Adamello-Ortles. Operazioni ad alta quota, scontri su ghiacciai. Presenza di artiglieria posizionata a oltre 3000m.",
        "conflict": "WWI",
        "event_type": "fronte_montano",
        "parent_event_id": "evt_0061",
        "stable_id": "evt_0062",
    },
    {
        "nome": "Battaglia del Monte Sabotino",
        "data_inizio": "1916-08-06",
        "data_fine": "1916-08-08",
        "luogo": "Gorizia, Monte Sabotino",
        "aliases": ["Sabotino", "Conquista del Sabotino"],
        "keywords": ["Sabotino", "Gorizia", "Sesta Isonzo", "Podgora", "conquista"],
        "descrizione": "Conquista italiana del Monte Sabotino durante la Sesta battaglia dell'Isonzo. Posizione chiave per la successiva conquista di Gorizia. Attacco di sorpresa con bombardamento intensivo.",
        "conflict": "WWI",
        "event_type": "battaglia",
        "parent_event_id": "evt_0044",
        "stable_id": "evt_0063",
    },
    {
        "nome": "Difesa del Grappa",
        "data_inizio": "1917-11-13",
        "data_fine": "1918-11-04",
        "luogo": "Massiccio del Grappa, Veneto",
        "aliases": ["Presidio del Grappa", "Grappa-Piave", "Linea Grappa"],
        "keywords": ["Grappa", "difesa", "Piave", "bunker", "gallerie", "Asolone", "Solarolo", "Pertica"],
        "descrizione": "Difesa strategica del massiccio del Grappa come baluardo della linea Piave-Grappa dopo Caporetto. Costruzione di un sistema difensivo con gallerie e bunker. Il Grappa resiste a tutti gli attacchi austro-ungarici fino a Vittorio Veneto.",
        "conflict": "WWI",
        "event_type": "difesa_strategica",
        "parent_event_id": "evt_0022",
        "stable_id": "evt_0064",
    },
]


def main():
    conn = sqlite3.connect(str(EDB))
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat()

    inserted = 0
    skipped = 0
    for ev in NEW_EVENTS:
        existing = conn.execute("SELECT id FROM eventi_1gm WHERE nome = ?", (ev["nome"],)).fetchone()
        if existing:
            print(f"  SKIP (exists): {ev['nome']}")
            skipped += 1
            continue

        conn.execute(
            """INSERT INTO eventi_1gm
               (nome, data_inizio, data_fine, luogo, aliases, keywords, descrizione,
                created_at, stable_id, conflict, event_type, parent_event_id, review_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'candidate')""",
            (
                ev["nome"],
                ev["data_inizio"],
                ev["data_fine"],
                ev["luogo"],
                json.dumps(ev["aliases"], ensure_ascii=False),
                json.dumps(ev["keywords"], ensure_ascii=False),
                ev["descrizione"],
                now,
                ev["stable_id"],
                ev["conflict"],
                ev["event_type"],
                ev["parent_event_id"],
            ),
        )
        ev_id = conn.execute("SELECT id FROM eventi_1gm WHERE nome = ?", (ev["nome"],)).fetchone()[0]

        for alias in ev["aliases"]:
            conn.execute(
                "INSERT OR IGNORE INTO event_aliases (event_id, alias, alias_type, created_at) VALUES (?, ?, 'alias', ?)",
                (ev_id, alias, now),
            )

        print(f"  INSERT [{ev_id}] {ev['nome']} ({ev['stable_id']})")
        inserted += 1

    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM eventi_1gm").fetchone()[0]
    wwi = conn.execute("SELECT COUNT(*) FROM eventi_1gm WHERE conflict = 'WWI'").fetchone()[0]
    ww2 = conn.execute("SELECT COUNT(*) FROM eventi_1gm WHERE conflict = 'WWII'").fetchone()[0]
    aliases_count = conn.execute("SELECT COUNT(*) FROM event_aliases").fetchone()[0]

    print(f"\n--- Summary ---")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (already present): {skipped}")
    print(f"  Total events: {total} (WWI: {wwi}, WWII: {ww2})")
    print(f"  Total aliases: {aliases_count}")

    conn.close()


if __name__ == "__main__":
    main()
