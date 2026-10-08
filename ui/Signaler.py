"""Page citoyen.  Lancer depuis la racine du projet :  streamlit run ui/Signaler.py"""
import hashlib
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import voice  # noqa: E402
from app.messages import msg  # noqa: E402
from config import settings  # noqa: E402
from ui.common import URGENCY_LABELS, category_label, get_assistant, setup  # noqa: E402

setup("Signaler")
assistant = get_assistant()
state = st.session_state
for key, default in {"messages": [], "draft": None, "stage": "talk", "decision": None, "report": None,
                     "mic_key": 0, "last_audio": None, "lang": "fr"}.items():
    state.setdefault(key, default)

LANG_OPTIONS = {"Auto": None, "Français": "fr", "Wolof": "wo", "English": "en"}

st.markdown(f"<p class='yg-title'>{html.escape(settings.APP_NAME)}</p>"
            "<p class='yg-tag'>Un problème dans votre quartier ? Dites-le simplement. "
            "Nous trouvons le service qui doit s'en occuper.</p>", unsafe_allow_html=True)

left, right = st.columns([3, 1])
choice = left.segmented_control("Langue", list(LANG_OPTIONS), default="Auto", label_visibility="collapsed")
voice_on = right.toggle("Voix", value=True, help="Lire les réponses à voix haute")
forced_lang = LANG_OPTIONS.get(choice or "Auto")

if assistant.offline:
    st.info("Mode hors ligne : la compréhension se fait par mots-clés et uniquement par écrit. "
            "Ajoutez GEMINI_API_KEY dans le fichier .env pour activer la voix.")


def say(text: str, lang: str) -> None:
    entry = {"role": "assistant", "content": text}
    if voice_on:
        audio, mime = voice.speak(assistant.llm, text, lang)
        if audio:
            entry.update(audio=audio, mime=mime)
    state.messages.append(entry)


def reset() -> None:
    state.update(draft=None, stage="talk", decision=None, report=None, last_audio=None)
    state.mic_key += 1


def handle(text: str | None = None, audio: bytes | None = None, mime: str = "audio/wav") -> None:
    with st.spinner("Je vous écoute…" if audio else "Un instant…"):
        turn = assistant.analyze(state.draft, text=text, audio=audio, mime_type=mime, lang=forced_lang)
    state.messages.append({"role": "user", "content": turn.heard or text or "🎤 …"})
    state.draft, state.lang, state.decision = turn.draft, turn.language, turn.decision
    state.stage = "confirm" if turn.kind == "confirm" else "talk"
    state.mic_key += 1
    say(turn.message, turn.language)


def send() -> None:
    with st.spinner("Enregistrement…"):
        turn = assistant.submit(state.draft)
    if turn.kind == "done":
        state.report, state.stage = turn.report, "done"
    say(turn.message, turn.language)


for m in state.messages:
    with st.chat_message(m["role"], avatar="🧑🏾" if m["role"] == "user" else "📣"):
        st.write(m["content"])
        if m.get("audio"):
            st.audio(m["audio"], format=m["mime"], autoplay=not m.get("played"))
            m["played"] = True   # lecture automatique une seule fois

if state.stage == "confirm":
    d, decision = state.draft, state.decision or {}
    ready = decision.get("status") == "ready_for_transmission"
    org = (decision.get("organization") or {}).get("org_name") if ready else "À déterminer par notre équipe"
    place = d.get("location_text") or d.get("territorial_area") or "Non précisé"
    st.markdown(
        f"<div class='yg-card{'' if ready else ' review'}'><h4>Votre signalement</h4>"
        f"<p><b>Problème :</b> {html.escape(d.get('description_user') or d['description'])}</p>"
        f"<p><b>Catégorie :</b> {html.escape(category_label(assistant, d['category'], state.lang))}</p>"
        f"<p><b>Lieu :</b> {html.escape(place)}</p>"
        f"<p><b>Urgence :</b> {URGENCY_LABELS.get(d['urgency'], d['urgency'])}</p>"
        f"<p><b>Service destinataire :</b> {html.escape(org)}</p></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Envoyer", type="primary", width="stretch"):
        send()
        st.rerun()
    if c2.button("✏️ Corriger", width="stretch"):
        state.stage = "talk"
        say(msg("correct", state.lang), state.lang)
        st.rerun()
    if c3.button("✖ Annuler", width="stretch"):
        lang = state.lang
        reset()
        say(msg("cancelled", lang), lang)
        st.rerun()

elif state.stage == "done" and state.report:
    st.markdown("Gardez cette référence pour suivre votre signalement :")
    st.markdown(f"<div class='yg-ref'>{html.escape(state.report['reference'])}</div>", unsafe_allow_html=True)
    st.page_link("pages/1_Suivre_mon_signalement.py", label="Suivre mon signalement", icon="🔎")
    if st.button("Faire un nouveau signalement"):
        state.messages = []
        reset()
        st.rerun()

else:
    if not assistant.offline:
        recorded = st.audio_input("Appuyez sur le micro et décrivez le problème", key=f"mic_{state.mic_key}")
        if recorded is not None:
            data = recorded.getvalue()
            digest = hashlib.sha1(data).hexdigest()
            if digest != state.last_audio:      # ne jamais traiter deux fois le même enregistrement
                state.last_audio = digest
                handle(audio=data, mime=recorded.type or "audio/wav")
                st.rerun()
    if typed := st.chat_input("Ou écrivez votre message ici"):
        handle(text=typed)
        st.rerun()

st.caption("Votre voix n'est pas conservée. Aucun nom ni numéro de téléphone n'est demandé.")
