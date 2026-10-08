"""Suivi citoyen : statut d'un signalement à partir de sa référence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from ui.common import STATUS_LABELS, category_label, get_assistant, setup  # noqa: E402

setup("Suivi")
assistant = get_assistant()

st.title("Suivre mon signalement")
reference = st.text_input("Votre référence", placeholder="YGL-261008-ABC234").strip().upper()

if reference:
    view = assistant.storage.public_view(reference)
    if not view:
        st.error("Aucun signalement ne correspond à cette référence. Vérifiez les lettres et les chiffres.")
    else:
        org = view["organization"] or "En cours de vérification par notre équipe"
        st.markdown(
            f"<div class='yg-card'><h4>{view['reference']}</h4>"
            f"<p><b>Statut :</b> {STATUS_LABELS.get(view['status'], view['status'])}</p>"
            f"<p><b>Catégorie :</b> {category_label(assistant, view['category'])}</p>"
            f"<p><b>Service destinataire :</b> {org}</p>"
            f"<p><b>Créé le :</b> {view['created_at'][:16].replace('T', ' à ')} (UTC)</p>"
            f"<p><b>Dernière mise à jour :</b> {view['updated_at'][:16].replace('T', ' à ')} (UTC)</p></div>",
            unsafe_allow_html=True)
