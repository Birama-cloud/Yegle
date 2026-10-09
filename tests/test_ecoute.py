"""Écoute du vocal : transcription séparée, lexique wolof, langue choisie par le citoyen."""
import json

import pytest

from app import understanding
from app.assistant import Assistant
from app.storage import Storage
from config import settings

FICHE = json.dumps({"language": "wo", "is_report": True, "category": "eau", "subcategory": "fuite_d_eau",
                    "description_fr": "Fuite d'eau dans la rue", "location_text": "Grand-Yoff",
                    "urgency": "medium", "confidence_problem": 0.9})


class FauxLLM:
    def __init__(self, *reponses):
        self.reponses, self.appels = list(reponses), []

    def audio_part(self, data, mime_type):
        return ("audio", mime_type)

    def generate(self, contents, **kwargs):
        self.appels.append((contents, kwargs))
        return self.reponses.pop(0)


@pytest.fixture
def separee(monkeypatch):
    monkeypatch.setattr(settings, "TRANSCRIPTION_SEPAREE", True)
    understanding.lexique.cache_clear()


def assistant_avec(llm, verified, gazetteer):
    return Assistant(llm=llm, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))


def test_vocal_transcrit_puis_compris(separee, verified, gazetteer, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_ASR_MODEL", "modele-ecoute")
    llm = FauxLLM("« Ndox mi mongui ballë ci mbedd mi, fii ci Grand-Yoff »", FICHE)
    tour = assistant_avec(llm, verified, gazetteer).analyze(None, audio=b"....", mime_type="audio/mp4", lang="wo")

    assert tour.kind == "confirm" and tour.draft["source"] == "voice" and tour.draft["zone_id"] == "grand-yoff"
    assert tour.heard == "Ndox mi mongui ballë ci mbedd mi, fii ci Grand-Yoff"        # guillemets retirés
    (ecoute, options), (comprehension, _) = llm.appels
    assert ecoute[0] == ("audio", "audio/mp4") and options["temperature"] == 0.0
    assert options["model"] == "modele-ecoute"
    consigne = ecoute[1]
    assert "wolof, parfois avec des mots français" in consigne and "Ne traduis rien" in consigne
    assert "ndox (eau)" in consigne and "mongui ballë" in consigne                    # lexique et phrase type
    assert "Grand-Yoff" in consigne and "réellement prononcés" in consigne            # lieux du répertoire
    assert isinstance(comprehension, str) and "Ndox mi mongui ballë" in comprehension  # compris comme un texte
    assert "transcription automatique" in comprehension


@pytest.mark.parametrize("entendu", ["", "   ", "[inaudible]", "[Inaudible] ... [inaudible]", "…"])
def test_rien_d_exploitable_demande_de_repeter(separee, verified, gazetteer, entendu):
    llm = FauxLLM(entendu)
    tour = assistant_avec(llm, verified, gazetteer).analyze(None, audio=b"....")
    assert tour.kind == "not_heard" and len(llm.appels) == 1          # pas de second appel inutile


def test_sans_langue_choisie_la_consigne_reste_ouverte(separee, gazetteer):
    consigne = understanding.transcription_prompt(None, gazetteer)
    assert "wolof, français ou anglais" in consigne
    assert "français" in understanding.transcription_prompt("fr") and "Noms de lieux" not in \
        understanding.transcription_prompt("fr")


def test_lexique_absent_ou_illisible_ne_bloque_pas(separee, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LEXIQUE_FILE", tmp_path / "absent.yaml")
    understanding.lexique.cache_clear()
    assert understanding.lexique() == {"mots": [], "phrases": []}
    assert "Vocabulaire" not in understanding.transcription_prompt("wo")
    (tmp_path / "casse.yaml").write_text("mots: [", encoding="utf-8")
    monkeypatch.setattr(settings, "LEXIQUE_FILE", tmp_path / "casse.yaml")
    understanding.lexique.cache_clear()
    assert understanding.lexique()["mots"] == []
    understanding.lexique.cache_clear()


def test_lexique_livre_est_lisible():
    understanding.lexique.cache_clear()
    lex = understanding.lexique()
    assert any(m["wo"] == "ndox" for m in lex["mots"]) and lex["phrases"]


def test_mode_un_seul_appel_transmet_la_langue(verified, gazetteer):
    """Avec TRANSCRIPTION_SEPAREE=false (réglage des tests), la langue choisie est quand même indiquée."""
    llm = FauxLLM(json.dumps({**json.loads(FICHE), "transcription": "Ndox mi mongui ballë"}))
    tour = assistant_avec(llm, verified, gazetteer).analyze(None, audio=b"....", lang="wo")
    assert tour.kind == "confirm" and len(llm.appels) == 1
    assert "a indiqué parler wolof" in llm.appels[0][0][1]
