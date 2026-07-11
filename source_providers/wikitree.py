"""WikiTree API provider — genealogia collaborativa globale.

API: https://api.wikitree.com/api.php
Action: searchPerson (pubblica, no auth necessaria per profili pubblici)
Docs: https://github.com/wikitree/wikitree-api

WikiTree contiene ~40M+ profili genealogici, inclusi militari WW1/WW2.
I profili pubblici (nati >150 anni fa o deceduti) sono accessibili senza auth.
"""

from typing import Dict, List

import requests

from .base import SourceProvider


class ProviderWikiTree(SourceProvider):
    """WikiTree — genealogia collaborativa con profili militari."""

    name = "wikitree"
    display_name = "WikiTree"
    country = "Globale"
    archive_name = "WikiTree"
    base_url = "https://www.wikitree.com"
    authorized_domains = {"api.wikitree.com", "www.wikitree.com"}
    cache_ttl_days = 120

    def search(self, query: str, filters: dict = None) -> List[dict]:
        """Cerca profili WikiTree per nome.

        Estrae nome/cognome dalla query e usa searchPerson API.
        filters puo' contenere: birth_date, death_date, birth_location, death_location
        """
        parts = query.strip().split()
        if len(parts) < 1:
            return []

        # estrai nome e cognome
        last_name = parts[0] if parts else ""
        first_name = parts[1] if len(parts) > 1 else ""

        # se la query ha piu' di 2 parole, potrebbe essere cognome + nome composto
        if len(parts) > 2:
            first_name = " ".join(parts[1:])

        params = {
            "action": "searchPerson",
            "LastName": last_name,
            "fields": "Id,Name,FirstName,LastNameAtBirth,LastNameCurrent,"
                      "BirthDate,DeathDate,BirthLocation,DeathLocation,"
                      "Gender,IsLiving,PhotoData,Derived.BirthName,Derived.LongName",
            "limit": 10,
        }
        if first_name:
            params["FirstName"] = first_name

        # filtri aggiuntivi
        if filters:
            if filters.get("birth_date"):
                params["BirthDate"] = filters["birth_date"]
            if filters.get("death_date"):
                params["DeathDate"] = filters["death_date"]
            if filters.get("birth_location"):
                params["BirthLocation"] = filters["birth_location"]
            if filters.get("death_location"):
                params["DeathLocation"] = filters["death_location"]

        try:
            resp = requests.get(
                "https://api.wikitree.com/api.php",
                params=params,
                timeout=20,
                headers={"Accept": "application/json"},
                verify=False,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            if not data or not isinstance(data, list):
                return []

            results = []
            for entry in data:
                if entry.get("status", 0) != 0:
                    continue
                matches = entry.get("matches", [])
                for m in matches:
                    if not m.get("Name"):
                        continue

                    wt_name = m.get("Name", "")
                    first = m.get("FirstName", "")
                    last_birth = m.get("LastNameAtBirth", "")
                    last_current = m.get("LastNameCurrent", "")
                    birth_date = m.get("BirthDate", "")
                    death_date = m.get("DeathDate", "")
                    birth_loc = m.get("BirthLocation", "")
                    death_loc = m.get("DeathLocation", "")
                    is_living = m.get("IsLiving", 0)

                    # salta profili viventi (privacy)
                    if is_living:
                        continue

                    # costruisci titolo
                    full_name = f"{first} {last_birth}".strip()
                    title = f"WikiTree: {full_name} ({wt_name})"

                    # descrizione con date e luoghi
                    desc_parts = []
                    if birth_date and birth_date != "0000-00-00":
                        desc_parts.append(f"Nato: {birth_date}")
                    if birth_loc:
                        desc_parts.append(f"a {birth_loc}")
                    if death_date and death_date != "0000-00-00":
                        desc_parts.append(f"Deceduto: {death_date}")
                    if death_loc:
                        desc_parts.append(f"a {death_loc}")
                    description = " · ".join(desc_parts) if desc_parts else "Profilo genealogico WikiTree"

                    # thumbnail se disponibile
                    photo = m.get("PhotoData", {})
                    thumbnail = ""
                    if photo and isinstance(photo, dict):
                        thumbnail = photo.get("url", "")
                        if thumbnail and not thumbnail.startswith("http"):
                            thumbnail = f"https://www.wikitree.com{thumbnail}"

                    # confidence: alto se match esatto cognome+nome
                    confidence = 0.6
                    if first_name and first.lower() == first.lower():
                        confidence = 0.75
                    if birth_date and birth_date != "0000-00-00":
                        confidence = min(confidence + 0.1, 0.9)

                    results.append({
                        "provider": self.name,
                        "provider_record_id": wt_name,
                        "archivio": "WikiTree",
                        "titolo": title,
                        "description": description,
                        "source_type": "genealogy_profile",
                        "catalog_url": f"https://www.wikitree.com/wiki/{wt_name}",
                        "direct_url": f"https://www.wikitree.com/wiki/{wt_name}",
                        "thumbnail": thumbnail,
                        "access_type": "online",
                        "downloadable": False,
                        "confidence": confidence,
                        "persone_possibili": full_name,
                        "data_inizio": birth_date if birth_date and birth_date != "0000-00-00" else "",
                        "luogo": birth_loc,
                    })

            return results

        except Exception:
            return []

    def get_metadata(self, record_id: str) -> dict:
        """Recupera metadati dettagliati per un profilo WikiTree."""
        try:
            resp = requests.get(
                "https://api.wikitree.com/api.php",
                params={
                    "action": "getProfile",
                    "key": record_id,
                    "fields": "Id,Name,FirstName,LastNameAtBirth,LastNameCurrent,"
                              "BirthDate,DeathDate,BirthLocation,DeathLocation,"
                              "Gender,Bio,PhotoData",
                },
                timeout=20,
                headers={"Accept": "application/json"},
                verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and data[0].get("status", 0) == 0:
                    return data[0].get("profile", {})
        except Exception:
            pass
        return {"provider": self.name, "access_type": "online"}

    def get_person_bio(self, record_id: str) -> str:
        """Recupera la biografia testuale di un profilo."""
        try:
            resp = requests.get(
                "https://api.wikitree.com/api.php",
                params={"action": "getBio", "key": record_id},
                timeout=20,
                headers={"Accept": "application/json"},
                verify=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and data[0].get("status", 0) == 0:
                    return data[0].get("bio", "")
        except Exception:
            pass
        return ""
