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


def _incompris(assistant, *texts):
    turn = None
    for text in texts:
        turn = assistant.analyze(turn.draft if turn else None, text=text)
    return turn


def test_probleme_incompris_porte_de_sortie_apres_deux_questions(assistant):
    t2 = _incompris(assistant, "Un chien mort pourrit devant le marché de Ouakam", "Un cadavre d'animal")
    assert t2.kind == "clarify"
    t3 = assistant.analyze(t2.draft, text="C'est un animal mort")
    assert t3.kind == "confirm" and t3.message.startswith("Je n'ai pas bien compris")
    assert t3.draft["category"] == "autre" and t3.draft["location_text"] == "Ouakam"      # lieu du 1er message
    assert "chien mort" in t3.draft["description"] and "animal mort" in t3.draft["description"]
    assert t3.decision["status"] == "organization_to_verify"

    done = assistant.submit(t3.draft)
    assert done.report["status"] == "NEEDS_REVIEW" and done.report["category"] == "autre"


def test_porte_de_sortie_description_suit_le_citoyen_puis_vraie_categorie(assistant):
    t3 = _incompris(assistant, "Un chien mort à Ouakam", "Un cadavre", "C'est un animal")
    t4 = assistant.analyze(t3.draft, text="Il sent très fort")
    assert t4.kind == "confirm" and "sent très fort" in t4.draft["description"]
    assert not t4.message.startswith("Je n'ai pas bien compris")              # dit une seule fois
    t5 = assistant.analyze(t4.draft, text="En fait ce sont des ordures")
    assert t5.draft["category"] == "proprete" and "SONAGED" in t5.message


def test_porte_de_sortie_sans_lieu_demande_le_lieu(assistant):
    t3 = _incompris(assistant, "Un chien mort", "Un cadavre", "Un animal")
    assert t3.kind == "clarify" and t3.message.startswith("Je n'ai pas bien compris")
    assert "Où se trouve" in t3.message
    t4 = assistant.analyze(t3.draft, text="À Médina")
    assert t4.kind == "confirm" and t4.draft["category"] == "autre" and "Médina" in t4.message


def test_porte_de_sortie_sans_aucun_mot_redemande(assistant):
    t3 = _incompris(assistant, "   ", "  ", " ")
    assert t3.kind == "clarify" and t3.draft["category"] is None


def test_porte_de_sortie_par_l_api_avec_brouillon_signe(assistant, monkeypatch):
    from fastapi.testclient import TestClient

    from api import main
    monkeypatch.setattr(main, "get_assistant", lambda: assistant)
    client, r = TestClient(main.app), None
    for text in ("Un chien mort à Ouakam", "Un cadavre", "Un animal"):
        body = {"text": text, **({"draft": r["draft"], "draft_token": r["draft_token"]} if r else {})}
        r = client.post("/api/analyze", json=body).json()
    assert r["kind"] == "confirm" and r["draft"]["category"] == "autre"
    created = client.post("/api/reports", json={"draft": r["draft"], "draft_token": r["draft_token"]})
    assert created.status_code == 201


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


def test_proprete_orientee_vers_la_sonaged_sans_demander_la_commune(assistant):
    t = assistant.analyze(None, text="Les ordures ne sont pas ramassées à Pikine")
    assert t.kind == "confirm" and "SONAGED" in t.message and "commune" not in t.draft["asked"]
    assert assistant.submit(t.draft).report["status"] == "ROUTED"


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


def _reponse(**kw):
    base = {"transcription": "", "language": "fr", "is_report": True, "category": None, "subcategory": None,
            "description_fr": None, "description_user": None, "location_text": None, "urgency": "medium",
            "confidence_problem": 0.9}
    return json.dumps({**base, **kw})


def test_une_reponse_de_lieu_garde_la_langue_wolof(verified, gazetteer):
    # Cas réel : problème dit en wolof, puis seulement le lieu ; Yëgle répondait en français.
    llm = FakeLLM(
        _reponse(transcription="Sali sa baye église. Ñénsu ñu koñ bi dafa tàr ndox, kayen jappale ñu.",
                 language="wo", category="assainissement", subcategory="inondation",
                 description_fr="Inondation du quartier", description_user="Koñ bi dafa tàr ndox",
                 location_text="Sali sa baye église"),
        _reponse(transcription="Parcelles Assainies unité 21", language="fr", category="assainissement",
                 description_fr="Inondation du quartier", description_user="Inondation du quartier",
                 location_text="Sali sa baye église, Parcelles Assainies unité 21"))
    a = Assistant(llm=llm, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
    t1 = a.analyze(None, text="Sali sa baye église. Ñénsu ñu koñ bi dafa tàr ndox, kayen jappale ñu.")
    assert t1.language == "wo"
    t2 = a.analyze(t1.draft, text="Parcelles Assainies unité 21")
    assert t2.kind == "confirm" and t2.language == "wo"
    assert t2.message.startswith("Sa yëgle : Koñ bi dafa tàr ndox")


def test_le_citoyen_peut_changer_de_langue(verified, gazetteer):
    llm = FakeLLM(
        _reponse(transcription="Ndox mi dafa tuuru", language="wo", category="eau",
                 description_fr="Fuite d'eau", description_user="Ndox mi dafa tuuru"),
        _reponse(transcription="C'est dans la rue à Grand-Yoff", language="fr", category="eau",
                 description_fr="Fuite d'eau", description_user="Fuite d'eau", location_text="Grand-Yoff"))
    a = Assistant(llm=llm, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
    t1 = a.analyze(None, text="Ndox mi dafa tuuru")
    t2 = a.analyze(t1.draft, text="C'est dans la rue à Grand-Yoff")
    assert t2.language == "fr" and "Votre signalement : Fuite d'eau" in t2.message


@pytest.mark.parametrize("reponse,attendu", [
    ("Waaw", "yes"), ("waaw, yónnee ko", "yes"), ("Oui", "yes"), ("D'accord", "yes"), ("yes", "yes"),
    ("Déedéet", "no"), ("Non", "no"), ("Annule", "no"), ("bul ko yónnee", "no"),
    ("Waaw waaye ci Grand-Yoff la nekk, du Parcelles Assainies", None), ("", None), ("oui non", None),
])
def test_reponse_courte_au_resume(reponse, attendu):
    assert Assistant.yes_or_no(reponse) == attendu


def _jusqu_au_resume(assistant):
    t = assistant.analyze(None, text="Il y a une fuite d'eau dans ma rue à Grand-Yoff")
    assert t.kind == "confirm"
    return t


def test_confirmer_a_la_voix_envoie(assistant):
    t = assistant.answer(_jusqu_au_resume(assistant).draft, text="Waaw")
    assert t.kind == "done" and t.report["reference"] and t.heard == "Waaw"


def test_refuser_a_la_voix_annule(assistant):
    t = assistant.answer(_jusqu_au_resume(assistant).draft, text="Déedéet")
    assert t.kind == "cancelled" and assistant.storage.list_reports() == []


def test_une_autre_phrase_corrige_le_signalement(assistant):
    t = assistant.answer(_jusqu_au_resume(assistant).draft, text="Non, c'est à Pikine")
    assert t.kind == "confirm" and "Pikine" in t.message


def test_confirmer_par_un_vocal_transcrit(verified, gazetteer):
    a = Assistant(llm=FakeLLM(_reponse(transcription="Ndox mi dafa tuuru ci Grand-Yoff", language="wo",
                                       category="eau", subcategory="fuite_d_eau", description_fr="Fuite d'eau",
                                       description_user="Ndox mi dafa tuuru", location_text="Grand-Yoff"),
                              "Waaw"),
                  knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
    t1 = a.analyze(None, text="Ndox mi dafa tuuru ci Grand-Yoff")
    assert t1.kind == "confirm" and "waaw" in t1.message
    t2 = a.answer(t1.draft, audio=b"RIFF....")
    assert t2.kind == "done" and t2.language == "wo" and t2.message.startswith("Sa yëgle bindu na")


@pytest.mark.parametrize("transcription", ["Waw.", "Wao", "waaw waaw", "Ouai", "Dakor"])
def test_oui_mal_orthographie_par_la_transcription(transcription):
    assert Assistant.yes_or_no(transcription) == "yes"


def test_reponse_courte_incomprise_redemande_sans_tourner_en_boucle(assistant):
    t1 = _jusqu_au_resume(assistant)
    t2 = assistant.answer(t1.draft, text="Ndax")
    assert t2.kind == "ask_again" and "oui" in t2.message and t2.draft["description"] == t1.draft["description"]
    assert assistant.answer(t2.draft, text="Oui").kind == "done"


@pytest.mark.parametrize("reponse,attendu", [
    # Réponses réellement transcrites lors d'un test en wolof, qui faisaient tourner Yëgle en boucle.
    ("Waw, yoon wi ñëku", "done"), ("Dédéet bu ko yóbbul", "cancelled"), ("dégât", "ask_again"),
    ("Man, he did it, did it, did it.", "ask_again"), ("Mané dé dédet.", "cancelled"),
])
def test_reponses_reelles_au_resume(assistant, reponse, attendu):
    t1 = _jusqu_au_resume(assistant)
    t2 = assistant.answer(t1.draft, text=reponse)
    assert t2.kind == attendu
    if attendu == "ask_again":            # le signalement n'est pas modifié par une réponse incomprise
        assert t2.draft["description"] == t1.draft["description"]


def test_reponse_de_lieu_avec_de_garde_le_wolof(verified, gazetteer):
    # Cas réel : « Siège de Parcelles Assainies, unité 21 » faisait passer Yëgle au français à cause de « de ».
    llm = FakeLLM(
        _reponse(transcription="Nu ngi suñu koñ ap benn lampadaire mo daal ci wétu jumaa ji. Kéen jappale ñu gaaw.",
                 language="wo", category="eclairage_public", description_fr="Lampadaire en panne",
                 description_user="Benn lampadaire dafa yàqu", location_text="wétu jumaa ji"),
        _reponse(transcription="Siège de Parcelles Assainies, unité 21.", language="fr",
                 category="eclairage_public", description_fr="Lampadaire en panne",
                 description_user="Lampadaire en panne",
                 location_text="Siège de Parcelles Assainies, unité 21"))
    a = Assistant(llm=llm, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
    t1 = a.analyze(None, text="Nu ngi suñu koñ ap benn lampadaire mo daal ci wétu jumaa ji. Kéen jappale ñu gaaw.")
    t2 = a.analyze(t1.draft, text="Siège de Parcelles Assainies, unité 21.")
    assert t2.language == "wo" and t2.message.startswith("Sa yëgle : Benn lampadaire dafa yàqu")
