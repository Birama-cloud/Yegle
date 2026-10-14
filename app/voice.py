"""Synthèse vocale des messages de l'assistant (adapté du prototype TEKTALMA du même auteur).

Français / anglais : gTTS, puis Gemini TTS en secours. Wolof : Gemini TTS.
Renvoie (None, None) si aucune voix n'est disponible : le texte reste affiché.

Les phrases fixes de Yëgle (questions, confirmations) sont enregistrées dans data/voix/ la première
fois qu'elles sont dites : ensuite, elles ne coûtent plus aucun appel. Seuls les résumés, qui
contiennent le problème et le lieu du citoyen, sont générés à chaque fois et jamais enregistrés.
Pour tout préparer d'avance :  python -m scripts.precharger_voix
"""
import hashlib
import io
import logging
import re
import wave
from functools import lru_cache

from config import settings

log = logging.getLogger(__name__)


def speakable(text: str) -> str:
    text = re.sub(r"[*#_`>|]", "", text or "")
    return re.sub(r"\s+", " ", text).strip()[:900]


def _wav(samples: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples)
    return buf.getvalue()


def _gemini_tts(llm, text: str):
    data, mime = llm.synthesize(text, timeout_s=settings.TIMEOUT_TTS_S)
    if "wav" in mime:
        return data, "audio/wav"
    rate = int(m.group(1)) if (m := re.search(r"rate=(\d+)", mime)) else 24000
    return _wav(data, rate), "audio/wav"   # PCM 16 bits brut -> WAV


def _gtts(text: str, lang: str):
    from gtts import gTTS

    buf = io.BytesIO()
    gTTS(text, lang=lang).write_to_fp(buf)
    return buf.getvalue(), "audio/mp3"


@lru_cache(maxsize=128)
def _speak_cached(llm, text: str, lang: str):
    engines = []
    if lang in ("fr", "en"):
        engines.append(lambda: _gtts(text, lang))
    if llm is not None:
        engines.append(lambda: _gemini_tts(llm, text))
    for engine in engines:
        try:
            return engine()
        except Exception:  # noqa: BLE001  (quota, réseau, module absent)
            continue
    return None, None


@lru_cache(maxsize=1)
def fixed_phrases() -> tuple[str, ...]:
    """Toutes les phrases fixes, dans toutes les langues (les plus longues d'abord)."""
    from app.messages import MESSAGES

    texts = {speakable(t) for m in MESSAGES.values() for t in m.values() if "{" not in t}
    return tuple(sorted(texts, key=len, reverse=True))


def is_fixed(text: str) -> bool:
    """Vrai si le texte n'est fait que de phrases fixes (ex. « je n'ai pas compris » + « où est-ce ? »)."""
    rest = f" {text} "
    for phrase in fixed_phrases():
        rest = rest.replace(phrase, " ")
    return bool(text) and not rest.strip(" .")


def _voice_file(text: str, lang: str):
    key = "|".join((settings.GEMINI_TTS_MODEL, settings.GEMINI_TTS_VOICE, lang, text))
    return settings.VOICE_DIR / f"{lang}-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"


def _from_disk(text: str, lang: str):
    base = _voice_file(text, lang)
    for ext, mime in ((".wav", "audio/wav"), (".mp3", "audio/mp3")):
        if (path := base.with_suffix(ext)).exists():
            return path.read_bytes(), mime
    return None, None


def _to_disk(text: str, lang: str, data: bytes, mime: str) -> None:
    try:
        settings.VOICE_DIR.mkdir(parents=True, exist_ok=True)
        path = _voice_file(text, lang).with_suffix(".wav" if "wav" in mime else ".mp3")
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)                       # jamais de fichier à moitié écrit
    except OSError:
        log.warning("Voix non enregistrée sur le disque (%s)", settings.VOICE_DIR)


def speak(llm, text: str, lang: str):
    clean = speakable(text)
    if not clean:
        return None, None
    fixed = is_fixed(clean)
    if fixed:
        data, mime = _from_disk(clean, lang)
        if data:
            return data, mime
    data, mime = _speak_cached(llm, clean, lang)
    if fixed and data:
        _to_disk(clean, lang, data, mime)
    return data, mime
