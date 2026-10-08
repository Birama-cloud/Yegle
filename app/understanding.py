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

from app.knowledge import Knowledge
from app.text import contains_phrase, norm
from app.zones import Gazetteer
from config import settings

URGENCIES = ("low", "medium", "high", "critical")

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


def extract_llm(llm, knowledge: Knowledge, text: str | None = None, audio: bytes | None = None,
                mime_type: str = "audio/wav", draft: dict | None = None) -> dict:
    """Un seul appel : transcription (si audio) + langue + extraction."""
    categories = "\n".join(f"- {c.id} : sous-catégories {', '.join(c.subcategories)}"
                           for c in knowledge.categories.values())
    prompt = (f"CATÉGORIES AUTORISÉES :\n{categories}\n\nBROUILLON EN COURS : {_draft_for_prompt(draft)}\n\n"
              f"DERNIER MESSAGE : {'[AUDIO JOINT]' if audio else text}")
    contents = prompt
    if audio:
        contents = [llm.audio_part(audio, mime_type), prompt + "\n\n" + AUDIO_HINT]
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
