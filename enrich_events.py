"""Arricchimento eventi — collega fonti internazionali multilaterali agli eventi
rilevanti per gli internati (catture, campi, campagne).

Per ogni evento vengono archiviati metadati da:
- fonti italiane (ANPI, USSME, ANED, Archivio Luce...)
- fonti dell'Asse/Berlinesi (Bundesarchiv, Arolsen, Mauthausen Memorial...)
- fonti Alleate (TNA, NARA, AWM, IWM, CWGC, USHMM...)

Non scarica documenti; memorizza solo metadati + URL diretti.
"""

import json
import logging
from source_locator import register_source_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Eventi con fonti curate per fazione.
# url_catalogo = link di ricerca o scheda; url_file = digitale diretto se noto.
EVENTS = [
    {
        "evento": "Eccidio di Cefalonia (settembre 1943)",
        "luogo": "Cefalonia, Grecia",
        "descrizione": "Scontri e rappresaglia tedesca contro la Divisione Acqui dopo l'8 settembre 1943",
        "fonti": [
            {
                "fazione": "Italia",
                "archivio": "Ufficio Storico SME / Associazione Divisione Acqui",
                "titolo": "Cefalonia settembre 1943: guida sommaria alle fonti archivistiche dell'Ufficio Storico dello Stato Maggiore dell'Esercito",
                "url_catalogo": "https://www.associazioneacqui.eu/ussme/",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.95,
            },
            {
                "fazione": "Italia",
                "archivio": "ANPI",
                "titolo": "Né eroi, né martiri, soltanto soldati. La Divisione 'Acqui' a Cefalonia e Corfù, settembre 1943",
                "url_catalogo": "https://www.anpi.it/bibliografia/ne-eroi-ne-martiri-soltanto-soldati",
                "tipo_fonte": "fonte_esterna",
                "access_type": "online",
                "confidence": 0.85,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "H.F. Meyer / ricerca storica tedesca",
                "titolo": "Bloodstained Edelweiss. The 1st Mountain-Division in the Second World War — indice operazioni su Cefalonia",
                "url_catalogo": "http://hfmeyer.com/english/publications/edelweiss/inhaltsverzeichnis.html",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.85,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Der Spiegel",
                "titolo": "Kefalonia 1943: Massaker der Wehrmacht an italienischen Kriegsgefangenen",
                "url_catalogo": "https://www.spiegel.de/geschichte/kefalonia-1943-massaker-der-wehrmacht-an-italienischen-kriegsgefangenen-a-1227737.html",
                "tipo_fonte": "fonte_esterna",
                "access_type": "online",
                "confidence": 0.70,
            },
            {
                "fazione": "Alleati",
                "archivio": "The National Archives (UK)",
                "titolo": "War crimes 1939-1945 — Research guide",
                "url_catalogo": "https://www.nationalarchives.gov.uk/help-with-your-research/research-guides/war-crimes-1939-1945/",
                "tipo_fonte": "guida_ricerca",
                "access_type": "online",
                "confidence": 0.80,
            },
            {
                "fazione": "Alleati",
                "archivio": "The National Archives (UK)",
                "titolo": "CAB 79/62/30 - COS(43)376(O): Morale of Italian Troops in Balkans, Greece and the Aegean; Prisoners-of-War and Civilian Internees - Transport by Sea",
                "url_catalogo": "https://discovery.nationalarchives.gov.uk/details/r/C9192472",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.85,
            },
        ],
    },
    {
        "evento": "Campi di concentramento di Mauthausen e Gusen",
        "luogo": "Mauthausen, Austria",
        "descrizione": "Internamento, lavoro forzato e morte di prigionieri italiani nei campi del sistema Mauthausen-Gusen",
        "fonti": [
            {
                "fazione": "Italia",
                "archivio": "ANED - Associazione Nazionale Ex Deportati",
                "titolo": "I deportati italiani: archivio e trasporti per Mauthausen-Gusen",
                "url_catalogo": "https://deportati.it/archivio/deportati/",
                "tipo_fonte": "archivio_vittime",
                "access_type": "online",
                "confidence": 0.95,
            },
            {
                "fazione": "Italia",
                "archivio": "ANPI",
                "titolo": "On-line i nomi dei 23.826 italiani deportati per motivi politici nei lager nazisti",
                "url_catalogo": "https://www.anpi.it/line-i-nomi-dei-23826-italiani-deportati-motivi-politici-nei-lager-nazisti",
                "tipo_fonte": "archivio_vittime",
                "access_type": "online",
                "confidence": 0.90,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Arolsen Archives",
                "titolo": "Lists of liberated prisoners of CC Mauthausen and detachment Gusen by various nationalities",
                "url_catalogo": "https://collections.arolsen-archives.org/en/archive/1-1-26-1_8101999",
                "tipo_fonte": "archivio_vittime",
                "access_type": "online",
                "confidence": 0.95,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Mauthausen Memorial",
                "titolo": "Collections and Specialist Library — KL Mauthausen",
                "url_catalogo": "https://www.mauthausen-memorial.org/en/History/Collections-and-Specialist-Library",
                "tipo_fonte": "archivio_vittime",
                "access_type": "online",
                "confidence": 0.90,
            },
            {
                "fazione": "Alleati",
                "archivio": "National Archives and Records Administration (USA)",
                "titolo": "The Mauthausen Concentration Camp Complex — Reference Information Paper 115 (PDF)",
                "url_catalogo": "https://www.archives.gov/files/publications/ref-info-papers/rip115.pdf",
                "url_file": "https://www.archives.gov/files/publications/ref-info-papers/rip115.pdf",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.90,
            },
            {
                "fazione": "Alleati",
                "archivio": "United States Holocaust Memorial Museum",
                "titolo": "Mauthausen prisoner list (Holocaust Survivors and Victims Database)",
                "url_catalogo": "https://www.ushmm.org/online/hsv/source_view.php?SourceId=20571",
                "tipo_fonte": "archivio_vittime",
                "access_type": "online",
                "confidence": 0.90,
            },
        ],
    },
    {
        "evento": "Battaglia di Tobruk e prigionia (gennaio 1941)",
        "luogo": "Tobruk, Libia",
        "descrizione": "Caduta di Tobruk in Libia e cattura di decine di migliaia di soldati italiani dalle forze australiane/britanniche",
        "fonti": [
            {
                "fazione": "Alleati",
                "archivio": "Australian War Memorial",
                "titolo": "Italian prisoners — painting by Ivor Hele, Tobruk 1941",
                "url_catalogo": "https://www.awm.gov.au/collection/C170779",
                "tipo_fonte": "fotografia_dipinto",
                "access_type": "online",
                "confidence": 0.95,
            },
            {
                "fazione": "Alleati",
                "archivio": "Australian War Memorial",
                "titolo": "Blindfolded Italian prisoners of war being brought into the fortress area, Tobruk, Libya, 1941",
                "url_catalogo": "https://www.awm.gov.au/collection/C13666",
                "tipo_fonte": "fotografia_dipinto",
                "access_type": "online",
                "confidence": 0.95,
            },
            {
                "fazione": "Alleati",
                "archivio": "Australian War Memorial",
                "titolo": "Tobruk - prisoners on their way to concentration camp after the battle of Tobruk",
                "url_catalogo": "https://www.awm.gov.au/collection/005640",
                "tipo_fonte": "fotografia_dipinto",
                "access_type": "online",
                "confidence": 0.95,
            },
            {
                "fazione": "Alleati",
                "archivio": "State Library of Queensland",
                "titolo": "Italian prisoners captured in Tobruk, January 1941",
                "url_catalogo": "https://www.slq.qld.gov.au/media/49192",
                "tipo_fonte": "fotografia_dipinto",
                "access_type": "online",
                "confidence": 0.85,
            },
            {
                "fazione": "Italia",
                "archivio": "Ufficio Storico SME / Comando Supremo",
                "titolo": "Diari storici e documentazione della 10ª Armata: campagna di Libia 1940-1941",
                "url_catalogo": "https://www.esercito.difesa.it/storia/Ufficio-Storico-SME",
                "tipo_fonte": "military_document",
                "access_type": "richiesta",
                "confidence": 0.75,
            },
        ],
    },
    {
        "evento": "Campagna italiana in Russia (ARMIR, 1941-1943)",
        "luogo": "Fronte orientale (Russia)",
        "descrizione": "Operazioni dell'ARMIR sul fronte orientale e disastro della ritirata invernale 1942-1943",
        "fonti": [
            {
                "fazione": "Italia",
                "archivio": "Ufficio Storico SME",
                "titolo": "Archivio storico SME: campagna di Russia dell'ARMIR",
                "url_catalogo": "https://www.esercito.difesa.it/storia/Ufficio-Storico-SME",
                "tipo_fonte": "military_document",
                "access_type": "richiesta",
                "confidence": 0.85,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "National Archives and Records Administration (USA) / captured German records",
                "titolo": "Relazione sul II C.A. al fronte russo, 13 May 1943 — NARA T-821/511/0956",
                "url_catalogo": "https://www.archives.gov/research/captured-german-records",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.75,
            },
            {
                "fazione": "Alleati",
                "archivio": "Defense Technical Information Center (USA)",
                "titolo": "The Italian Expedition in the Russian Campaign 1941-43",
                "url_catalogo": "https://apps.dtic.mil/sti/tr/pdf/AD1039005.pdf",
                "url_file": "https://apps.dtic.mil/sti/tr/pdf/AD1039005.pdf",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.80,
            },
        ],
    },
    {
        "evento": "Operazione Achse e internamento militare italiano (1943-1945)",
        "luogo": "Italia / Germania",
        "descrizione": "Disarmo delle forze armate italiane nei territori occupati e deportazione come 'Internati Militari Italiani' (IMI) nel Terzo Reich",
        "fonti": [
            {
                "fazione": "Italia",
                "archivio": "ANPI",
                "titolo": "8 settembre 1943: l'armistizio e l'internamento militare italiano",
                "url_catalogo": "https://www.anpi.it",
                "tipo_fonte": "fonte_esterna",
                "access_type": "online",
                "confidence": 0.70,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Bundesarchiv",
                "titolo": "Italian POWs and military internees in Nazi Germany — Portal on Forced Labour",
                "url_catalogo": "https://www.bundesarchiv.de/zwangsarbeit/leistungen/direktleistungen/nicht_beruecksichtigt/index.html.en",
                "tipo_fonte": "guida_ricerca",
                "access_type": "online",
                "confidence": 0.85,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Nazi Forced Labor Documentation Center",
                "titolo": "Between all stools. The history of the Italian military internees 1943-1945",
                "url_catalogo": "https://www.ns-zwangsarbeit.de/en/italian-military-internees",
                "tipo_fonte": "mostra_documentazione",
                "access_type": "online",
                "confidence": 0.90,
            },
            {
                "fazione": "Alleati",
                "archivio": "National Archives and Records Administration (USA)",
                "titolo": "Guides to Records of the Italian Armed Forces (captured Italian and German records, T-94)",
                "url_catalogo": "https://www.archives.gov/files/research/captured-german-records/microfilm/t94.pdf",
                "url_file": "https://www.archives.gov/files/research/captured-german-records/microfilm/t94.pdf",
                "tipo_fonte": "military_document",
                "access_type": "online",
                "confidence": 0.80,
            },
        ],
    },
    {
        "evento": "Lavoro forzato italiano nel Terzo Reich (1943-1945)",
        "luogo": "Germania",
        "descrizione": "Impiego di Internati Militari Italiani (IMI) e altri prigionieri italiani come manodopera coatta in Germania",
        "fonti": [
            {
                "fazione": "Italia",
                "archivio": "ANED",
                "titolo": "I deportati italiani: archivio generale",
                "url_catalogo": "https://deportati.it/archivio/deportati/",
                "tipo_fonte": "archivio_vittime",
                "access_type": "online",
                "confidence": 0.90,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Bundesarchiv",
                "titolo": "Foreign Manpower from other Nations — Italian officers arrested by German paratroopers, September 1943",
                "url_catalogo": "https://www.bundesarchiv.de/zwangsarbeit/geschichte/auslaendisch/andere_kraefte/index.html.en",
                "tipo_fonte": "guida_ricerca",
                "access_type": "online",
                "confidence": 0.85,
            },
            {
                "fazione": "Germania/Asse",
                "archivio": "Nazi Forced Labor Documentation Center",
                "titolo": "Zwischen allen Stühlen — Geschichte der italienischen Militärinternierten 1943-1945",
                "url_catalogo": "https://www.ns-zwangsarbeit.de/en/italian-military-internees",
                "tipo_fonte": "mostra_documentazione",
                "access_type": "online",
                "confidence": 0.90,
            },
            {
                "fazione": "Alleati",
                "archivio": "National Archives and Records Administration (USA)",
                "titolo": "Records of Italian military internees and forced labourers in Germany",
                "url_catalogo": "https://catalog.archives.gov/search?q=Italian%20military%20internees%20Germany",
                "tipo_fonte": "guida_ricerca",
                "access_type": "online",
                "confidence": 0.70,
            },
        ],
    },
]


def main():
    stats = {"events": 0, "registered": 0, "updated": 0, "errors": 0}
    for event in EVENTS:
        event_name = event["evento"]
        event_luogo = event.get("luogo", "")
        logger.info("Evento: %s", event_name)
        for f in event["fonti"]:
            try:
                note = {
                    "fazione": f["fazione"],
                    "evento": event_name,
                    "descrizione": event.get("descrizione", ""),
                }
                result = register_source_metadata(
                    archivio=f["archivio"],
                    titolo=f["titolo"],
                    tipo_fonte=f["tipo_fonte"],
                    soggetti_collegati=event_name,
                    luogo=event_luogo,
                    data_inizio=None,
                    data_fine=None,
                    url_catalogo=f["url_catalogo"],
                    url_file=f.get("url_file"),
                    access_type=f["access_type"],
                    confidence=f["confidence"],
                    note=json.dumps(note, ensure_ascii=False),
                )
                if result.get("created"):
                    stats["registered"] += 1
                else:
                    stats["updated"] += 1
                logger.info("  [%s] %s -> %s", f["fazione"], f["archivio"], result.get("id"))
            except Exception as e:
                stats["errors"] += 1
                logger.error("  ERRORE %s: %s", f.get("archivio"), e)
        stats["events"] += 1

    logger.info("Riepilogo: eventi=%d, registrate=%d, aggiornate=%d, errori=%d",
                stats["events"], stats["registered"], stats["updated"], stats["errors"])
    return stats


if __name__ == "__main__":
    main()
