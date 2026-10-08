"""Éléments partagés par les pages Streamlit."""
import streamlit as st

from app.assistant import Assistant
from config import settings

STATUS_LABELS = {
    "RECEIVED": "Reçu", "ROUTED": "Orienté", "NEEDS_REVIEW": "En vérification", "ASSIGNED": "Affecté",
    "IN_PROGRESS": "En cours de traitement", "RESOLVED": "Résolu", "CLOSED": "Clôturé", "REJECTED": "Rejeté",
}
URGENCY_LABELS = {"low": "Faible", "medium": "Moyenne", "high": "Élevée", "critical": "Critique"}

CSS = """
<style>
.block-container{padding-top:3.6rem;}
.yg-title{font-size:2.6rem; font-weight:800; letter-spacing:.02em; color:#0B6E4F; line-height:1; margin:0;}
.yg-tag{color:#4E5F58; font-size:1.05rem; margin:.4rem 0 1.2rem;}
.yg-card{background:#fff; border:1px solid #E2D9C6; border-left:6px solid #0B6E4F; border-radius:10px;
  padding:16px 18px; margin:10px 0;}
.yg-card.review{border-left-color:#C9741A;}
.yg-card h4{margin:0 0 8px; font-size:1rem; color:#0B6E4F;}
.yg-card p{margin:3px 0;}
.yg-ref{font-family:ui-monospace, Menlo, Consolas, monospace; font-size:1.7rem; font-weight:700;
  letter-spacing:.06em; color:#1D2B26; background:#F0E9DA; border-radius:8px; padding:10px 14px;
  display:inline-block; margin:6px 0;}
[data-testid="stAudioInput"]{margin:6px 0 2px;}
</style>
"""


def setup(title: str, wide: bool = False) -> None:
    st.set_page_config(page_title=f"{title} · {settings.APP_NAME}", page_icon="📣",
                       layout="wide" if wide else "centered")
    st.markdown(CSS, unsafe_allow_html=True)
    if not wide:
        st.markdown("<style>.block-container{max-width:780px;}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Démarrage…")
def get_assistant() -> Assistant:
    return Assistant()


def category_label(assistant: Assistant, category_id: str, lang: str = "fr") -> str:
    category = assistant.knowledge.categories.get(category_id)
    return category.name(lang) if category else category_id
