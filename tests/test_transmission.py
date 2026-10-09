"""Transmission : quoi qu'il arrive pendant l'envoi, le signalement n'est ni perdu ni bloqué en « Reçu »."""
import httpx
import pytest

from app import transmission
from app.assistant import Assistant
from app.storage import Storage

FUITE = {"category": "eau", "description": "Fuite d'eau", "transcript": "Fuite devant chez Awa Diop",
         "location_text": "Médina", "confidence_problem": 0.9}


class FakeResponse:
    def __init__(self, status):
        self.status_code, self.is_success = status, 200 <= status < 300


@pytest.fixture
def webhook(assistant):
    org = assistant.knowledge.get_org("ORG_SENEAU")
    org.transmission_mode, org.api_endpoint = "webhook", "https://seneau.example/hook"
    return assistant


def _raise(error):
    def post(*args, **kwargs):
        raise error
    return post


def test_webhook_reussi(webhook, monkeypatch):
    sent = []
    monkeypatch.setattr(transmission.httpx, "post", lambda url, json, timeout: sent.append(json) or FakeResponse(200))
    done = webhook.submit(FUITE)
    assert done.report["status"] == "ROUTED" and "SEN'EAU" in done.message
    assert "transcript" not in sent[0] and "Awa" not in str(sent[0])


@pytest.mark.parametrize("post, error", [
    (lambda *a, **k: FakeResponse(503), "HTTP 503"),
    (_raise(httpx.ConnectTimeout("délai")), "ConnectTimeout"),
    (_raise(httpx.InvalidURL("adresse")), "InvalidURL"),          # pas une httpx.HTTPError
    (_raise(ValueError("imprévu")), "ValueError"),
])
def test_echec_d_envoi_trace_et_mis_en_verification(webhook, monkeypatch, post, error):
    monkeypatch.setattr(transmission.httpx, "post", post)
    done = webhook.submit(FUITE)
    assert done.kind == "done" and "vérifier" in done.message
    ref = done.report["reference"]
    [sent] = webhook.storage.history(ref)["transmissions"]
    assert sent["success"] == 0 and error in sent["error"]
    assert webhook.storage.get(ref)["status"] == "NEEDS_REVIEW"


def test_webhook_non_securise_jamais_appele(webhook, monkeypatch):
    webhook.knowledge.get_org("ORG_SENEAU").api_endpoint = "http://seneau.example/hook"
    monkeypatch.setattr(transmission.httpx, "post", lambda *a, **k: pytest.fail("appel non sécurisé"))
    done = webhook.submit(FUITE)
    assert done.report["status"] == "NEEDS_REVIEW"


def test_erreur_imprevue_dans_la_transmission(assistant, monkeypatch):
    monkeypatch.setattr(transmission, "transmit", _raise(RuntimeError("panne")))
    done = assistant.submit({**FUITE, "urgency": "critical"})
    assert done.kind == "done" and "vérifier" in done.message
    ref = done.report["reference"]
    statuses = assistant.storage.history(ref)["statuses"]
    assert statuses[-1]["new_status"] == "NEEDS_REVIEW" and "RuntimeError" in statuses[-1]["note"]
    assert len(assistant.storage.list_alerts()) == 1          # l'alerte part quand même


def test_mise_en_verification_atomique_a_la_creation(unverified, gazetteer):
    a = Assistant(llm=None, knowledge=unverified, gazetteer=gazetteer, storage=Storage(":memory:"))
    ref = a.submit(FUITE).report["reference"]
    assert [s["new_status"] for s in a.storage.history(ref)["statuses"]] == ["RECEIVED", "NEEDS_REVIEW"]


def test_signalements_interrompus_repris_au_demarrage(verified, gazetteer, tmp_path):
    path = tmp_path / "base.sqlite"
    storage = Storage(path)
    a = Assistant(llm=None, knowledge=verified, gazetteer=gazetteer, storage=storage)
    old = storage.create_report(FUITE, a._route(dict(FUITE)))["reference"]     # arrêt juste après la création
    recent = storage.create_report(FUITE, a._route(dict(FUITE)))["reference"]
    with storage.transaction():
        storage.db.execute("UPDATE reports SET created_at = '2026-01-01T00:00:00+00:00' WHERE reference = ?", (old,))

    Assistant(llm=None, knowledge=verified, gazetteer=gazetteer, storage=Storage(path))   # redémarrage
    assert storage.get(old)["status"] == "NEEDS_REVIEW"
    assert storage.history(old)["statuses"][-1]["note"].startswith("Transmission interrompue")
    assert storage.get(recent)["status"] == "RECEIVED"        # peut-être encore en cours d'envoi


def test_reorientation_en_cours_de_traitement_vers_un_webhook_en_panne(webhook, monkeypatch):
    ref = webhook.submit({**FUITE, "category": "electricite"}).report["reference"]
    webhook.storage.set_status(ref, "IN_PROGRESS", "admin:Awa")
    monkeypatch.setattr(transmission.httpx, "post", _raise(httpx.ConnectError("hors ligne")))
    report = webhook.reroute(ref, "ORG_SENEAU", "admin:Awa", "C'est une conduite d'eau")
    assert report["status"] == "NEEDS_REVIEW"
    assert webhook.storage.history(ref)["transmissions"][-1]["error"] == "ConnectError"
