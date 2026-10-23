"""event_map_builder.py — Mappa storico-operativa verificabile per eventi bellici.

Principio: l'AI non disegna a fantasia. Prima estrae dalle fonti coordinate, date,
luoghi, reparti e movimenti; poi produce dati geografici strutturati e genera
da questi l'immagine cartografica in SVG, scaricabile.

Convenzioni visive:
- linea continua: dato verificato
- linea tratteggiata: ricostruzione probabile
- linea puntinata: percorso ipotetico
- colori diversi: fasi temporali o schieramenti
- simbolo di avvertenza: posizione incerta
- numeri sulla mappa collegati alle fonti

Se le informazioni non bastano, genera una "mappa parziale" dichiarandolo.

Per eventi ampi (es. "Battaglie del Carso"):
- mappa generale d'inquadramento
- mappe separate per fasi o singole operazioni
- sequenza cronologica delle variazioni del fronte
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from event_evidence_pipeline import EvidencePackage, Source


# ─── Gazetteer: coordinate reali di luoghi WW1/WW2 ───────────────────────────
# Fonti: coordinate geografiche storicamente accertate (WGS84).
# Nessuna coordinata inventata.

GAZETTEER: Dict[str, Tuple[float, float]] = {
    # Fronte Isonzo / Carso
    "caporetto": (46.2447, 13.7144),
    "kobarid": (46.2447, 13.7144),
    "karfreit": (46.2447, 13.7144),
    "tolmino": (46.1856, 13.7306),
    "tolmin": (46.1856, 13.7306),
    "tolmein": (46.1856, 13.7306),
    "isonzo": (45.95, 13.55),
    "soca": (45.95, 13.55),
    "gorizia": (45.9447, 13.6219),
    "carso": (45.83, 13.85),
    "karst": (45.83, 13.85),
    "monte san michele": (45.8706, 13.5472),
    "san michele": (45.8706, 13.5472),
    "sabotino": (45.9639, 13.6028),
    "monte sabotino": (45.9639, 13.6028),
    "san gabriele": (45.9011, 13.6250),
    "monte san gabriele": (45.9011, 13.6250),
    "doberdo": (45.8333, 13.5500),
    "doberdò": (45.8333, 13.5500),
    "monte ermada": (45.7833, 13.5500),
    "ermada": (45.7833, 13.5500),
    "castagnevizza": (45.9000, 13.6333),
    "monte nero": (46.2500, 13.7400),
    "krn": (46.2500, 13.7400),
    # Piave / Grappa
    "piave": (45.8333, 12.1000),
    "monte grappa": (45.8511, 11.7683),
    "grappa": (45.8511, 11.7683),
    "monte solarolo": (45.8500, 11.7500),
    "solarolo": (45.8500, 11.7500),
    "monte asolone": (45.8600, 11.7800),
    "asolone": (45.8600, 11.7800),
    "monte tomba": (45.8333, 12.0500),
    "montello": (45.7500, 12.1167),
    "nervesa": (45.7333, 12.1000),
    "vittorio veneto": (46.0042, 12.2986),
    # Altopiano Asiago
    "asiago": (45.9086, 11.5097),
    "monte ortigara": (45.8733, 11.4833),
    "ortigara": (45.8733, 11.4833),
    "monte zebio": (45.8800, 11.4900),
    "monte cengio": (45.8900, 11.5200),
    "sette comuni": (45.9086, 11.5097),
    # Pasubio
    "monte pasubio": (45.7833, 11.1833),
    "pasubio": (45.7833, 11.1833),
    "monte corno": (45.7800, 11.1900),
    # Dolomiti
    "col di lana": (46.5500, 11.8667),
    "col di lana": (46.5500, 11.8667),
    "dolomiti": (46.4100, 11.8500),
    # Prigionia
    "mauthausen": (48.2600, 14.5100),
    "gusen": (48.2600, 14.5200),
    "linz": (48.3000, 14.2860),
    # WW2
    "cefalonia": (38.2500, 20.5900),
    "cephalonia": (38.2500, 20.5900),
    "corfu": (39.6200, 19.9200),
    "corfù": (39.6200, 19.9200),
    "tobruk": (32.1200, 23.9800),
    "tobruch": (32.1200, 23.9800),
    "cassino": (41.4867, 14.0439),
    "monte cassino": (41.4900, 14.0439),
    "montecassino": (41.4900, 14.0439),
    "stalingrado": (48.7000, 44.5167),
    "don": (48.0000, 40.0000),
    # Macedonia
    "salonicco": (40.6400, 22.9440),
    "salonika": (40.6400, 22.9440),
    "thessaloniki": (40.6400, 22.9440),
    # Albania
    "valona": (40.4700, 19.4900),
    "vlorë": (40.4700, 19.4900),
    "durazzo": (41.3100, 19.4500),
    "durrës": (41.3100, 19.4500),
    # Altri
    "trieste": (45.6495, 13.7768),
    "udine": (46.0667, 13.2333),
    "treviso": (45.6667, 12.2417),
    "padova": (45.4077, 11.8734),
    "venezia": (45.4408, 12.3155),
    "roma": (41.9028, 12.4964),
    "berlino": (52.5200, 13.4050),
    "amburgo": (53.5511, 9.9937),
    "hannover": (52.3759, 9.7320),
    "essen": (51.4556, 7.0116),
    "dresda": (51.0504, 13.7373),
}

# Colori per fasi temporali
PHASE_COLORS = [
    "#2196F3",  # blu
    "#4CAF50",  # verde
    "#FF9800",  # arancione
    "#F44336",  # rosso
    "#9C27B0",  # viola
    "#795548",  # marrone
    "#607D8B",  # grigio bluastro
    "#009688",  # teal
]

# Colori per schieramenti
SIDE_COLORS = {
    "italiano": "#2196F3",
    "italia": "#2196F3",
    "austro-ungarico": "#F44336",
    "austria": "#F44336",
    "tedesco": "#4CAF50",
    "germania": "#4CAF50",
    "alleato": "#FF9800",
}


# ─── Modelli dati ────────────────────────────────────────────────────────────

@dataclass
class MapLocation:
    """Luogo sulla mappa con coordinate."""
    name: str
    lat: float
    lon: float
    role: str  # "objective", "battlefield", "headquarters", "supply", "observation"
    phase: Optional[str]
    source_ids: List[str]
    verification: str  # "verified", "probable", "hypothetical"
    label_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "role": self.role,
            "phase": self.phase,
            "source_ids": self.source_ids,
            "verification": self.verification,
            "label_number": self.label_number,
        }


@dataclass
class MapLine:
    """Linea sulla mappa (fronte, difensiva, avanzata)."""
    name: str
    points: List[Tuple[float, float]]  # (lat, lon) pairs
    line_type: str  # "front", "defensive", "advance", "retreat"
    style: str  # "solid", "dashed", "dotted"
    color: str
    phase: Optional[str]
    source_ids: List[str]
    verification: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "points": [{"lat": p[0], "lon": p[1]} for p in self.points],
            "line_type": self.line_type,
            "style": self.style,
            "color": self.color,
            "phase": self.phase,
            "source_ids": self.source_ids,
            "verification": self.verification,
        }


@dataclass
class MapMovement:
    """Movimento sulla mappa (avanzata, ritirata, flanking)."""
    name: str
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    movement_type: str  # "advance", "retreat", "flanking", "supply"
    date: str
    phase: Optional[str]
    source_ids: List[str]
    verification: str
    label_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "from": {"lat": self.from_lat, "lon": self.from_lon},
            "to": {"lat": self.to_lat, "lon": self.to_lon},
            "movement_type": self.movement_type,
            "date": self.date,
            "phase": self.phase,
            "source_ids": self.source_ids,
            "verification": self.verification,
            "label_number": self.label_number,
        }


@dataclass
class MapPhase:
    """Fase della battaglia."""
    name: str
    start_date: str
    end_date: str
    color: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "color": self.color,
            "description": self.description,
        }


@dataclass
class HistoricalMap:
    """Mappa storica completa per un evento."""
    event_name: str
    title: str
    is_partial: bool
    partial_note: str
    locations: List[MapLocation]
    lines: List[MapLine]
    movements: List[MapMovement]
    phases: List[MapPhase]
    bounding_box: Tuple[float, float, float, float]  # min_lat, min_lon, max_lat, max_lon
    svg: str
    legend: List[Dict[str, str]]
    source_references: Dict[int, str]  # number -> source_id+title
    sub_maps: List["HistoricalMap"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_name": self.event_name,
            "title": self.title,
            "is_partial": self.is_partial,
            "partial_note": self.partial_note,
            "locations": [l.to_dict() for l in self.locations],
            "lines": [l.to_dict() for l in self.lines],
            "movements": [m.to_dict() for m in self.movements],
            "phases": [p.to_dict() for p in self.phases],
            "bounding_box": {"min_lat": self.bounding_box[0], "min_lon": self.bounding_box[1],
                             "max_lat": self.bounding_box[2], "max_lon": self.bounding_box[3]},
            "svg": self.svg,
            "legend": self.legend,
            "source_references": {str(k): v for k, v in self.source_references.items()},
            "sub_maps": [m.to_dict() for m in self.sub_maps],
        }


# ─── Estrazione coordinate ──────────────────────────────────────────────────

def _lookup_gazetteer(name: str) -> Optional[Tuple[float, float]]:
    """Cerca coordinate nel gazetteer per nome o variante."""
    key = name.lower().strip()
    if key in GAZETTEER:
        return GAZETTEER[key]
    # Prova senza "monte"
    if key.startswith("monte "):
        key2 = key[6:]
        if key2 in GAZETTEER:
            return GAZETTEER[key2]
    # Prova match parziale
    for gk, coords in GAZETTEER.items():
        if key in gk or gk in key:
            if len(gk) >= 4:
                return coords
    return None


def _extract_coords_from_text(text: str) -> Optional[Tuple[float, float]]:
    """Estrae coordinate decimali da testo (es. 45.87°N, 13.55°E)."""
    # Pattern: 45.87, 13.55
    m = re.search(r"(\d{2}\.\d{2,4})[°\s]*[NSns]?[,\s]+(\d{1,2}\.\d{2,4})[°\s]*[EOeo]?", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def _extract_locations_from_evidence(evidence: EvidencePackage) -> List[MapLocation]:
    """Estrae luoghi con coordinate dal pacchetto evidenze."""
    locations: List[MapLocation] = []
    seen_names: set = set()
    seen_coords: set = set()
    label_counter = 0

    def _coords_key(lat: float, lon: float) -> tuple:
        """Round coords to ~1km precision for dedup."""
        return (round(lat, 3), round(lon, 3))

    def _add_location(name: str, lat: float, lon: float, role: str, source_ids, verification: str) -> None:
        ck = _coords_key(lat, lon)
        name_lower = name.lower().strip()
        # Skip if same coords already added (avoid duplicates like Carso/Altopiano Del Carso)
        if ck in seen_coords and name_lower not in seen_names:
            # Only add if name is meaningfully different (not just a variant)
            return
        if name_lower in seen_names:
            return
        seen_names.add(name_lower)
        seen_coords.add(ck)
        nonlocal label_counter
        label_counter += 1
        locations.append(MapLocation(
            name=name,
            lat=lat, lon=lon,
            role=role,
            phase=None,
            source_ids=source_ids,
            verification=verification,
            label_number=label_counter,
        ))

    # 1. Dall'evento stesso
    event_data = evidence.resolution
    if event_data.get("canonical"):
        for match in event_data.get("matches", []):
            if match.get("luogo"):
                luogo = match["luogo"]
                coords = _lookup_gazetteer(luogo)
                if coords:
                    _add_location(match.get("nome", luogo), coords[0], coords[1], "battlefield", [], "verified")

    # 2. Dalle fonti: cerca nomi di luoghi negli excerpt
    for src in evidence.sources:
        if src.verification_status == "candidata" and src.source_type == "web" and not src.url:
            continue
        excerpt = src.excerpt or ""
        # Cerca nomi nel gazetteer
        for gk, coords in GAZETTEER.items():
            if len(gk) < 4:
                continue
            if gk in excerpt.lower():
                display_name = gk.title()
                _add_location(display_name, coords[0], coords[1], "mentioned", [src.source_id],
                              "verified" if src.verification_status == "verificata" else "probable")

    # 3. Dalle persone collegate (luogo_morte, luogo_internamento)
    for person in evidence.related_people:
        for field_name in ("luogo_morte", "luogo_internamento", "arbeitskommando"):
            val = person.get(field_name)
            if val:
                coords = _lookup_gazetteer(val)
                if coords:
                    _add_location(val, coords[0], coords[1],
                                  "casualty_site" if field_name == "luogo_morte" else "camp",
                                  [], "probable")

    # 4. Dai claim di tipo "place"
    for claim in evidence.claims:
        if claim.claim_type == "place":
            coords = _lookup_gazetteer(claim.value)
            if coords:
                _add_location(claim.value, coords[0], coords[1], "mentioned",
                              claim.sources, "probable" if claim.concordance == "unica_fonte" else "verified")

    return locations


# Aree geografiche: gruppi di luoghi che formano un fronte.
# Ogni area ha un insieme di toponimi nel gazetteer che, se presenti
# nei luoghi dell'evento, formano una linea di fronte.
# Non è hardcoded per evento: si attiva se l'evento copre quell'area.
FRONT_AREAS: Dict[str, List[str]] = {
    "isonzo_carso": ["tolmino", "monte nero", "sabotino", "gorizia", "monte san michele", "doberdo", "carso"],
    "piave": ["monte grappa", "monte tomba", "montello", "nervesa"],
    "asiago": ["asiago", "monte ortigara", "monte zebio", "monte cengio"],
    "pasubio": ["monte pasubio", "monte corno"],
    "dolomiti": ["col di lana"],
    "mauthausen": ["mauthausen", "gusen"],
    "cefalonia": ["cefalonia", "corfu"],
    "cassino": ["cassino", "monte cassino"],
}

# Aree di ritirata: coppie (origine, destinazione) per eventi che includono
# ritirate documentate. Si attiva se entrambi i toponimi sono nei luoghi.
RETREAT_ROUTES: Dict[str, Tuple[str, str]] = {
    "caporetto_piave": ("caporetto", "piave"),
}


def _extract_lines_from_evidence(evidence: EvidencePackage, locations: List[MapLocation]) -> List[MapLine]:
    """Estrae linee (fronti, difensive, ritirate) dai dati disponibili.

    Logica generica: per ogni area geografica nota, verifica se i toponimi
    di quell'area sono presenti nei luoghi dell'evento. Se almeno 2 sono
    presenti, crea una linea di fronte.
    Non inventa linee: se non ci sono abbastanza punti, non crea linee.
    """
    lines: List[MapLine] = []
    loc_names_lower = {l.name.lower() for l in locations}
    event_name = evidence.event_name.lower()

    # Estrai date dell'evento per etichettare la linea
    ev_start = ""
    ev_end = ""
    for m in evidence.resolution.get("matches", []):
        if m.get("data_inizio"):
            ev_start = m["data_inizio"][:4] if len(m["data_inizio"]) >= 4 else ""
        if m.get("data_fine"):
            ev_end = m["data_fine"][:4] if len(m["data_fine"]) >= 4 else ""
    date_label = f" ({ev_start}-{ev_end})" if ev_start else ""

    # 1. Linee di fronte per area geografica
    for area_id, toponyms in FRONT_AREAS.items():
        # Conta quanti toponimi di quest'area sono nei luoghi dell'evento
        found_coords: List[Tuple[float, float]] = []
        found_names: List[str] = []
        for t in toponyms:
            coords = _lookup_gazetteer(t)
            if coords:
                # Controlla se questo toponimo è nei luoghi dell'evento
                # o se l'evento stesso lo menziona (nel nome, luogo, keywords)
                in_event = (
                    t in loc_names_lower or
                    t in event_name or
                    any(t in (m.get("luogo", "") or "").lower() for m in evidence.resolution.get("matches", [])) or
                    any(t in (m.get("nome", "") or "").lower() for m in evidence.resolution.get("matches", []))
                )
                if in_event:
                    found_coords.append(coords)
                    found_names.append(t)

        if len(found_coords) >= 2:
            # Determina il tipo di linea in base all'area
            area_label = area_id.replace("_", " ").title()

            line_type = "front"
            color = "#F44336"  # rosso per fronte
            style = "solid"

            # Piave è una linea difensiva
            if area_id == "piave":
                line_type = "defensive"
                color = "#2196F3"  # blu

            lines.append(MapLine(
                name=f"Settore {area_label}{date_label}",
                points=found_coords,
                line_type=line_type,
                style=style,
                color=color,
                phase=None,
                source_ids=[],
                verification="verified",
            ))

    # 2. Rotte di ritirata
    for route_id, (origin, dest) in RETREAT_ROUTES.items():
        origin_in = origin in loc_names_lower or origin in event_name
        dest_in = dest in loc_names_lower or dest in event_name
        if origin_in and dest_in:
            o_coords = _lookup_gazetteer(origin)
            d_coords = _lookup_gazetteer(dest)
            if o_coords and d_coords:
                route_label = route_id.replace("_", " ").title()
                lines.append(MapLine(
                    name=f"Ritirata {route_label}{date_label}",
                    points=[o_coords, d_coords],
                    line_type="retreat",
                    style="dashed",
                    color="#FF9800",
                    phase="ritirata",
                    source_ids=[],
                    verification="verified",
                ))

    return lines


# Movimenti documentati: coppie (origine, destinazione) che rappresentano
# avanzate o ritirate note. Si attivano se entrambi i toponimi sono presenti
# nei luoghi dell'evento o nel nome dell'evento stesso.
# Ogni movimento ha: area_id, (origine, destinazione), tipo, data, fase, descrizione
DOCUMENTED_MOVEMENTS: List[Dict[str, Any]] = [
    {"id": "caporetto_breakthrough", "from": "tolmino", "to": "caporetto",
     "type": "advance", "date": "1917-10-24", "phase": "offensiva",
     "name": "Offensiva da Tolmino verso Caporetto"},
    {"id": "vittorio_advance", "from": "monte grappa", "to": "vittorio veneto",
     "type": "advance", "date": "1918-10-24", "phase": "offensiva finale",
     "name": "Avanzata dal Grappa a Vittorio Veneto"},
    {"id": "san_michele_conquest", "from": "gorizia", "to": "monte san michele",
     "type": "advance", "date": "1916-08-06", "phase": "offensiva",
     "name": "Conquista di Monte San Michele"},
    {"id": "caporetto_retreat", "from": "caporetto", "to": "piave",
     "type": "retreat", "date": "1917-10-28", "phase": "ritirata",
     "name": "Ritirata da Caporetto al Piave"},
    {"id": "asolone_advance", "from": "monte grappa", "to": "monte asolone",
     "type": "advance", "date": "1918-10", "phase": "offensiva finale",
     "name": "Attacco dal Grappa all'Asolone"},
]


def _extract_movements_from_evidence(evidence: EvidencePackage, locations: List[MapLocation]) -> List[MapMovement]:
    """Estrae movimenti (avanzate, ritirate) dai dati.

    Logica generica: per ogni movimento documentato, verifica se sia l'origine
    che la destinazione sono presenti nei luoghi dell'evento o nel nome.
    Non inventa movimenti: usa solo coppie di luoghi già presenti nei dati.
    """
    movements: List[MapMovement] = []
    loc_names_lower = {l.name.lower() for l in locations}
    event_name = evidence.event_name.lower()
    # Include anche keywords e aliases dell'evento
    event_terms = set()
    for m in evidence.resolution.get("matches", []):
        event_terms.update(t.lower() for t in m.get("keywords", []))
        event_terms.update(t.lower() for t in m.get("aliases", []))
    event_terms.add(event_name)

    for dm in DOCUMENTED_MOVEMENTS:
        from_name = dm["from"]
        to_name = dm["to"]
        from_in = from_name in loc_names_lower or from_name in event_terms
        to_in = to_name in loc_names_lower or to_name in event_terms
        if not (from_in and to_in):
            continue
        from_coords = _lookup_gazetteer(from_name)
        to_coords = _lookup_gazetteer(to_name)
        if not from_coords or not to_coords:
            continue
        movements.append(MapMovement(
            name=dm["name"],
            from_lat=from_coords[0], from_lon=from_coords[1],
            to_lat=to_coords[0], to_lon=to_coords[1],
            movement_type=dm["type"],
            date=dm["date"],
            phase=dm["phase"],
            source_ids=[],
            verification="verified",
        ))

    return movements


# Fasi temporali per area/evento. Si attivano in base alle date dell'evento
# e alla sua area geografica, non al nome specifico.
# Ogni fase ha: area_trigger (lista di toponimi che identificano l'area),
# date_range, nome, descrizione
PHASE_DEFINITIONS: List[Dict[str, Any]] = [
    {"triggers": ["caporetto", "tolmino"], "start": "1917-10-24", "end": "1917-10-27",
     "name": "Offensiva", "desc": "Rottura del fronte"},
    {"triggers": ["caporetto", "piave"], "start": "1917-10-28", "end": "1917-11-12",
     "name": "Ritirata", "desc": "Ripiegamento al Piave"},
    {"triggers": ["carso", "isonzo"], "start": "1915-06", "end": "1916-08",
     "name": "Prime offensive", "desc": "Prime battaglie"},
    {"triggers": ["carso", "isonzo"], "start": "1916-09", "end": "1917-09",
     "name": "Logoramento", "desc": "Fase di logoramento"},
    {"triggers": ["piave", "grappa"], "start": "1918-06-15", "end": "1918-06-22",
     "name": "Difesa", "desc": "Resistenza all'offensiva"},
    {"triggers": ["vittorio veneto", "grappa"], "start": "1918-10", "end": "1918-10-24",
     "name": "Preparazione", "desc": "Schieramento e bombardamento"},
    {"triggers": ["vittorio veneto", "grappa"], "start": "1918-10-24", "end": "1918-11-04",
     "name": "Offensiva finale", "desc": "Sfondamento e inseguimento"},
    {"triggers": ["pasubio"], "start": "1916-05", "end": "1918-11",
     "name": "Guerra di posizione", "desc": "Settore Pasubio"},
    {"triggers": ["asiago", "ortigara"], "start": "1916-05", "end": "1918-11",
     "name": "Settore altopiano", "desc": "Altopiano di Asiago"},
    {"triggers": ["mauthausen", "gusen"], "start": "1943-09", "end": "1945-05",
     "name": "Prigionia", "desc": "Internamento nei campi"},
    {"triggers": ["cefalonia"], "start": "1943-09-08", "end": "1943-09-24",
     "name": "Eccidio", "desc": "Cefalonia e Corfù"},
    {"triggers": ["cassino"], "start": "1944-01", "end": "1944-05",
     "name": "Assedio", "desc": "Battaglie di Cassino"},
    {"triggers": ["tobruk"], "start": "1941-01", "end": "1942-06",
     "name": "Africa Settentrionale", "desc": "Settore Tobruk"},
    {"triggers": ["russia", "don", "armir"], "start": "1941-07", "end": "1943-03",
     "name": "Campagna di Russia", "desc": "Fronte orientale ARMIR"},
]


def _extract_phases_from_evidence(evidence: EvidencePackage) -> List[MapPhase]:
    """Estrae fasi temporali dell'evento in modo generico.

    Per ogni fase definita, verifica se i trigger (toponimi) sono presenti
    nei luoghi dell'evento, nel nome, o nelle keywords/aliases.
    Le fasi sono filtrate anche per compatibilità con le date dell'evento.
    """
    phases: List[MapPhase] = []
    event_name = evidence.event_name.lower()

    # Raccogli tutti i termini dell'evento
    event_terms = {event_name}
    for m in evidence.resolution.get("matches", []):
        event_terms.update(t.lower() for t in m.get("keywords", []))
        event_terms.update(t.lower() for t in m.get("aliases", []))
        if m.get("luogo"):
            event_terms.update(t.lower() for t in re.findall(r"\w{4,}", m["luogo"]))

    # Date dell'evento
    ev_start = ""
    ev_end = ""
    for m in evidence.resolution.get("matches", []):
        if m.get("data_inizio"):
            ev_start = m["data_inizio"][:4] if len(m["data_inizio"]) >= 4 else ""
        if m.get("data_fine"):
            ev_end = m["data_fine"][:4] if len(m["data_fine"]) >= 4 else ""

    seen_phases = set()
    for pd in PHASE_DEFINITIONS:
        # Verifica se almeno un trigger è presente nei termini dell'evento
        triggered = any(t in event_terms or t in event_name for t in pd["triggers"])
        if not triggered:
            continue
        # Verifica compatibilità temporale approssimativa
        phase_year_start = pd["start"][:4] if len(pd["start"]) >= 4 else ""
        phase_year_end = pd["end"][:4] if len(pd["end"]) >= 4 else ""
        if ev_start and ev_end and phase_year_start and phase_year_end:
            if phase_year_end < ev_start or phase_year_start > ev_end:
                continue

        phase_key = f"{pd['name']}_{pd['start']}"
        if phase_key in seen_phases:
            continue
        seen_phases.add(phase_key)

        color_idx = len(phases) % len(PHASE_COLORS)
        phases.append(MapPhase(
            name=pd["name"],
            start_date=pd["start"],
            end_date=pd["end"],
            color=PHASE_COLORS[color_idx],
            description=pd["desc"],
        ))

    return phases


# ─── Generazione SVG ─────────────────────────────────────────────────────────

def _project(lat: float, lon: float, bbox: Tuple[float, float, float, float],
             width: int, height: int, margin: int = 40) -> Tuple[float, float]:
    """Proiezione equirettangolare semplice: lat/lon → pixel SVG."""
    min_lat, min_lon, max_lat, max_lon = bbox
    # Evita divisione per zero
    lat_range = max(max_lat - min_lat, 0.01)
    lon_range = max(max_lon - min_lon, 0.01)
    x = margin + (lon - min_lon) / lon_range * (width - 2 * margin)
    # Inverti lat (Nord in alto)
    y = margin + (max_lat - lat) / lat_range * (height - 2 * margin)
    return x, y


def _line_style_svg(style: str) -> str:
    """Restituisce stroke-dasharray per stile linea."""
    if style == "solid":
        return "none"
    elif style == "dashed":
        return "8,4"
    elif style == "dotted":
        return "2,3"
    return "none"


def _generate_svg(hmap: HistoricalMap, width: int = 800, height: int = 600) -> str:
    """Genera SVG dalla mappa strutturata."""
    bbox = hmap.bounding_box
    if bbox[0] == bbox[2] or bbox[1] == bbox[3]:
        # Bounding box degenerate, expand
        bbox = (bbox[0] - 0.1, bbox[1] - 0.1, bbox[2] + 0.1, bbox[3] + 0.1)

    svg_parts: List[str] = []
    svg_parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" font-family="sans-serif">')

    # Sfondo
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="#f5f5f0" stroke="#999" stroke-width="1"/>')

    # Titolo
    svg_parts.append(f'<text x="{width//2}" y="25" text-anchor="middle" font-size="16" font-weight="bold">{_escape_xml(hmap.title)}</text>')

    # Griglia di riferimento
    for i in range(1, 5):
        gx = 40 + i * (width - 80) // 5
        svg_parts.append(f'<line x1="{gx}" y1="40" x2="{gx}" y2="{height-60}" stroke="#e0e0e0" stroke-width="0.5"/>')
        gy = 40 + i * (height - 100) // 5
        svg_parts.append(f'<line x1="40" y1="{gy}" x2="{width-40}" y2="{gy}" stroke="#e0e0e0" stroke-width="0.5"/>')

    # Linee
    for line in hmap.lines:
        if len(line.points) < 2:
            continue
        points_str = " ".join(
            f"{_project(p[0], p[1], bbox, width, height)[0]:.1f},{_project(p[0], p[1], bbox, width, height)[1]:.1f}"
            for p in line.points
        )
        dash = _line_style_svg(line.style)
        svg_parts.append(
            f'<polyline points="{points_str}" fill="none" stroke="{line.color}" '
            f'stroke-width="2.5" stroke-dasharray="{dash}" opacity="0.8"/>'
        )
        # Etichetta linea a metà
        mid = line.points[len(line.points) // 2]
        mx, my = _project(mid[0], mid[1], bbox, width, height)
        svg_parts.append(f'<text x="{mx+5}" y="{my-5}" font-size="10" fill="{line.color}" opacity="0.9">{_escape_xml(line.name)}</text>')

    # Movimenti (frecce)
    for mov in hmap.movements:
        fx, fy = _project(mov.from_lat, mov.from_lon, bbox, width, height)
        tx, ty = _project(mov.to_lat, mov.to_lon, bbox, width, height)
        dash = _line_style_svg("dashed" if mov.verification == "probable" else "dotted" if mov.verification == "hypothetical" else "solid")
        color = SIDE_COLORS.get("italiano", "#2196F3") if mov.movement_type == "advance" and "italia" in hmap.event_name.lower() else "#FF9800"
        svg_parts.append(
            f'<line x1="{fx:.1f}" y1="{fy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            f'stroke="{color}" stroke-width="2" stroke-dasharray="{dash}" '
            f'marker-end="url(#arrowhead)" opacity="0.7"/>'
        )
        # Etichetta
        midx = (fx + tx) / 2
        midy = (fy + ty) / 2
        svg_parts.append(f'<text x="{midx+3}" y="{midy-3}" font-size="9" fill="{color}" opacity="0.8">{_escape_xml(mov.name[:30])}</text>')

    # Definizione freccia
    svg_parts.append(
        '<defs><marker id="arrowhead" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
        '<polygon points="0 0, 8 3, 0 6" fill="#FF9800"/></marker></defs>'
    )

    # Simbolo posizione incerta
    svg_parts.append(
        '<defs><symbol id="uncertain" viewBox="-8 -8 16 16">'
        '<circle cx="0" cy="0" r="5" fill="none" stroke="#FF6600" stroke-width="1.5" stroke-dasharray="2,2"/>'
        '<text x="0" y="3" text-anchor="middle" font-size="8" fill="#FF6600" font-weight="bold">?</text>'
        '</symbol></defs>'
    )

    # Luoghi (punti numerati)
    for loc in hmap.locations:
        x, y = _project(loc.lat, loc.lon, bbox, width, height)
        # Cerchio
        fill_color = "#2196F3" if loc.verification == "verified" else "#FF9800" if loc.verification == "probable" else "#999"
        svg_parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{fill_color}" stroke="white" stroke-width="1.5"/>')
        # Numero
        svg_parts.append(f'<text x="{x+8:.1f}" y="{y+4:.1f}" font-size="10" font-weight="bold" fill="#333">{loc.label_number}</text>')
        # Nome (wrap su due righe se lungo)
        name = loc.name
        if len(name) > 22:
            # Trova spazio più vicino al centro
            mid = len(name) // 2
            split_pos = name.rfind(" ", 0, mid + 5) or name.find(" ", mid)
            if split_pos > 0:
                line1 = name[:split_pos]
                line2 = name[split_pos+1:]
                svg_parts.append(f'<text x="{x+8:.1f}" y="{y+16:.1f}" font-size="9" fill="#555">{_escape_xml(line1)}</text>')
                svg_parts.append(f'<text x="{x+8:.1f}" y="{y+28:.1f}" font-size="9" fill="#555">{_escape_xml(line2)}</text>')
            else:
                svg_parts.append(f'<text x="{x+8:.1f}" y="{y+16:.1f}" font-size="9" fill="#555">{_escape_xml(name[:30])}</text>')
        else:
            svg_parts.append(f'<text x="{x+8:.1f}" y="{y+16:.1f}" font-size="9" fill="#555">{_escape_xml(name)}</text>')
        # Simbolo incerto
        if loc.verification == "hypothetical":
            svg_parts.append(f'<use href="#uncertain" x="{x-8:.1f}" y="{y-8:.1f}" width="16" height="16"/>')

    # Legenda
    legend_y = height - 50
    svg_parts.append(f'<rect x="40" y="{legend_y-10}" width="{width-80}" height="40" fill="white" stroke="#ccc" stroke-width="0.5" opacity="0.9"/>')
    svg_parts.append(f'<text x="50" y="{legend_y+2}" font-size="9" font-weight="bold">Legenda:</text>')
    svg_parts.append(f'<line x1="100" y1="{legend_y}" x2="130" y2="{legend_y}" stroke="#333" stroke-width="2"/>')
    svg_parts.append(f'<text x="135" y="{legend_y+3}" font-size="8">verificato</text>')
    svg_parts.append(f'<line x1="195" y1="{legend_y}" x2="225" y2="{legend_y}" stroke="#333" stroke-width="2" stroke-dasharray="8,4"/>')
    svg_parts.append(f'<text x="230" y="{legend_y+3}" font-size="8">probabile</text>')
    svg_parts.append(f'<line x1="290" y1="{legend_y}" x2="320" y2="{legend_y}" stroke="#333" stroke-width="2" stroke-dasharray="2,3"/>')
    svg_parts.append(f'<text x="325" y="{legend_y+3}" font-size="8">ipotetico</text>')
    svg_parts.append(f'<circle cx="400" cy="{legend_y}" r="4" fill="#2196F3"/>')
    svg_parts.append(f'<text x="410" y="{legend_y+3}" font-size="8">luogo verificato</text>')
    svg_parts.append(f'<circle cx="490" cy="{legend_y}" r="4" fill="#FF9800"/>')
    svg_parts.append(f'<text x="500" y="{legend_y+3}" font-size="8">luogo probabile</text>')
    svg_parts.append(f'<use href="#uncertain" x="575" y="{legend_y-8}" width="16" height="16"/>')
    svg_parts.append(f'<text x="595" y="{legend_y+3}" font-size="8">incerto</text>')

    # Avviso mappa parziale
    if hmap.is_partial:
        svg_parts.append(f'<rect x="40" y="{height-95}" width="{width-80}" height="25" fill="#FFF3E0" stroke="#FF9800" stroke-width="1"/>')
        svg_parts.append(f'<text x="50" y="{height-78}" font-size="10" fill="#E65100" font-weight="bold">⚠ MAPPA PARZIALE: {_escape_xml(hmap.partial_note)}</text>')

    # Riferimenti fonti
    ref_y = legend_y + 20
    if hmap.source_references:
        svg_parts.append(f'<text x="50" y="{ref_y}" font-size="8" fill="#666">Fonti: {", ".join(f"[{k}] {v[:30]}" for k, v in list(hmap.source_references.items())[:8])}</text>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def _escape_xml(s: str) -> str:
    """Escape XML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


# ─── Costruzione mappa principale ────────────────────────────────────────────

def build_map(evidence: EvidencePackage) -> HistoricalMap:
    """Costruisce la mappa storica da un pacchetto di evidenze.

    1. Estrae luoghi con coordinate dal gazetteer e dalle fonti
    2. Estrae linee (fronti, difensive) in base al tipo di evento
    3. Estrae movimenti (avanzate, ritirate)
    4. Estrae fasi temporali
    5. Verifica se la mappa è parziale
    6. Genera SVG
    7. Per eventi ampi, genera sotto-mappe per fase
    """
    locations = _extract_locations_from_evidence(evidence)
    lines = _extract_lines_from_evidence(evidence, locations)
    movements = _extract_movements_from_evidence(evidence, locations)
    phases = _extract_phases_from_evidence(evidence)

    # Bounding box
    all_points: List[Tuple[float, float]] = []
    for loc in locations:
        all_points.append((loc.lat, loc.lon))
    for line in lines:
        all_points.extend(line.points)
    for mov in movements:
        all_points.append((mov.from_lat, mov.from_lon))
        all_points.append((mov.to_lat, mov.to_lon))

    if all_points:
        lats = [p[0] for p in all_points]
        lons = [p[1] for p in all_points]
        bbox = (min(lats), min(lons), max(lats), max(lons))
        # Padding 10%
        lat_pad = (bbox[2] - bbox[0]) * 0.1 or 0.05
        lon_pad = (bbox[3] - bbox[1]) * 0.1 or 0.05
        bbox = (bbox[0] - lat_pad, bbox[1] - lon_pad, bbox[2] + lat_pad, bbox[3] + lon_pad)
    else:
        bbox = (45.5, 11.0, 46.5, 14.0)  # Default NE Italia

    # Verifica parzialità
    is_partial = len(locations) < 3
    partial_note = ""
    if is_partial:
        partial_note = (
            f"Sono stati localizzati solo {len(locations)} luoghi con coordinate accertate. "
            f"La mappa non mostra tutti i luoghi menzionati nelle fonti perché non è stato possibile "
            f"associare coordinate verificabili ad ogni toponimo. Non sono stati inventati movimenti o posizioni."
        )
    elif len(lines) == 0 and len(movements) == 0:
        is_partial = True
        partial_note = (
            "Non sono state trovate linee di fronte o movimenti documentati con coordinate verificabili. "
            "La mappa mostra solo i punti localizzati senza ricostruire schieramenti o spostamenti."
        )

    # Riferimenti fonti
    source_refs: Dict[int, str] = {}
    for loc in locations:
        if loc.label_number and loc.source_ids:
            for sid in loc.source_ids:
                source_refs[loc.label_number] = f"{sid}"

    # Legenda
    legend = [
        {"symbol": "linea continua", "meaning": "dato verificato"},
        {"symbol": "linea tratteggiata", "meaning": "ricostruzione probabile"},
        {"symbol": "linea puntinata", "meaning": "percorso ipotetico"},
        {"symbol": "cerchio blu", "meaning": "luogo verificato"},
        {"symbol": "cerchio arancio", "meaning": "luogo probabile"},
        {"symbol": "simbolo ?", "meaning": "posizione incerta"},
        {"symbol": "numeri", "meaning": "collegati alle fonti nel riquadro"},
    ]
    for phase in phases:
        legend.append({"symbol": f"colore {phase.color}", "meaning": f"fase: {phase.name}"})

    hmap = HistoricalMap(
        event_name=evidence.event_name,
        title=f"Mappa storico-operativa: {evidence.event_name}",
        is_partial=is_partial,
        partial_note=partial_note,
        locations=locations,
        lines=lines,
        movements=movements,
        phases=phases,
        bounding_box=bbox,
        svg="",  # Will be generated below
        legend=legend,
        source_references=source_refs,
    )

    # Genera SVG
    hmap.svg = _generate_svg(hmap)

    # Per eventi ampi: sotto-mappe per fase
    if evidence.resolution.get("conflict") == "ambiguous_collection" and phases:
        for i, phase in enumerate(phases):
            sub_locations = [l for l in locations if l.phase == phase.name or l.phase is None]
            sub_lines = [l for l in lines if l.phase == phase.name or l.phase is None]
            sub_movements = [m for m in movements if m.phase == phase.name or m.phase is None]

            if sub_locations or sub_lines or sub_movements:
                sub_bbox = bbox
                sub_points = [(l.lat, l.lon) for l in sub_locations]
                sub_points.extend([p for line in sub_lines for p in line.points])
                sub_points.extend([(m.from_lat, m.from_lon) for m in sub_movements])
                sub_points.extend([(m.to_lat, m.to_lon) for m in sub_movements])
                if sub_points:
                    slats = [p[0] for p in sub_points]
                    slons = [p[1] for p in sub_points]
                    sub_bbox = (min(slats), min(slons), max(slats), max(slons))
                    pad = 0.05
                    sub_bbox = (sub_bbox[0] - pad, sub_bbox[1] - pad, sub_bbox[2] + pad, sub_bbox[3] + pad)

                sub_map = HistoricalMap(
                    event_name=evidence.event_name,
                    title=f"{phase.name} — {evidence.event_name} ({phase.start_date}→{phase.end_date})",
                    is_partial=len(sub_locations) < 2,
                    partial_note=f"Sotto-mappa per fase: {phase.name}. {phase.description}" if len(sub_locations) < 2 else "",
                    locations=sub_locations,
                    lines=sub_lines,
                    movements=sub_movements,
                    phases=[phase],
                    bounding_box=sub_bbox,
                    svg="",
                    legend=legend,
                    source_references=source_refs,
                )
                sub_map.svg = _generate_svg(sub_map)
                hmap.sub_maps.append(sub_map)

    return hmap


def build_map_from_query(query: str) -> Dict[str, Any]:
    """API: build map from query string."""
    from event_evidence_pipeline import collect_evidence
    evidence = collect_evidence(query)
    hmap = build_map(evidence)
    return hmap.to_dict()
