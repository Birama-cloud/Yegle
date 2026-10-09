import json

import pytest

from app.assistant import Assistant
from app.storage import Storage
from scripts import evaluer

ENTETE = "fichier;langue;texte;categorie;zone;organisme\n"


def ecrire(tmp_path, lignes):
    chemin = tmp_path / "cas.csv"
    chemin.write_text(ENTETE + lignes, encoding="utf-8")
    return chemin


def test_cas_reussis_et_echecs_sont_comptes(assistant, tmp_path):
    cas = evaluer.lire_cas(ecrire(tmp_path, (
        ";fr;Il y a une fuite d'eau à Ouakam;eau;ouakam;SEN'EAU\n"
        ";fr;Les égouts débordent aux Parcelles Assainies;assainissement;parcelles;ONAS\n"   # zone donnée par son nom
        ";fr;Le lampadaire est en panne à Yoff;voirie;yoff;\n"                               # catégorie attendue fausse
        ";fr;Fuite d'eau dans ma rue;eau;;VERIFICATION\n")), assistant)                     # sans lieu : vérification
    resultats = [evaluer.evaluer_cas(assistant, c, "auto", tmp_path) for c in cas]
    assert [r.tout_ok for r in resultats] == [True, True, False, True]
    assert cas[1].zone == "parcelles-assainies" and resultats[3].organisme == "VERIFICATION"
    assert resultats[2].ok_organisme is None                                                 # non contrôlé

    s = evaluer.synthese(resultats)
    assert s["global"]["tout"] == {"reussis": 3, "total": 4, "taux": 75}
    assert s["global"]["organisme"]["total"] == 3 and s["ecrits"] == 4 and s["vocaux"] == 0
    texte = evaluer.rapport(resultats, s, cas, "test")
    assert "3 sur 4" in texte and "lampadaire" in texte and "voirie, yoff" in texte


@pytest.mark.parametrize("ligne, message", [
    (";fr;;eau;;", "fichier audio ou un texte"),
    (";xx;texte;eau;;", "langue"),
    (";fr;texte;plomberie;;", "catégorie"),
    (";fr;texte;eau;tombouctou;", "zone"),
    (";fr;texte;eau;;Ministère inventé", "organisme"),
])
def test_valeur_attendue_inconnue_arrete_tout(assistant, tmp_path, ligne, message):
    with pytest.raises(evaluer.CasInvalide, match=message):
        evaluer.lire_cas(ecrire(tmp_path, ligne + "\n"), assistant)


def test_separateur_virgule_et_lignes_vides(assistant, tmp_path):
    chemin = tmp_path / "cas.csv"
    chemin.write_text("fichier,langue,texte,categorie,zone,organisme\n,fr,Fuite d'eau à Yoff,eau,yoff,\n,,,,,\n",
                      encoding="utf-8-sig")
    assert len(evaluer.lire_cas(chemin, assistant)) == 1


class FauxLLM:
    def __init__(self, reponse):
        self.reponse = reponse

    def audio_part(self, data, mime_type):
        return ("audio", mime_type)

    def generate(self, contents, **kwargs):
        return self.reponse


def test_vocal_et_pannes(verified, gazetteer, tmp_path):
    (tmp_path / "fuite.m4a").write_bytes(b"....")
    (tmp_path / "note.txt").write_text("x")
    llm = FauxLLM(json.dumps({"transcription": "Ndox mi mongui ballë, fii ci Grand-Yoff", "language": "wo",
                              "is_report": True, "category": "eau", "description_fr": "Fuite d'eau",
                              "location_text": "Grand-Yoff", "urgency": "medium", "confidence_problem": 0.9}))
    a = Assistant(llm=llm, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
    cas = evaluer.lire_cas(ecrire(tmp_path, (
        "fuite.m4a;wo;;eau;grand-yoff;SEN'EAU\n"
        "absent.wav;wo;;eau;grand-yoff;\n"
        "note.txt;wo;;eau;grand-yoff;\n")), a)
    r = [evaluer.evaluer_cas(a, c, "auto", tmp_path) for c in cas]
    assert r[0].mode == "vocal" and r[0].tout_ok and "Ndox" in r[0].entendu
    assert "introuvable" in r[1].erreur and "format" in r[2].erreur

    s = evaluer.synthese(r)                       # les pannes ne sont ni des réussites ni des échecs
    assert s["mesures"] == 1 and s["pannes"] == 2 and s["global"]["tout"]["taux"] == 100
    assert "Cas non mesurés" in evaluer.rapport(r, s, cas, "test")
    assert a.storage.list_reports() == []         # l'évaluation n'enregistre aucun signalement


def test_vocal_sans_cle_est_une_panne_pas_un_echec(assistant, tmp_path):
    (tmp_path / "a.wav").write_bytes(b"....")
    cas = evaluer.lire_cas(ecrire(tmp_path, "a.wav;wo;;eau;;\n"), assistant)
    assert "GEMINI_API_KEY" in evaluer.evaluer_cas(assistant, cas[0], "auto", tmp_path).erreur
