"""Enregistre d'avance la voix de toutes les phrases fixes de Yëgle (questions, confirmations).

Lancer :  python -m scripts.precharger_voix            (toutes les langues)
          python -m scripts.precharger_voix --langue wo (seulement le wolof)

À faire une fois, quand la clé Gemini a encore du quota : ensuite ces phrases ne coûtent plus
aucun appel. Les fichiers vont dans data/voix/ ; ils peuvent être publiés avec le projet
(ce sont les phrases de Yëgle, aucune donnée de citoyen). Une phrase déjà enregistrée est sautée.
"""
import argparse
import sys

from app import voice
from app.messages import MESSAGES
from config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--langue", choices=sorted(settings.LANGS), help="une seule langue")
    args = parser.parse_args()

    llm = None
    if settings.LLM_MODE == "gemini":
        from app.llm.client import LLMClient

        llm = LLMClient()
    if llm is None:
        print("Mode hors ligne (pas de GEMINI_API_KEY) : seules les voix française et anglaise (gTTS) "
              "peuvent être préparées. La voix wolof demande une clé Gemini.\n")
    langs = [args.langue] if args.langue else sorted(settings.LANGS)
    done = skipped = failed = 0
    for lang in langs:
        for key, texts in MESSAGES.items():
            text = texts.get(lang)
            if not text or "{" in text:
                continue                        # résumés et références : propres à chaque citoyen
            clean = voice.speakable(text)
            if voice._from_disk(clean, lang)[0]:
                skipped += 1
                continue
            data, _ = voice.speak(llm, clean, lang)
            if data:
                done += 1
                print(f"  OK      {lang}  {key}")
            else:
                failed += 1
                print(f"  ÉCHEC   {lang}  {key}")
    print(f"\n{done} enregistrée(s), {skipped} déjà prête(s), {failed} en échec. Dossier : {settings.VOICE_DIR}")
    if failed:
        print("Échecs : quota Gemini atteint (erreur 429) ou réseau. Relancez plus tard : "
              "les phrases déjà prêtes sont gardées.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
