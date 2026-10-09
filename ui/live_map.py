"""Carte en direct des signalements, pour le tableau de bord.

Un point par signalement : à la position GPS fournie par le citoyen, sinon au centre de la commune
reconnue, légèrement décalé pour que les signalements d'une même commune ne s'empilent pas.
Couleur selon l'état, taille selon l'urgence, halo pour les signalements récents.
"""
import hashlib
import html
import math
from datetime import datetime, timedelta, timezone

import pydeck as pdk

REFRESH_S = 15
RECENT = timedelta(minutes=15)
SPREAD_M = 250                    # écart maximal autour du centre de la commune
DAKAR = {"latitude": 14.72, "longitude": -17.46, "zoom": 11}

# (étiquette de légende, couleur RGB)
TONES = {
    "alert": ("Alerte d'urgence en attente", (179, 38, 30)),
    "review": ("À vérifier par l'équipe", (224, 168, 0)),
    "open": ("Chez les services", (27, 42, 107)),
    "solved": ("Résolu", (23, 121, 76)),
    "closed": ("Rejeté", (92, 100, 128)),
}
STATUS_TONE = {"RECEIVED": "review", "NEEDS_REVIEW": "review", "ROUTED": "open", "ASSIGNED": "open",
               "IN_PROGRESS": "open", "RESOLVED": "solved", "CLOSED": "solved", "REJECTED": "closed"}
URGENCY_RADIUS = {"low": 70, "medium": 90, "high": 120, "critical": 160}    # mètres


def _spread(reference: str, lat: float, lon: float) -> tuple[float, float]:
    """Décalage stable (toujours le même pour une référence) de 0 à SPREAD_M mètres."""
    h = hashlib.sha1(reference.encode()).digest()
    angle, dist = h[0] / 255 * 2 * math.pi, math.sqrt(h[1] / 255) * SPREAD_M
    return (lat + dist * math.cos(angle) / 111_320,
            lon + dist * math.sin(angle) / (111_320 * math.cos(math.radians(lat))))


def map_points(reports: list[dict], gazetteer, alert_refs: set, labels: dict, now: datetime | None = None
               ) -> list[dict]:
    """Points à afficher. Textes échappés : l'infobulle de la carte les insère comme du HTML."""
    now = now or datetime.now(timezone.utc)
    points = []
    for r in reports:
        zone = gazetteer.get(r["zone_id"])
        if r["latitude"] is not None and r["longitude"] is not None:
            lat, lon, where = r["latitude"], r["longitude"], "position GPS"
        elif zone and zone.lat is not None:
            lat, lon = _spread(r["reference"], zone.lat, zone.lon)
            where = f"vers le centre de {zone.name}"
        else:
            continue
        tone = "alert" if r["reference"] in alert_refs else STATUS_TONE.get(r["status"], "open")
        created = datetime.fromisoformat(r["created_at"])
        points.append({
            "lat": lat, "lon": lon, "color": [*TONES[tone][1], 220],
            "radius": URGENCY_RADIUS.get(r["urgency"], 90), "recent": now - created <= RECENT,
            "reference": html.escape(r["reference"]),
            "description": html.escape((r["description"] or "")[:90]),
            "place": html.escape(r["location_text"] or r["territorial_area"] or "lieu non précisé"),
            "where": html.escape(where),
            "status": html.escape(labels["status"].get(r["status"], r["status"])),
            "urgency": html.escape(labels["urgency"].get(r["urgency"], r["urgency"])),
            "org": html.escape(r["org_name"] or "à déterminer"),
            "when": created.strftime("%d/%m à %H:%M"),
        })
    return points


def deck(points: list[dict]) -> pdk.Deck:
    layers = [
        pdk.Layer("ScatterplotLayer", [p for p in points if p["recent"]], id="recents",
                  get_position="[lon, lat]", get_radius="radius * 2.2", radius_min_pixels=14,
                  filled=False, stroked=True, get_line_color=[255, 198, 41, 255], line_width_min_pixels=3),
        pdk.Layer("ScatterplotLayer", points, id="signalements", pickable=True,
                  get_position="[lon, lat]", get_radius="radius", radius_min_pixels=6, radius_max_pixels=30,
                  get_fill_color="color", stroked=True, get_line_color=[255, 255, 255, 230],
                  line_width_min_pixels=1.5),
    ]
    tooltip = {
        "html": "<b>{reference}</b> · {status}<br/>{description}<br/><span>{place}</span><br/>"
                "Priorité : {urgency} · Organisme : {org}<br/><span>Reçu le {when}, {where}</span>",
        "style": {"backgroundColor": "#141A33", "color": "white", "fontSize": "13px", "maxWidth": "320px"},
    }
    return pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(**DAKAR), tooltip=tooltip,
                    map_provider="carto", map_style=pdk.map_styles.CARTO_LIGHT)


def legend_html() -> str:
    items = "".join(f"<span><i style='background:rgb{color}'></i>{html.escape(label)}</span>"
                    for label, color in TONES.values())
    return (f"<div class='yg-legend'>{items}<span><i class='ring'></i>Reçu il y a moins de 15 min</span>"
            "<span>Taille : priorité</span></div>")
