from app import routing
from app.knowledge import Organization, Rule


def test_fiche_non_verifiee_part_en_verification(unverified, gazetteer):
    d = routing.route(unverified, "eau", "fuite_d_eau", gazetteer.get("grand-yoff"), 0.9)
    assert not d.ready and d.organization.org_name == "SEN'EAU"
    assert "non vérifiée" in d.justification


def test_fiche_verifiee_est_orientee(verified, gazetteer):
    d = routing.route(verified, "eau", "fuite_d_eau", gazetteer.get("grand-yoff"), 0.9)
    assert d.ready and d.organization.org_id == "ORG_SENEAU" and d.organization.confidence == 0.9
    assert "R_EAU_01" in d.justification


def test_mairie_prend_le_nom_de_la_commune(verified, gazetteer):
    d = routing.route(verified, "voirie", "nid_de_poule", gazetteer.get("ouakam"), 0.9)
    assert d.ready
    assert (d.organization.org_id, d.organization.org_name) == ("ORG_MAIRIE:ouakam", "Mairie de Ouakam")


def test_mairie_sans_commune_part_en_verification(verified, gazetteer):
    d = routing.route(verified, "voirie", None, gazetteer.get("dep-pikine"), 0.9)
    assert not d.ready and "commune non identifiée" in d.justification


def test_zone_inconnue_baisse_la_confiance(verified):
    d = routing.route(verified, "electricite", None, None, 0.9)
    assert not d.ready and d.organization.confidence == 0.54


def test_categorie_sans_organisme(verified, gazetteer):
    d = routing.route(verified, "autre", None, gazetteer.get("medina"), 0.9)
    assert not d.ready and d.organization is None and d.candidates == []


def test_probleme_mal_compris(verified, gazetteer):
    d = routing.route(verified, "eau", None, gazetteer.get("medina"), 0.2)
    assert not d.ready and "insuffisamment compris" in d.justification


def test_deux_organismes_proches_sont_ambigus(verified, gazetteer):
    verified.organizations.append(Organization(
        id="ORG_BIS", name="Autre opérateur", type="t", domains=["eau"], coverage=["region:dakar"],
        rules=[Rule("R_EAU_02", "eau", 0.88)], last_verified_at="2026-10-08"))
    d = routing.route(verified, "eau", None, gazetteer.get("medina"), 0.9)
    assert not d.ready and len(d.candidates) == 2 and "plusieurs organismes" in d.justification


def test_organisme_hors_zone_ou_inactif_est_ecarte(verified, gazetteer):
    verified.organizations.append(Organization(
        id="ORG_RUF", name="Régie de Rufisque", type="t", domains=["eau"], coverage=["departement:rufisque"],
        rules=[Rule("R_EAU_03", "eau", 0.95)], last_verified_at="2026-10-08"))
    verified.get_org("ORG_SENEAU").active = False
    d = routing.route(verified, "eau", None, gazetteer.get("medina"), 0.9)
    assert d.candidates == []
