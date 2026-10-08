"""Outils de texte partagés."""
import re
import unicodedata


def norm(text: str) -> str:
    """Minuscules, sans accents, ponctuation remplacée par des espaces."""
    text = unicodedata.normalize("NFKD", (text or "").lower().replace("œ", "oe"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def contains_phrase(haystack_norm: str, phrase: str, plural: bool = False) -> bool:
    """Vrai si l'expression apparaît en mots entiers dans un texte déjà normalisé.

    plural=True accepte aussi la forme au pluriel (égout -> égouts, tuyau -> tuyaux).
    """
    phrase = norm(phrase)
    end = "(?:s|x)?" if plural else ""
    return bool(phrase) and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}{end}(?![a-z0-9])",
                                      haystack_norm) is not None
