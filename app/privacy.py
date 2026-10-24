"""Masquage des données personnelles avant l'enregistrement d'un signalement.

Yëgle ne demande ni nom ni numéro de téléphone. Si le citoyen en donne un quand même,
le signalement est accepté (le rejeter écarterait ceux qui ne savent pas lire), mais
ces informations sont remplacées par une mention neutre avant d'être enregistrées.

Le masquage est volontairement prudent : il ne retire que ce qui est sûr (numéros de
téléphone, adresses e-mail) et les noms annoncés explicitement (« je m'appelle… »,
« sama tur… »). Il ne touche ni aux lieux ni aux autres nombres (« depuis 3 jours »).
"""

import re

NUMERO_RETIRE = "[numéro retiré]"
EMAIL_RETIRE = "[e-mail retiré]"
NOM_RETIRE = "[nom retiré]"

# Numéros sénégalais : mobiles 70, 71, 75, 76, 77, 78 et fixes 33, avec ou sans +221 / 00221,
# chiffres collés ou séparés par des espaces, points ou tirets.
_TEL_SN = re.compile(
    r"(?<!\d)(?:(?:\+|00)\s?221[\s.\-]?)?(?:7[015678]|33)(?:[\s.\-]?\d){7}(?!\d)"
)
# Numéro international quelconque écrit avec un « + » (ex. +33 6 12 34 56 78).
_TEL_INTER = re.compile(r"\+\s?\d{1,3}(?:[\s.\-]?\d){6,12}(?!\d)")
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")

# Un mot de nom : commence par une lettre, accepte accents, tiret et apostrophe.
_MOT = r"[A-Za-zÀ-ÖØ-öø-ÿËë][\wÀ-ÖØ-öø-ÿ'\-]*"
_NOM = rf"{_MOT}(?:\s+{_MOT})?"     # prénom, ou prénom + nom
_ANNONCES_NOM = [
    r"je\s+m['’]\s?appelle",
    r"mon\s+nom\s+(?:est|c['’]est)",
    r"maa\s+ngi\s+tudd",
    r"dama\s+tudd",
    r"sama\s+tur\s+(?:mooy|moo\s+di|mo\s+di|di)",
    r"sama\s+tur",
    r"my\s+name\s+is",
]
_NOM_ANNONCE = re.compile(rf"\b((?:{'|'.join(_ANNONCES_NOM)}))\s+{_NOM}", re.IGNORECASE)


def mask_personal_data(text: str | None) -> str | None:
    """Remplace numéros de téléphone, e-mails et noms annoncés par une mention neutre."""
    if not text:
        return text
    masked = _EMAIL.sub(EMAIL_RETIRE, text)
    masked = _TEL_INTER.sub(NUMERO_RETIRE, masked)   # d'abord les numéros avec « + » (dont +221)
    masked = _TEL_SN.sub(NUMERO_RETIRE, masked)
    masked = _NOM_ANNONCE.sub(lambda m: f"{m.group(1)} {NOM_RETIRE}", masked)
    return masked
