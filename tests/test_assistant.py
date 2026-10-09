import json

import pytest

from app.assistant import Assistant
from app.storage import Storage, StorageError
from app.understanding import validate


def test_parcours_complet_en_deux_messages(assistant):
    t1 = assistant.analyze(None, text="Il y a une grosse fuite d'eau dans ma rue depuis ce matin")
    assert t1.kind == "clarify" and "Où se trouve" in t1.message

    t2 = assistant.analyze(t1.draft, text="À Grand-Yoff, près du marché")
    assert t2.kind == "confirm" and "SEN'EAU" in t2.message and "Grand-Yoff, près du marché" in t2.message
    assert t2.draft["category"] == "eau" and t2.draft["zone_id"] == "grand-yoff"

    done = assistant.submit(t2.draft)
    assert done.kind == "done" and done.report["status"] == "ROUTED"
    assert done.report["reference"].startswith("YGL-") and done.report["reference"] in done.message
    history = assistant.storage.history(done.report["reference"])
    assert [s["new_status"] for s in history["statuses"]] == ["RECEIVED", "ROUTED"]
    assert history["transmissions"][0]["channel"] == "internal_queue" and history["transmissions"][0]["success"]
    assert history["routing"][0]["rule_id"] == "R_EAU_01"


def test_un_seul_message_suffit_si_le_lieu_est_dit(assistant):
    t = assistant.analyze(None, text="Le lampadaire est en panne à Ouakam")
    assert t.kind == "confirm" and "Ville de Dakar" in t.message


def test_message_hors_sujet(assistant):
    t = assistant.analyze(None, text="Bonjour, quel temps fait-il ?")
    assert t.kind == "clarify" and "signaler un problème" in t.message and t.draft["category"] is None


def test_lieu_trop_large_demande_une_precision_une_seule_fois(assistant):
    t1 = assistant.analyze(None, text="Il y a un trou sur la route à Pikine")
    assert t1.kind == "clarify" and "commune" in t1.message
    t2 = assistant.analyze(t1.draft, text="Je ne sais pas")
    assert t2.kind == "confirm" and "Notre équipe vérifiera" in t2.message   # pas d'organisme annoncé
    done = assistant.submit(t2.draft)
    assert done.report["status"] == "NEEDS_REVIEW" and "vérifier" in done.message
    assert assistant.storage.history(done.report["reference"])["transmissions"] == []


def test_pluriels_reconnus_hors_ligne(assistant):
    t = assistant.analyze(None, text="Les égouts débordent aux Parcelles Assainies")
    assert t.kind == "confirm" and t.draft["category"] == "assainissement" and "ONAS" in t.message


def test_urgence_detectee(assistant):
    t = assistant.analyze(None, text="Un câble électrique est tombé par terre à la Médina, c'est dangereux")
    assert t.draft["category"] == "electricite" and t.draft["urgency"] == "high"


def test_fiche_non_verifiee_rien_n_est_transmis(unverified, gazetteer):
    a = Assistant(llm=None, knowledge=unverified, gazetteer=gazetteer, storage=Storage(":memory:"))
    t = a.analyze(None, text="Fuite d'eau à Ouakam")
    assert t.kind == "confirm" and "SEN'EAU" not in t.message
    assert a.submit(t.draft).report["status"] == "NEEDS_REVIEW"


def test_l_organisme_est_recalcule_a_l_envoi(assistant):
    """Un client ne peut pas imposer un organisme, une zone ou une confiance."""
    t = assistant.analyze(None, text="Fuite d'eau à Ouakam")
    forged = {**t.draft, "zone_id": "medina", "confidence_location": 1.0,
              "responsible_organization": {"id": "ORG_PIRATE", "name": "Pirate"}}
    report = assistant.submit(forged).report
    assert report["org_id"] == "ORG_SENEAU" and report["zone_id"] == "ouakam"


def test_envoi_refuse_si_brouillon_invalide(assistant):
    assert assistant.submit({"category": "inventee", "description": "x"}).kind == "error"
    assert assistant.submit({"category": "eau", "description": "  "}).kind == "error"
    assert assistant.storage.list_reports() == []


def test_proprete_orientee_vers_la_sonaged_meme_sans_commune(assistant):
    t1 = assistant.analyze(None, text="Les ordures ne sont pas ramassées à Pikine")
    t2 = assistant.analyze(t1.draft, text="Je ne sais pas")
    assert t2.kind == "confirm" and "SONAGED" in t2.message
    assert assistant.submit(t2.draft).report["status"] == "ROUTED"


def test_eclairage_hors_de_la_ville_de_dakar_part_en_verification(assistant):
    t = assistant.analyze(None, text="Le lampadaire est en panne à Rufisque")
    t = assistant.analyze(t.draft, text="Je ne sais pas")
    assert t.kind == "confirm" and t.decision["organization"] is None


def test_reorientation_manuelle_tracee(assistant):
    t = assistant.analyze(None, text="Il y a un trou sur la route à Pikine")
    ref = assistant.submit(assistant.analyze(t.draft, text="Je ne sais pas").draft).report["reference"]

    with pytest.raises(StorageError, match="motif"):
        assistant.reroute(ref, "ORG_ONAS", "admin:Awa", "  ")
    with pytest.raises(StorageError, match="inconnu"):
        assistant.reroute(ref, "ORG_PIRATE", "admin:Awa", "test")

    report = assistant.reroute(ref, "ORG_MAIRIE:ouakam", "admin:Awa", "Vérifié par téléphone")
    assert report["status"] == "ROUTED" and report["org_name"] == "Mairie de Ouakam"
    last = assistant.storage.history(ref)["routing"][-1]
    assert last["actor"] == "admin:Awa" and "Vérifié par téléphone" in last["justification"]


def test_statuts_et_suivi_public(assistant):
    ref = assistant.submit(assistant.analyze(None, text="Fuite d'eau à Ouakam").draft).report["reference"]
    storage = assistant.storage
    with pytest.raises(StorageError, match="impossible"):
        storage.set_status(ref, "CLOSED", "admin:Awa")
    for status in ("ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"):
        storage.set_status(ref, status, "admin:Awa")
    with pytest.raises(StorageError):
        assistant.reroute(ref, "ORG_ONAS", "admin:Awa", "trop tard")
    view = storage.public_view(ref.lower())
    assert view["status"] == "CLOSED" and view["organization"] == "SEN'EAU"
    assert set(view) == {"reference", "status", "created_at", "updated_at", "category", "organization"}
    assert storage.public_view("YGL-000000-XXXXXX") is None


class FakeLLM:
    """Remplace Gemini : renvoie des réponses préparées et garde les demandes reçues."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def audio_part(self, data, mime_type):
        return ("audio", mime_type, len(data))

    def generate(self, contents, **kwargs):
        self.calls.append(contents)
        return self.answers.pop(0)


def test_vocal_wolof_avec_llm(verified, gazetteer):
    llm = FakeLLM(json.dumps({
        "transcription": "Ndox mi dafa tuuru ci mbedd mi, ci Grand-Yoff", "language": "wo", "is_report": True,
        "category": "eau", "subcategory": "fuite_d_eau", "description_fr": "Fuite d'eau dans la rue",
        "description_user": "Ndox mi dafa tuuru ci mbedd mi", "location_text": "Grand-Yoff",
        "urgency": "high", "confidence_problem": 0.92,
        "responsible_organization": "Une organisation inventée"}))
    a = Assistant(llm=llm, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
    t = a.analyze(None, audio=b"RIFF....", mime_type="audio/wav")
    assert t.kind == "confirm" and t.language == "wo" and t.draft["source"] == "voice"
    assert "SEN'EAU" in t.message and "inventée" not in json.dumps(t.draft)
    assert llm.calls[0][0] == ("audio", "audio/wav", 8)


def test_vocal_inaudible_et_reponse_illisible(verified, gazetteer):
    a = Assistant(llm=FakeLLM("{}", "pas du json"), knowledge=verified, gazetteer=gazetteer,
                  storage=Storage(":memory:"))
    assert a.analyze(None, audio=b"x").kind == "not_heard"
    assert a.analyze(None, text="blabla").kind == "clarify"


def test_validation_stricte_de_la_sortie_du_modele(knowledge):
    out = validate({"category": "piratage", "subcategory": "x", "urgency": "apocalypse", "language": "xx",
                    "confidence_problem": 7, "description_fr": "a" * 900, "location_text": 42,
                    "latitude": 14.7, "longitude": -17.4}, knowledge)
    assert out["category"] == "autre" and out["subcategory"] is None and out["urgency"] == "medium"
    assert out["language"] == "fr" and out["confidence_problem"] == 1.0 and len(out["description"]) == 300
    assert out["location_text"] is None and "latitude" not in out
