"""Client LLM : Gemini en principal, OpenAI en dernier secours.

Module repris et adapté du prototype TEKTALMA du même auteur.
- 503 / 500 / délai dépassé : 1 nouvel essai rapide, puis modèle Gemini de secours.
- 429 (quota épuisé) : pas de réessai inutile, on passe directement au modèle suivant.
- Si les deux modèles Gemini échouent et qu'une clé OpenAI est configurée,
  la même demande part chez OpenAI (les vocaux sont d'abord transcrits par OpenAI).
"""
import io
import sys
import time

from config import settings

TEMPORARY = {500, 502, 503, 504}
QUOTA = 429


class LLMUnavailable(RuntimeError):
    """Tous les modèles ont échoué (surcharge, quota ou réseau)."""

    def __init__(self, message, quota=False):
        super().__init__(message)
        self.quota = quota


class LLMClient:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY manquante dans .env")
        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.models = [m for m in dict.fromkeys([settings.GEMINI_MODEL, settings.GEMINI_FALLBACK_MODEL]) if m]
        self.openai = None
        if settings.OPENAI_API_KEY:
            from openai import OpenAI

            self.openai = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=0)

    def audio_part(self, data: bytes, mime_type: str):
        return self.types.Part.from_bytes(data=data, mime_type=mime_type)

    def _call(self, models, contents, config):
        last_error, only_quota = None, True
        for i, model in enumerate(models):
            attempts = 2 if i == 0 else 1
            for attempt in range(attempts):
                try:
                    return self.client.models.generate_content(model=model, contents=contents, config=config)
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    code = getattr(e, "code", None)
                    print(f"  LLM {model} essai {attempt + 1}/{attempts} : {code or type(e).__name__}",
                          file=sys.stderr)
                    only_quota = only_quota and code == QUOTA
                    if code in TEMPORARY or code is None:   # surcharge, délai, réseau
                        time.sleep(1)
                        continue
                    break                                     # quota ou erreur définitive : modèle suivant
        raise LLMUnavailable(f"LLM indisponible : {last_error}", quota=only_quota)

    def _http(self, timeout_s):
        return self.types.HttpOptions(timeout=int((timeout_s or settings.GEMINI_TIMEOUT_S) * 1000))

    def generate(self, contents, system: str | None = None, json_mode: bool = False,
                 temperature: float = 0.1, timeout_s: float | None = None, model: str | None = None) -> str:
        """model : modèle à essayer en premier pour cet appel (les modèles habituels restent en secours)."""
        types = self.types
        models = list(dict.fromkeys([model, *self.models])) if model else self.models
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=(types.ThinkingConfig(thinking_level=settings.GEMINI_THINKING_LEVEL)
                             if settings.GEMINI_THINKING_LEVEL else None),
            http_options=self._http(timeout_s),
        )
        try:
            resp = self._call(models, contents, config)
            return (resp.text or "").strip()
        except LLMUnavailable as gemini_error:
            if not self.openai:
                raise
            print(f"  Gemini indisponible, bascule vers OpenAI ({settings.OPENAI_MODEL})", file=sys.stderr)
            try:
                return self._openai_generate(contents, system, json_mode, temperature, timeout_s)
            except Exception as e:  # noqa: BLE001
                raise LLMUnavailable(f"Gemini et OpenAI indisponibles : {e}", quota=gemini_error.quota) from e

    # ------------------------------------------------------------------ OpenAI (secours)
    def _openai_transcribe(self, data: bytes, mime_type: str, timeout_s: float) -> str:
        ext = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/mp3": "mp3",
               "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a"}.get(mime_type, "wav")
        f = io.BytesIO(data)
        f.name = f"vocal.{ext}"
        r = self.openai.audio.transcriptions.create(model=settings.OPENAI_TRANSCRIBE_MODEL, file=f,
                                                    timeout=timeout_s)
        return (r.text or "").strip()

    def _openai_generate(self, contents, system, json_mode, temperature, timeout_s) -> str:
        timeout = timeout_s or settings.GEMINI_TIMEOUT_S
        texts = []
        for part in contents if isinstance(contents, list) else [contents]:
            blob = getattr(part, "inline_data", None)
            if isinstance(part, str):
                texts.append(part)
            elif blob is not None and str(blob.mime_type or "").startswith("audio"):
                heard = self._openai_transcribe(blob.data, blob.mime_type, timeout)
                texts.append(f"[Transcription automatique de l'audio joint] : {heard}")
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": "\n\n".join(texts)}]
        kwargs = {"model": settings.OPENAI_MODEL, "messages": messages, "timeout": timeout,
                  "temperature": temperature}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        r = self.openai.chat.completions.create(**kwargs)
        return (r.choices[0].message.content or "").strip()

    # ------------------------------------------------------------------ voix
    def synthesize(self, text: str, timeout_s: float | None = None) -> tuple[bytes, str]:
        """Renvoie (données audio brutes, mime_type) via le modèle TTS de Gemini."""
        types = self.types
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            http_options=self._http(timeout_s),
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.GEMINI_TTS_VOICE))),
        )
        resp = self._call([settings.GEMINI_TTS_MODEL], config=config, contents=text)
        part = resp.candidates[0].content.parts[0].inline_data
        return part.data, part.mime_type or "audio/L16;rate=24000"
