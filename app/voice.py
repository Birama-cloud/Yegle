"""Synthèse vocale des messages de l'assistant (adapté du prototype TEKTALMA du même auteur).

Français / anglais : gTTS, puis Gemini TTS en secours. Wolof : Gemini TTS.
Renvoie (None, None) si aucune voix n'est disponible : le texte reste affiché.
"""
import io
import re
import wave
from functools import lru_cache

from config import settings


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


def speak(llm, text: str, lang: str):
    clean = speakable(text)
    return _speak_cached(llm, clean, lang) if clean else (None, None)
