from app.privacy import NOM_RETIRE, NUMERO_RETIRE, EMAIL_RETIRE, mask_personal_data


def test_numeros_senegalais_masques():
    for numero in ["77 123 45 67", "771234567", "+221 77 123 45 67", "00221781234567", "33.821.23.45", "76-123-45-67"]:
        texte = f"Appelez-moi au {numero} s'il vous plaît"
        assert mask_personal_data(texte) == f"Appelez-moi au {NUMERO_RETIRE} s'il vous plaît"


def test_numero_international_et_email():
    assert mask_personal_data("mon numéro +33 6 12 34 56 78") == f"mon numéro {NUMERO_RETIRE}"
    assert mask_personal_data("écrivez à awa.diop@gmail.com") == f"écrivez à {EMAIL_RETIRE}"


def test_noms_annonces_masques():
    assert mask_personal_data("Je m'appelle Awa Diop, il y a une fuite") == f"Je m'appelle {NOM_RETIRE}, il y a une fuite"
    assert mask_personal_data("mon nom est Moussa") == f"mon nom est {NOM_RETIRE}"
    assert mask_personal_data("Maa ngi tudd Fatou, ndox mi") == f"Maa ngi tudd {NOM_RETIRE}, ndox mi"
    assert mask_personal_data("sama tur mooy Ibrahima") == f"sama tur mooy {NOM_RETIRE}"


def test_le_reste_ne_change_pas():
    textes = [
        "Ndox mi mongui ballë ci mbedd mi, fii ci Grand-Yoff",
        "Une fuite d'eau depuis 3 jours à Grand-Yoff, rue 10",
        "Le lampadaire est en panne depuis 2026, près du marché HLM 5",
        "Référence YGL-EAU-1510-K7P2",
        "Il y a 12 maisons inondées à Ouakam",
    ]
    for texte in textes:
        assert mask_personal_data(texte) == texte


def test_vide():
    assert mask_personal_data(None) is None
    assert mask_personal_data("") == ""
