"""Page citoyen.  Lancer depuis la racine du projet :  streamlit run ui/Signaler.py"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import voice  # noqa: E402
from app.messages import msg  # noqa: E402
from ui.common import (PAGE_TRACK, URGENCY_LABELS, analyze_limiter, category_label, client_ip,  # noqa: E402
                       esc, get_assistant, setup, steps)

setup("Signaler")
assistant = get_assistant()
state = st.session_state
for key, default in {"messages": [], "draft": None, "stage": "talk", "decision": None, "report": None,
                     "mic_key": 0, "last_audio": None, "lang": "fr", "speak": None, "notice": None}.items():
    state.setdefault(key, default)

LANG_OPTIONS = {"Auto": None, "Français": "fr", "Wolof": "wo", "English": "en"}
# Préférences gardées hors des widgets : Streamlit oublie un widget dès qu'il n'est plus affiché.
state.setdefault("pref_lang", "Auto")
state.setdefault("pref_voice", True)
forced_lang = LANG_OPTIONS.get(state.pref_lang)


def say(text: str, lang: str) -> None:
    state.messages.append({"role": "bot", "content": text})
    state.speak = None
    if state.pref_voice:
        audio, mime = voice.speak(assistant.llm, text, lang)
        if audio:
            state.speak = {"audio": audio, "mime": mime, "played": False}


def reset() -> None:
    state.update(draft=None, stage="talk", decision=None, report=None, last_audio=None, speak=None)
    state.mic_key += 1


def handle(text: str | None = None, audio: bytes | None = None, mime: str = "audio/wav") -> None:
    if analyze_limiter().take(client_ip()):
        state.mic_key += 1
        state.notice = "Vous avez envoyé beaucoup de messages. Patientez une minute, puis réessayez."
        return
    with st.spinner("Je vous écoute…" if audio else "Un instant…"):
        turn = assistant.analyze(state.draft, text=text, audio=audio, mime_type=mime, lang=forced_lang)
    state.messages.append({"role": "user", "content": turn.heard or text or "Message vocal"})
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


# ---------------------------------------------------------------- en-tête de page
steps({"talk": 0, "confirm": 1, "done": 3}[state.stage])

if not state.messages:
    st.markdown(
        "<div class='yg-hero'><h1>Un problème dans votre quartier ? Dites-le.</h1>"
        "<p>Eau, électricité, route, éclairage, ordures. Parlez en wolof, en français ou en anglais : "
        "nous trouvons le service qui doit s'en occuper.</p></div>", unsafe_allow_html=True)
else:
    bubbles = "".join(
        f"<div class='yg-msg {m['role']}'><small>{'Vous' if m['role'] == 'user' else 'Yëgle'}</small>"
        f"{esc(m['content'])}</div>" for m in state.messages)
    st.markdown(f"<div class='yg-chat'>{bubbles}</div>", unsafe_allow_html=True)
    if state.speak:
        st.audio(state.speak["audio"], format=state.speak["mime"], autoplay=not state.speak["played"])
        state.speak["played"] = True     # lecture automatique une seule fois

# ---------------------------------------------------------------- étape en cours
if state.stage == "confirm":
    d, decision = state.draft, state.decision or {}
    ready = decision.get("status") == "ready_for_transmission"
    org = (decision.get("organization") or {}).get("org_name") if ready else "À déterminer par notre équipe"
    place = d.get("location_text") or d.get("territorial_area") or "Non précisé"
    st.markdown(
        "<section class='yg-ticket'><header>Vérifiez votre signalement</header><dl>"
        f"<dt>Problème</dt><dd>{esc(d.get('description_user') or d['description'])}</dd>"
        f"<dt>Catégorie</dt><dd>{esc(category_label(assistant, d['category'], state.lang))}</dd>"
        f"<dt>Lieu</dt><dd>{esc(place)}</dd>"
        f"<dt>Urgence</dt><dd>{esc(URGENCY_LABELS.get(d['urgency'], d['urgency']))}</dd></dl>"
        f"<div class='dest'><i class='yg-dot{'' if ready else ' warn'}'></i><div>"
        f"<span>Service destinataire</span><b>{esc(org)}</b></div></div></section>", unsafe_allow_html=True)
    if st.button("Envoyer le signalement", type="primary", width="stretch"):
        send()
        st.rerun()
    left, right = st.columns(2)
    if left.button("Corriger", width="stretch"):
        state.stage = "talk"
        say(msg("correct", state.lang), state.lang)
        st.rerun()
    if right.button("Annuler", width="stretch"):
        lang = state.lang
        reset()
        say(msg("cancelled", lang), lang)
        st.rerun()

elif state.stage == "done" and state.report:
    report = state.report
    waiting = report["status"] == "NEEDS_REVIEW"
    org = "En cours de vérification par notre équipe" if waiting else report["org_name"]
    st.markdown(
        "<section class='yg-ticket'><header>Votre référence de suivi</header>"
        f"<div class='yg-ref'>{esc(report['reference'])}</div>"
        "<p class='yg-ref-help'>Notez-la ou faites une capture d'écran : elle permet de suivre votre signalement.</p>"
        f"<div class='dest'><i class='yg-dot{' warn' if waiting else ''}'></i><div>"
        f"<span>Service destinataire</span><b>{esc(org)}</b></div></div></section>", unsafe_allow_html=True)
    st.page_link(PAGE_TRACK, label="Suivre ce signalement", icon=":material/search:")
    if st.button("Faire un autre signalement", width="stretch"):
        state.messages = []
        reset()
        st.rerun()

else:
    if state.notice:
        st.warning(state.notice)
        state.notice = None
    if assistant.offline:
        st.info("Mode hors ligne : écrivez votre message. Le micro s'active dès qu'une clé GEMINI_API_KEY "
                "est renseignée dans le fichier .env.")
    else:
        label = "Appuyez sur le micro et parlez" if not state.messages else "Appuyez pour répondre"
        recorded = st.audio_input(label, key=f"mic_{state.mic_key}")
        if recorded is not None:
            data = recorded.getvalue()
            digest = hashlib.sha1(data).hexdigest()
            if digest != state.last_audio:      # ne jamais traiter deux fois le même enregistrement
                state.last_audio = digest
                handle(audio=data, mime=recorded.type or "audio/wav")
                st.rerun()
    state["yg_lang"], state["yg_voice"] = state.pref_lang, state.pref_voice
    with st.container(horizontal=True, vertical_alignment="center", gap="medium", key="yg_prefs"):
        st.segmented_control("Langue", list(LANG_OPTIONS), key="yg_lang", label_visibility="collapsed",
                             width="content")
        st.toggle("Réponses à voix haute", key="yg_voice", width="content")
    state.pref_lang, state.pref_voice = state.yg_lang or "Auto", state.yg_voice
    # À l'accueil, le champ reste dans la page pour qu'elle s'ouvre en haut. Une fois la conversation
    # commencée, il se fixe en bas et l'écran suit le dernier message.
    holder = st if state.messages else st.container()
    if typed := holder.chat_input("Ou écrivez votre message"):
        handle(text=typed)
        st.rerun()
    if not state.messages:
        st.markdown("<p class='yg-note'>Votre voix n'est pas conservée. Aucun nom ni numéro de téléphone "
                    "n'est demandé.</p>", unsafe_allow_html=True)
