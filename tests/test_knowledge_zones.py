from app.knowledge import Knowledge, Organization, Rule
from app.zones import covers


def test_base_livree_est_coherente(knowledge):
    assert knowledge.validate() == []


def test_fiche_verifiee_cite_sa_source(knowledge):
    for o in knowledge.organizations:
        assert not o.verified or str(o.source_url or "").startswith("https://"), o.id


def test_validation_detecte_les_erreurs(knowledge):
    bad = Organization(id="ORG_X", name="X", type="t", domains=["inconnu"], coverage=["partout"],
                       rules=[Rule("R_EAU_01", "eau", 1.5)], transmission_mode="webhook",
                       api_endpoint="http://exemple.invalid", last_verified_at="hier")
    errors = " | ".join(Knowledge(list(knowledge.categories.values()),
                                  [*knowledge.organizations, bad]).validate())
    for expected in ("domaine inconnu", "couverture invalide", "https", "AAAA-MM-JJ", "règle en double",
                     "hors des domaines", "entre 0 et 1"):
        assert expected in errors


def test_zone_la_plus_precise_gagne(gazetteer):
    zone, confidence = gazetteer.resolve("à Grand-Yoff, près du marché")
    assert (zone.id, confidence) == ("grand-yoff", 0.9)
    assert gazetteer.resolve("du côté de Yoff")[0].id == "yoff"


def test_zone_sans_accents_ni_casse(gazetteer):
    assert gazetteer.resolve("MEDINA rue 11")[0].id == "medina"
    assert gazetteer.resolve("Sacré-Cœur 3")[0].id == "mermoz-sacre-coeur"


def test_zone_trop_large_ou_inconnue(gazetteer):
    zone, confidence = gazetteer.resolve("à Pikine")
    assert not zone.is_commune and confidence == 0.5
    assert gazetteer.resolve("près de la boutique de Modou") == (None, 0.3)
    assert gazetteer.resolve("") == (None, 0.0)


def test_mot_partiel_ne_correspond_pas(gazetteer):
    assert gazetteer.resolve("un fanal cassé")[0] is None      # "fann" ne doit pas être reconnu


def test_gps_vers_commune(gazetteer):
    assert gazetteer.nearest(14.737, -17.455).id == "grand-yoff"
    assert gazetteer.nearest(48.85, 2.35) is None                # Paris : hors périmètre


def test_couverture(gazetteer):
    zone = gazetteer.get("ouakam")
    assert covers(["region:dakar"], zone) is True
    assert covers(["departement:pikine"], zone) is False
    assert covers(["region:dakar"], None) is None
    assert covers(["national"], None) is True
