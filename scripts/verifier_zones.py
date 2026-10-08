"""Compare les coordonnées de data/zones.yaml à OpenStreetMap (service Nominatim).

  python -m scripts.verifier_zones

Ne modifie aucun fichier : affiche l'écart pour chaque zone. Corrigez ensuite zones.yaml
à la main et passez coords_verified à true. Une requête par seconde (règle d'usage de Nominatim).
"""
import time

import httpx

from app.zones import Gazetteer, _distance_km

URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "yegle-hackathon/0.1 (verification des zones)"}


def main() -> None:
    for zone in Gazetteer.load().zones:
        try:
            r = httpx.get(URL, params={"q": f"{zone.name}, Dakar, Sénégal", "format": "json", "limit": 1},
                          headers=HEADERS, timeout=15)
            r.raise_for_status()
            hits = r.json()
        except httpx.HTTPError as e:
            print(f"{zone.name:32} erreur réseau : {type(e).__name__}")
            continue
        if not hits:
            print(f"{zone.name:32} introuvable sur OpenStreetMap")
        else:
            lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
            gap = _distance_km(zone.lat, zone.lon, lat, lon)
            flag = "OK       " if gap < 1 else "À CORRIGER"
            print(f"{zone.name:32} {flag} écart {gap:4.1f} km   OSM : lat {lat:.4f}, lon {lon:.4f}")
        time.sleep(1.1)


if __name__ == "__main__":
    main()
