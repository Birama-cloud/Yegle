"""Suivi citoyen : où en est un signalement, à partir de sa référence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from ui.common import badge, category_label, esc, get_assistant, setup, when  # noqa: E402

setup("Suivi")
assistant = get_assistant()

# Les étapes vues par le citoyen, et les statuts internes qui y correspondent.
STAGES = [
    ("Reçu", "Votre signalement est enregistré.", ("RECEIVED", "NEEDS_REVIEW")),
    ("Orienté", "Il a été transmis au service compétent.", ("ROUTED", "ASSIGNED")),
    ("En cours de traitement", "Le service s'en occupe.", ("IN_PROGRESS",)),
    ("Résolu", "Le problème est signalé comme réglé.", ("RESOLVED", "CLOSED")),
]

st.markdown("<h1>Suivre un signalement</h1>", unsafe_allow_html=True)
reference = st.text_input("Votre référence", placeholder="YGL-261008-ABC234",
                          help="Elle vous a été donnée à la fin de votre signalement.").strip().upper()

if reference:
    view = assistant.storage.public_view(reference)
    if not view:
        st.error("Aucun signalement ne porte cette référence. Vérifiez les lettres et les chiffres, tirets compris.")
    elif view["status"] == "REJECTED":
        st.markdown(f"<section class='yg-ticket'><header>{esc(view['reference'])}</header>"
                    "<div class='dest'><i class='yg-dot stop'></i><div><span>Statut</span>"
                    "<b>Ce signalement n'a pas été retenu.</b></div></div></section>", unsafe_allow_html=True)
    else:
        current = next(i for i, stage in enumerate(STAGES) if view["status"] in stage[2])
        finished = view["status"] in ("RESOLVED", "CLOSED")
        items = ""
        for i, (title, detail, _) in enumerate(STAGES):
            css = "done" if i < current or (finished and i == current) else "now" if i == current else ""
            note = detail if i <= current else ""
            if i == 0 and view["status"] == "NEEDS_REVIEW":
                note = "Notre équipe vérifie quel service doit le traiter."
            items += f"<li class='{css}'>{esc(title)}" + (f"<br><span>{esc(note)}</span>" if note else "") + "</li>"
        org = view["organization"] or "En cours de vérification par notre équipe"
        st.markdown(
            f"<section class='yg-ticket'><header>{esc(view['reference'])}</header>"
            f"<dl><dt>Statut</dt><dd>{badge(view['status'])}</dd>"
            f"<dt>Catégorie</dt><dd>{esc(category_label(assistant, view['category']))}</dd>"
            f"<dt>Créé le</dt><dd>{esc(when(view['created_at']))}</dd>"
            f"<dt>Mis à jour le</dt><dd>{esc(when(view['updated_at']))}</dd></dl>"
            f"<div class='dest'><i class='yg-dot{'' if view['organization'] else ' warn'}'></i><div>"
            f"<span>Service destinataire</span><b>{esc(org)}</b></div></div>"
            f"<ol class='yg-track' style='border-top:2px dashed var(--line)'>{items}</ol></section>",
            unsafe_allow_html=True)
        st.caption("Les heures sont indiquées en temps universel (UTC).")
