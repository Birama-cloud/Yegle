import httpx
import pytest

from app import alerts
from app.assistant import Assistant
from app.knowledge import Knowledge
from app.storage import Storage, StorageError

CABLE = {"category": "electricite", "description": "Câble électrique tombé sur la chaussée",
         "transcript": "Un câble est tombé, mon voisin s'appelle Moussa", "location_text": "Médina",
         "urgency": "critical", "confidence_problem": 0.9}


def test_urgence_critique_cree_une_alerte(assistant):
    report = assistant.submit(CABLE).report
    [alert] = assistant.storage.list_alerts()
    assert alert["reference"] == report["reference"] and alert["org_name"] == "SENELEC"
    assert "critique" in alert["reason"] and alert["acknowledged_at"] is None


def test_urgence_critique_alerte_meme_sans_organisme(unverified, gazetteer):
    a = Assistant(llm=None, knowledge=unverified, gazetteer=gazetteer, storage=Storage(":memory:"))
    report = a.submit(CABLE).report
    assert report["status"] == "NEEDS_REVIEW" and len(a.storage.list_alerts()) == 1


def test_urgence_ordinaire_pas_d_alerte(assistant):
    assistant.submit({**CABLE, "urgency": "high"})
    assistant.submit({**CABLE, "urgency": "medium"})
    assert assistant.storage.list_alerts() == []


def test_regle_d_escalade_de_l_organisme(assistant):
    assistant.knowledge.get_org("ORG_SENELEC").escalation_rules = [
        {"when_urgency": ["high"], "action": "notify_admin"}]
    assistant.submit({**CABLE, "urgency": "high"})
    [alert] = assistant.storage.list_alerts()
    assert "Règle d'escalade de SENELEC" in alert["reason"]


def test_une_seule_alerte_par_signalement(assistant):
    report = assistant.submit(CABLE).report
    assert alerts.escalate(assistant.storage, assistant.knowledge, report) is None
    assert len(assistant.storage.list_alerts(open_only=False)) == 1


def test_prise_en_charge_tracee(assistant):
    assistant.submit(CABLE)
    [alert] = assistant.storage.list_alerts()
    done = assistant.storage.acknowledge_alert(alert["id"], "admin:Awa")
    assert done["acknowledged_by"] == "admin:Awa" and done["acknowledged_at"]
    assert assistant.storage.list_alerts() == [] and len(assistant.storage.list_alerts(open_only=False)) == 1
    with pytest.raises(StorageError, match="déjà prise en charge par admin:Awa"):
        assistant.storage.acknowledge_alert(alert["id"], "admin:Bob")


class FakeResponse:
    def __init__(self, status):
        self.status_code, self.is_success = status, 200 <= status < 300


def test_webhook_envoye_sans_donnee_personnelle(assistant, monkeypatch):
    sent = []
    monkeypatch.setattr(alerts.settings, "ALERT_WEBHOOK_URL", "https://alertes.example/hook")
    monkeypatch.setattr(alerts.httpx, "post", lambda url, json, timeout: sent.append(json) or FakeResponse(200))
    assistant.submit(CABLE)
    [alert] = assistant.storage.list_alerts()
    assert alert["notified"] == 1 and alert["notify_error"] is None
    assert "Médina" in sent[0]["text"] and "Moussa" not in str(sent[0])     # pas de transcription


@pytest.mark.parametrize("url, post, expected", [
    ("https://alertes.example/hook", lambda *a, **k: FakeResponse(500), "HTTP 500"),
    ("https://alertes.example/hook", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectTimeout("x")), "ConnectTimeout"),
    ("http://alertes.example/hook", None, "https://"),
])
def test_webhook_en_echec_trace_sans_bloquer(assistant, monkeypatch, url, post, expected):
    monkeypatch.setattr(alerts.settings, "ALERT_WEBHOOK_URL", url)
    monkeypatch.setattr(alerts.httpx, "post", post or (lambda *a, **k: pytest.fail("appel non sécurisé")))
    assert assistant.submit(CABLE).kind == "done"
    [alert] = assistant.storage.list_alerts()
    assert alert["notified"] == 0 and expected in alert["notify_error"]


def test_validation_des_regles_d_escalade(knowledge):
    org = knowledge.get_org("ORG_SENEAU")
    org.escalation_rules = [{"when_urgency": ["critical"], "action": "envoyer_un_pigeon"},
                            {"when_urgency": ["tres_grave"], "action": "notify_admin"}]
    errors = " | ".join(Knowledge(list(knowledge.categories.values()), knowledge.organizations).validate())
    assert "action inconnue" in errors and "when_urgency" in errors
