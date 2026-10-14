import pytest

from app import voice
from app.messages import msg


class FakeTTS:
    def __init__(self):
        self.calls = 0

    def synthesize(self, text, timeout_s=None):
        self.calls += 1
        return b"RIFF" + text.encode("utf-8"), "audio/wav"


@pytest.fixture
def dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(voice.settings, "VOICE_DIR", tmp_path / "voix")
    return tmp_path / "voix"


def test_phrase_fixe_enregistree_puis_relue_sans_appel(dossier):
    phrase = msg("ask_commune", "wo")
    premier = FakeTTS()
    assert voice.speak(premier, phrase, "wo")[0] and premier.calls == 1
    second = FakeTTS()                       # nouvel objet : le cache en mémoire ne sert pas
    data, mime = voice.speak(second, phrase, "wo")
    assert data and mime == "audio/wav" and second.calls == 0
    assert len(list(dossier.iterdir())) == 1


def test_enchainement_de_phrases_fixes(dossier):
    texte = msg("not_understood", "wo") + " " + msg("ask_location", "wo")
    assert voice.is_fixed(voice.speakable(texte))


def test_resume_du_citoyen_jamais_ecrit_sur_le_disque(dossier):
    resume = msg("summary_known", "wo", description="Tuyo bi dafa todj", place="Grand-Yoff", org="SEN'EAU")
    assert not voice.is_fixed(voice.speakable(resume))
    tts = FakeTTS()
    assert voice.speak(tts, resume, "wo")[0] and tts.calls == 1
    assert not dossier.exists() or not list(dossier.iterdir())
