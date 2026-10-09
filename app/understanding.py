"""Compréhension du message du citoyen.

Deux modes :
- LLM (Gemini) : un seul appel transcrit le vocal, détecte la langue et extrait les informations.
- hors ligne   : mots-clés, texte uniquement. Sert de secours et permet de tester sans clé.

Dans les deux cas la sortie passe par validate() : rien de ce que renvoie le modèle
n'est utilisé sans contrôle. Le modèle ne choisit JAMAIS l'organisme : c'est le rôle
du moteur d'orientation, à partir de la base de connaissances.
"""
import json
import re
from functools import lru_cache

import yaml

from app.knowledge import URGENCIES, Knowledge
from app.text import contains_phrase, norm
from app.zones import Gazetteer
from config import settings

SYSTEM = """Tu es le module de compréhension d'un système de signalement citoyen au Sénégal.
Le citoyen décrit à l'oral ou par écrit un problème dans l'espace public (wolof, français, anglais ou mélange).
Le message peut venir d'une transcription vocale avec des fautes : interprète le sens.

RÈGLES ABSOLUES :
1. Extrais uniquement les informations réellement présentes dans le message ou dans le brouillon.
2. N'invente jamais un lieu, une adresse, des coordonnées, un organisme ou une responsabilité.
3. Ne désigne aucun organisme : l'application s'en charge avec sa propre base de connaissances.
4. Si un BROUILLON est fourni, le nouveau message le complète ou le corrige : garde ce qui reste valable.
5. Estime l'urgence avec prudence : "critical" seulement s'il y a un danger immédiat pour des personnes.
6. Choisis la catégorie uniquement dans la liste fournie ; si aucune ne convient, utilise "autre".

Réponds UNIQUEMENT avec un objet JSON ayant exactement ces clés :
{
 "transcription": "string",
 "language": "fr" | "wo" | "en",
 "is_report": true | false,
 "category": "string" | null,
 "subcategory": "string" | null,
 "description_fr": "string" | null,
 "description_user": "string" | null,
 "location_text": "string" | null,
 "urgency": "low" | "medium" | "high" | "critical",
 "confidence_problem": 0.0-1.0
}

Détail des clés :
- transcription : si le message est un AUDIO, sa transcription fidèle (wolof en orthographe usuelle,
  mots français gardés en français). Si le message est écrit, recopie-le tel quel.
- language : langue du DERNIER message uniquement.
- is_report : true si le message décrit un problème à signaler, ou complète le brouillon. false sinon.
- description_fr : le problème en une phrase courte et neutre, en français, sans le lieu.
- description_user : la même phrase dans la langue du citoyen.
- location_text : le lieu tel que le citoyen l'a dit (quartier, commune, repère). null s'il n'en a pas parlé.
- confidence_problem : ta confiance dans la compréhension du problème.
"""

AUDIO_HINT = (
    "Le DERNIER MESSAGE est l'audio joint : une personne au Sénégal parle wolof, français ou anglais, "
    "souvent en mélangeant wolof et français. Vocabulaire fréquent : fuite d'eau, robinet, tuyau, courant, "
    "câble, poteau, lampadaire, route, trou, ordures, égout, inondation, mairie, quartier, marché, "
    "ndox (eau), yoon (route), mbalit (ordures), fan (où), dafa (c'est), amul (il n'y a pas), yàqu (abîmé)."
)

TRANSCRIBE_PROMPT = """Transcris cet enregistrement mot pour mot. La personne parle {langue}.

Règles :
- Écris exactement ce qui est dit, dans la langue où c'est dit. Ne traduis rien.
- Le wolof s'écrit en wolof, avec l'orthographe courante. Les mots dits en français restent en français.
- N'ajoute rien, ne résume pas, ne corrige pas le sens. Si un passage est inaudible, écris [inaudible].
- Si l'enregistrement ne contient pas de parole, réponds par une ligne vide.

Contexte : un habitant du Sénégal signale un problème dans son quartier (eau, électricité, route,
éclairage, ordures, assainissement).
{lexique}{lieux}
Réponds uniquement par la transcription, sans guillemets ni commentaire."""

LANGUE_PARLEE = {
    "wo": "wolof, parfois avec des mots français",
    "fr": "français",
    "en": "anglais",
    None: "wolof, français ou anglais, souvent en mélangeant wolof et français",
}

URGENT_WORDS = ["danger", "dangereux", "cable tombe", "cable par terre", "etincelle", "feu", "accident",
                "blesse", "enfant", "inondation", "inonde", "inondee"]
WOLOF_MARKERS = re.compile(r"[ñëŋ]|\b(dafa|amul|nekk|ndox|yoon|mbalit|sama|bi|ci|fan|yàqu|ngir)\b", re.IGNORECASE)
ENGLISH_MARKERS = re.compile(r"\b(the|there|is|street|water|broken|near|road|light|my)\b", re.IGNORECASE)
LEADING_PREPOSITION = re.compile(r"^(?:à la|à l'|à|au|aux|vers|c'est à|c'est au|c'est)\s+", re.IGNORECASE)


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    data = json.loads(match.group(0) if match else text)
    if not isinstance(data, dict):
        raise ValueError("objet JSON attendu")
    return data


def _clean(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit] or None


def validate(data: dict, knowledge: Knowledge) -> dict:
    """Contrôle strict de la sortie du modèle : valeurs hors liste remplacées, textes bornés."""
    category = data.get("category") if data.get("category") in knowledge.categories else None
    if category is None and data.get("category"):
        category = "autre"
    subcategory = None
    if category and data.get("subcategory") in knowledge.categories[category].subcategories:
        subcategory = data["subcategory"]
    try:
        confidence = min(1.0, max(0.0, float(data.get("confidence_problem", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    description = _clean(data.get("description_fr"), 300)
    return {
        "transcription": _clean(data.get("transcription"), 2000) or "",
        "language": data.get("language") if data.get("language") in settings.LANGS else "fr",
        "is_report": bool(data.get("is_report")),
        "category": category,
        "subcategory": subcategory,
        "description": description,
        "description_user": _clean(data.get("description_user"), 300) or description,
        "location_text": _clean(data.get("location_text"), 200),
        "urgency": data.get("urgency") if data.get("urgency") in URGENCIES else "medium",
        "confidence_problem": confidence,
    }


def _draft_for_prompt(draft: dict | None) -> str:
    keys = ("category", "subcategory", "description", "location_text", "urgency")
    kept = {k: draft.get(k) for k in keys if draft and draft.get(k)}
    return json.dumps(kept, ensure_ascii=False) if kept else "(aucun)"


@lru_cache(maxsize=1)
def lexique() -> dict:
    """Mots et phrases wolof validés par l'équipe (data/lexique_wolof.yaml). Relu au redémarrage."""
    try:
        data = yaml.safe_load(settings.LEXIQUE_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"mots": [], "phrases": []}
    mots = [m for m in data.get("mots") or [] if isinstance(m, dict) and m.get("wo")]
    phrases = [str(x) for x in data.get("phrases") or [] if x]
    return {"mots": mots[:120], "phrases": phrases[:30]}


def transcription_prompt(lang_hint: str | None = None, gazetteer: Gazetteer | None = None) -> str:
    lex = lexique()
    bloc = ""
    if lex["mots"]:
        bloc += "\nVocabulaire wolof fréquent : " + ", ".join(
            f"{m['wo']} ({m['fr']})" if m.get("fr") else str(m["wo"]) for m in lex["mots"]) + "."
    if lex["phrases"]:
        bloc += "\nExemples de phrases correctement écrites :\n" + "\n".join(f"- {x}" for x in lex["phrases"])
    lieux = ""
    if gazetteer is not None and gazetteer.zones:
        lieux = ("\nNoms de lieux possibles, à n'écrire que s'ils sont réellement prononcés : "
                 + ", ".join(z.name for z in gazetteer.zones) + ".")
    return TRANSCRIBE_PROMPT.format(langue=LANGUE_PARLEE.get(lang_hint, LANGUE_PARLEE[None]),
                                    lexique=bloc + "\n" if bloc else "", lieux=lieux + "\n" if lieux else "")


def transcribe(llm, audio: bytes, mime_type: str = "audio/wav", lang_hint: str | None = None,
               gazetteer: Gazetteer | None = None) -> str:
    """Transcription seule du vocal. Renvoie "" si rien d'exploitable n'est entendu."""
    raw = llm.generate([llm.audio_part(audio, mime_type), transcription_prompt(lang_hint, gazetteer)],
                       temperature=0.0, timeout_s=settings.TIMEOUT_TRANSCRIBE_S,
                       model=settings.GEMINI_ASR_MODEL or None)
    text = re.sub(r"\s+", " ", (raw or "").strip().strip('"«»“”')).strip()
    return "" if not re.sub(r"\[inaudible\]|[\W_]", "", text, flags=re.IGNORECASE) else text[:2000]


def extract_llm(llm, knowledge: Knowledge, text: str | None = None, audio: bytes | None = None,
                mime_type: str = "audio/wav", draft: dict | None = None, lang_hint: str | None = None,
                gazetteer: Gazetteer | None = None) -> dict:
    """Comprend un message. Un vocal est d'abord transcrit seul, puis compris comme un texte
    (réglage TRANSCRIPTION_SEPAREE) ; sinon transcription et extraction se font dans le même appel."""
    heard = None
    if audio and settings.TRANSCRIPTION_SEPAREE:
        heard = transcribe(llm, audio, mime_type, lang_hint, gazetteer)
        if not heard:
            return validate({}, knowledge)             # rien d'entendu : l'assistant demandera de répéter
        text, audio = heard, None
    categories = "\n".join(f"- {c.id} : sous-catégories {', '.join(c.subcategories)}"
                           for c in knowledge.categories.values())
    prompt = (f"CATÉGORIES AUTORISÉES :\n{categories}\n\nBROUILLON EN COURS : {_draft_for_prompt(draft)}\n\n"
              f"DERNIER MESSAGE : {'[AUDIO JOINT]' if audio else text}")
    if heard:
        prompt += "\n\n(Ce message est la transcription automatique d'un vocal : elle peut contenir des fautes.)"
    contents = prompt
    if audio:
        langue = LANGUE_PARLEE.get(lang_hint)
        contents = [llm.audio_part(audio, mime_type), prompt + "\n\n" + AUDIO_HINT
                    + (f" La personne a indiqué parler {langue}." if lang_hint and langue else "")]
    raw = llm.generate(contents, system=SYSTEM, json_mode=True, timeout_s=settings.TIMEOUT_UNDERSTAND_S)
    try:
        data = parse_json(raw)
    except (ValueError, json.JSONDecodeError):
        data = {}
    result = validate(data, knowledge)
    if not audio:
        result["transcription"] = (text or "").strip()
    return result


def guess_language(text: str) -> str:
    if WOLOF_MARKERS.search(text or ""):
        return "wo"
    if len(ENGLISH_MARKERS.findall(text or "")) >= 2:
        return "en"
    return "fr"


def extract_rules(knowledge: Knowledge, gazetteer: Gazetteer, text: str, draft: dict | None = None) -> dict:
    """Mode hors ligne : repère la catégorie par mots-clés et le lieu par le répertoire des zones."""
    text = (text or "").strip()
    haystack = norm(text)
    best, best_score = None, 0
    for category in knowledge.categories.values():
        score = sum(len(norm(k)) for k in category.keywords if contains_phrase(haystack, k, plural=True))
        if score > best_score:
            best, best_score = category.id, score

    # Le lieu : une zone connue du répertoire, ou la réponse libre à « où se trouve le problème ? ».
    zone, _ = gazetteer.resolve(text)
    follow_up = bool(draft and draft.get("category")) and best is None
    location = None
    if follow_up and (zone or not draft.get("location_text")):
        location = LEADING_PREPOSITION.sub("", text).strip(" .!?")
    elif zone:
        location = zone.name

    urgent = any(contains_phrase(haystack, w, plural=True) for w in URGENT_WORDS)
    return validate({
        "transcription": text,
        "language": guess_language(text),
        "is_report": best is not None or bool(draft and draft.get("category")),
        "category": best or (draft or {}).get("category"),
        "description_fr": text if best else None,
        "location_text": location,
        "urgency": "high" if urgent else "medium",
        "confidence_problem": 0.8 if best else 0.0,
    }, knowledge)
