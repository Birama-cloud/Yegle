"""Répertoire des zones : reconnaître un lieu dit par le citoyen, sans jamais inventer."""
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.text import contains_phrase, norm
from config import settings


@dataclass
class Zone:
    id: str
    name: str
    type: str                 # commune | departement
    departement: str
    region: str
    aliases: list = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    coords_verified: bool = False

    @property
    def is_commune(self) -> bool:
        return self.type == "commune"


class Gazetteer:
    def __init__(self, zones: list[Zone]):
        self.zones = zones
        self.by_id = {z.id: z for z in zones}

    @classmethod
    def load(cls, path: Path | None = None) -> "Gazetteer":
        raw = yaml.safe_load(Path(path or settings.ZONES_FILE).read_text(encoding="utf-8")) or []
        return cls([Zone(**z) for z in raw])

    def get(self, zone_id: str | None) -> Zone | None:
        return self.by_id.get(zone_id or "")

    def resolve(self, text: str | None) -> tuple[Zone | None, float]:
        """Cherche une zone connue dans un texte. Renvoie (zone, confiance).

        Confiance : 0.9 commune, 0.5 zone trop large, 0.3 lieu dit mais inconnu, 0 rien.
        L'expression la plus longue l'emporte ("grand yoff" avant "yoff").
        """
        haystack = norm(text or "")
        if not haystack:
            return None, 0.0
        best, best_len = None, 0
        for zone in self.zones:
            for alias in [zone.name, *zone.aliases]:
                phrase = norm(alias)
                if len(phrase) > best_len and contains_phrase(haystack, phrase):
                    best, best_len = zone, len(phrase)
        if best is None:
            return None, 0.3
        return best, 0.9 if best.is_commune else 0.5

    def nearest(self, lat: float, lon: float, max_km: float = 3.0) -> Zone | None:
        """Commune dont le centre est le plus proche d'une position GPS fournie par le citoyen."""
        best, best_d = None, max_km
        for zone in self.zones:
            if not zone.is_commune or zone.lat is None or zone.lon is None:
                continue
            d = _distance_km(lat, lon, zone.lat, zone.lon)
            if d <= best_d:
                best, best_d = zone, d
        return best


def _distance_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def covers(coverage: list[str], zone: Zone | None) -> bool | None:
    """True : zone couverte. False : zone connue mais hors couverture. None : zone inconnue."""
    if "national" in coverage:
        return True
    if zone is None:
        return None
    return any(c in (f"region:{zone.region}", f"departement:{zone.departement}", f"zone:{zone.id}")
               for c in coverage)
