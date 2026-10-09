from datetime import datetime, timedelta, timezone

from app.zones import _distance_km
from ui import live_map

LABELS = {"status": {"ROUTED": "Orienté"}, "urgency": {"medium": "Moyenne"}}
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def _report(ref="YGL-261009-AAAAAA", **values):
    return {"reference": ref, "zone_id": "ouakam", "latitude": None, "longitude": None, "status": "ROUTED",
            "urgency": "medium", "created_at": (NOW - timedelta(hours=2)).isoformat(), "description": "Fuite",
            "location_text": "Ouakam", "territorial_area": "Ouakam", "org_name": "SEN'EAU", **values}


def test_point_pres_du_centre_de_la_commune_et_stable(gazetteer):
    ouakam = gazetteer.get("ouakam")
    [p] = live_map.map_points([_report()], gazetteer, set(), LABELS, NOW)
    assert _distance_km(p["lat"], p["lon"], ouakam.lat, ouakam.lon) <= live_map.SPREAD_M / 1000
    assert live_map.map_points([_report()], gazetteer, set(), LABELS, NOW)[0]["lat"] == p["lat"]


def test_signalements_d_une_meme_commune_ne_s_empilent_pas(gazetteer):
    points = live_map.map_points([_report(f"YGL-261009-AAAAA{i}") for i in range(2, 9)], gazetteer, set(),
                                 LABELS, NOW)
    assert len({(p["lat"], p["lon"]) for p in points}) == 7


def test_position_gps_utilisee_telle_quelle(gazetteer):
    [p] = live_map.map_points([_report(latitude=14.7, longitude=-17.45)], gazetteer, set(), LABELS, NOW)
    assert (p["lat"], p["lon"], p["where"]) == (14.7, -17.45, "position GPS")


def test_sans_lieu_reconnu_pas_de_point(gazetteer):
    assert live_map.map_points([_report(zone_id=None)], gazetteer, set(), LABELS, NOW) == []


def test_couleurs_taille_et_recents(gazetteer):
    reports = [_report("A", status="NEEDS_REVIEW"), _report("B", urgency="critical"),
               _report("C", created_at=(NOW - timedelta(minutes=5)).isoformat())]
    a, b, c = live_map.map_points(reports, gazetteer, {"B"}, LABELS, NOW)
    assert a["color"][:3] == list(live_map.TONES["review"][1])
    assert b["color"][:3] == list(live_map.TONES["alert"][1]) and b["radius"] > a["radius"]
    assert c["recent"] and not a["recent"]


def test_textes_de_l_infobulle_echappes(gazetteer):
    [p] = live_map.map_points([_report(location_text="<img src=x onerror=alert(1)>")], gazetteer, set(),
                              LABELS, NOW)
    assert "<img" not in p["place"] and "&lt;img" in p["place"]


def test_carte_sans_jeton_mapbox(gazetteer):
    deck = live_map.deck(live_map.map_points([_report()], gazetteer, set(), LABELS, NOW))
    assert deck.map_provider == "carto" and len(deck.layers) == 2
