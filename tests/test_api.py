import json

import pytest
from fastapi.testclient import TestClient

from api import main

ADMIN = {"X-API-Key": "cle-de-test"}


@pytest.fixture
def client(assistant, monkeypatch):
    monkeypatch.setattr(main, "get_assistant", lambda: assistant)
    return TestClient(main.app)


def test_parcours_par_l_api(client):
    assert client.get("/health").json()["knowledge_errors"] == []
    assert "eau" in [c["id"] for c in client.get("/api/categories").json()]

    r1 = client.post("/api/analyze", json={"text": "Il y a une fuite d'eau dans ma rue"}).json()
    assert r1["kind"] == "clarify"
    r2 = client.post("/api/analyze", json={"text": "À Grand-Yoff", "draft": r1["draft"],
                                           "draft_token": r1["draft_token"]}).json()
    assert r2["kind"] == "confirm" and r2["routing"]["organization"]["org_name"] == "SEN'EAU"

    created = client.post("/api/reports", json={"draft": r2["draft"], "draft_token": r2["draft_token"]})
    assert created.status_code == 201
    ref = created.json()["report"]["reference"]
    assert "transcript" not in created.json()["report"]            # vue publique uniquement
    assert client.get(f"/api/reports/{ref}").json()["status"] == "ROUTED"
    assert client.get("/api/reports/YGL-000000-XXXXXX").status_code == 404


def test_entrees_refusees(client):
    assert client.post("/api/analyze", json={"text": ""}).status_code == 422
    assert client.post("/api/analyze", json={"text": "x", "language": "zz"}).status_code == 422
    assert client.post("/api/analyze", json={"text": "x", "latitude": 400, "longitude": 0}).status_code == 422
    assert client.post("/api/reports", json={"draft": {"category": "inventee"}}).status_code == 422
    r = client.post("/api/analyze/audio", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 415


@pytest.mark.parametrize("bad", [
    {"category": "eau", "description": "x" * 301},              # texte trop long
    {"category": "eau", "description": "fuite", "transcript": 42},
    {"category": "eau", "description": "fuite", "latitude": "abc", "longitude": 0},
    {"category": "eau", "description": "fuite", "latitude": 95, "longitude": 0},
    {"category": "eau", "description": "fuite", "urgency": "apocalypse"},
    {"category": "eau", "description": "fuite", "confidence_problem": 7},
    {"category": "eau", "description": "fuite", "asked": ["nimporte"]},
    {"category": ["eau"], "description": "fuite"},
])
def test_brouillon_malforme_refuse_sans_erreur_serveur(client, bad):
    assert client.post("/api/reports", json={"draft": bad}).status_code == 422
    assert client.post("/api/analyze", json={"text": "à Ouakam", "draft": bad}).status_code == 422
    r = client.post("/api/analyze/audio", data={"draft": json.dumps(bad)},
                    files={"file": ("a.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 422
    assert client.get("/api/admin/reports", headers=ADMIN).json() == []


def test_brouillon_cles_inconnues_ignorees(client):
    r = client.post("/api/analyze", json={"text": "Fuite d'eau à Ouakam"}).json()
    draft = {**r["draft"], "org_id": "ORG_PIRATE", "responsible_organization": {"id": "ORG_PIRATE"}}
    created = client.post("/api/reports", json={"draft": draft, "draft_token": r["draft_token"]})
    ref = created.json()["report"]["reference"]
    assert client.get(f"/api/admin/reports/{ref}", headers=ADMIN).json()["report"]["org_id"] == "ORG_SENEAU"


@pytest.mark.parametrize("change", [
    {"confidence_problem": 1.0},            # se donner une confiance
    {"category": "electricite"},            # changer de catégorie après l'analyse
    {"description": "Autre chose"},
    {"location_text": "Médina"},
])
def test_brouillon_modifie_par_le_client_refuse(client, change):
    r = client.post("/api/analyze", json={"text": "Il y a une fuite d'eau dans ma rue"}).json()
    forged = {**r["draft"], **change}
    assert client.post("/api/reports", json={"draft": forged, "draft_token": r["draft_token"]}).status_code == 422
    assert client.post("/api/analyze", json={"text": "À Ouakam", "draft": forged,
                                             "draft_token": r["draft_token"]}).status_code == 422
    audio = client.post("/api/analyze/audio", data={"draft": json.dumps(forged), "draft_token": r["draft_token"]},
                        files={"file": ("a.wav", b"RIFF", "audio/wav")})
    assert audio.status_code == 422
    assert client.get("/api/admin/reports", headers=ADMIN).json() == []


def test_brouillon_sans_signature_ou_d_un_autre_echange_refuse(client):
    a = client.post("/api/analyze", json={"text": "Fuite d'eau à Ouakam"}).json()
    b = client.post("/api/analyze", json={"text": "Lampadaire en panne à Ouakam"}).json()
    assert client.post("/api/reports", json={"draft": a["draft"]}).status_code == 422
    assert client.post("/api/reports", json={"draft": a["draft"], "draft_token": b["draft_token"]}).status_code == 422
    assert client.post("/api/reports", json={"draft": a["draft"], "draft_token": a["draft_token"]}).status_code == 201


def test_administration_protegee(client, monkeypatch):
    assert client.get("/api/admin/reports").status_code == 401
    assert client.get("/api/admin/reports", headers={"X-API-Key": "faux"}).status_code == 401
    monkeypatch.setattr(main.settings, "ADMIN_API_KEY", "")
    assert client.get("/api/admin/reports", headers=ADMIN).status_code == 503


def test_administration(client):
    r = client.post("/api/analyze", json={"text": "Lampadaire en panne à Ouakam"}).json()
    ref = client.post("/api/reports", json={"draft": r["draft"], "draft_token": r["draft_token"]}
                      ).json()["report"]["reference"]

    assert len(client.get("/api/admin/reports", headers=ADMIN).json()) == 1
    assert client.get("/api/admin/reports?category=eau", headers=ADMIN).json() == []
    detail = client.get(f"/api/admin/reports/{ref}", headers=ADMIN).json()
    assert detail["report"]["org_name"] == "Ville de Dakar" and len(detail["routing"]) == 1

    url = f"/api/admin/reports/{ref}"
    assert client.patch(f"{url}/status", json={"status": "CLOSED"}, headers=ADMIN).status_code == 409
    assert client.patch(f"{url}/status", json={"status": "IN_PROGRESS"}, headers=ADMIN).json()["status"] == "IN_PROGRESS"
    assert client.post(f"{url}/reroute", json={"organization_id": "ORG_X", "reason": "test"},
                       headers=ADMIN).status_code == 409
    moved = client.post(f"{url}/reroute", json={"organization_id": "ORG_SENELEC", "reason": "Poteau SENELEC"},
                        headers=ADMIN).json()
    assert moved["org_name"] == "SENELEC" and moved["status"] == "ROUTED"
    assert client.get("/api/admin/stats", headers=ADMIN).json()["total"] == 1
    assert len(client.get("/api/admin/organizations", headers=ADMIN).json()) == 6
