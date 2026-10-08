"""Tableau de bord central : tous les signalements, leur orientation et leur suivi."""
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.storage import TRANSITIONS, StorageError  # noqa: E402
from config import settings  # noqa: E402
from ui.common import STATUS_LABELS, URGENCY_LABELS, category_label, get_assistant, setup  # noqa: E402

setup("Tableau de bord", wide=True)
assistant = get_assistant()
storage = assistant.storage
state = st.session_state

# ---------------------------------------------------------------- accès
if not settings.DASHBOARD_PASSWORD:
    st.error("Tableau de bord verrouillé : définissez DASHBOARD_PASSWORD dans le fichier .env, puis relancez.")
    st.stop()
if not state.get("admin"):
    st.title("Tableau de bord")
    with st.form("login"):
        name = st.text_input("Votre nom (inscrit dans l'historique des modifications)")
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Entrer"):
            if name.strip() and secrets.compare_digest(password.encode(), settings.DASHBOARD_PASSWORD.encode()):
                state.admin = name.strip()[:60]
                st.rerun()
            st.error("Nom manquant ou mot de passe incorrect.")
    st.stop()
actor = f"admin:{state.admin}"

# ---------------------------------------------------------------- alertes de configuration
unverified = [o.display_name for o in assistant.knowledge.organizations if o.active and not o.verified]
if unverified and settings.ROUTING_REQUIRE_VERIFIED:
    st.warning("Fiches organismes non vérifiées : " + ", ".join(unverified) + ". Tant qu'une fiche n'a pas de "
               "date de vérification dans data/organismes.yaml, ses signalements passent par la vérification "
               "humaine au lieu d'être orientés automatiquement.")
for error in assistant.knowledge.validate():
    st.error(f"Base de connaissances : {error}")

# ---------------------------------------------------------------- filtres
st.title("Tableau de bord")
all_reports = storage.list_reports(limit=2000)
orgs = sorted({(r["org_id"], r["org_name"]) for r in all_reports if r["org_id"]}, key=lambda x: x[1])
f1, f2, f3, f4 = st.columns(4)
org_filter = f1.selectbox("Organisme", [None, *[o[0] for o in orgs]],
                          format_func=lambda v: "Tous" if v is None else dict(orgs)[v])
cat_filter = f2.selectbox("Catégorie", [None, *assistant.knowledge.category_ids()],
                          format_func=lambda v: "Toutes" if v is None else category_label(assistant, v))
urg_filter = f3.selectbox("Priorité", [None, *URGENCY_LABELS],
                          format_func=lambda v: "Toutes" if v is None else URGENCY_LABELS[v])
status_filter = f4.selectbox("Statut", [None, *STATUS_LABELS],
                             format_func=lambda v: "Tous" if v is None else STATUS_LABELS[v])
reports = [r for r in all_reports
           if (not org_filter or r["org_id"] == org_filter) and (not cat_filter or r["category"] == cat_filter)
           and (not urg_filter or r["urgency"] == urg_filter) and (not status_filter or r["status"] == status_filter)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Signalements", len(all_reports))
m2.metric("À vérifier", sum(r["status"] == "NEEDS_REVIEW" for r in all_reports))
m3.metric("En cours", sum(r["status"] in ("ROUTED", "ASSIGNED", "IN_PROGRESS") for r in all_reports))
m4.metric("Résolus", sum(r["status"] in ("RESOLVED", "CLOSED") for r in all_reports))

if not reports:
    st.info("Aucun signalement ne correspond à ces filtres.")
    st.stop()

# ---------------------------------------------------------------- liste et carte
table = pd.DataFrame([{
    "Référence": r["reference"], "Créé le": r["created_at"][:16].replace("T", " "),
    "Statut": STATUS_LABELS.get(r["status"], r["status"]),
    "Catégorie": category_label(assistant, r["category"]),
    "Priorité": URGENCY_LABELS.get(r["urgency"], r["urgency"]),
    "Lieu": r["location_text"] or r["territorial_area"] or "",
    "Organisme recommandé": r["org_name"] or "À déterminer",
    "Confiance": r["confidence_organization"],
    "Description": r["description"],
} for r in reports])
tab_list, tab_map = st.tabs(["Liste", "Carte"])
tab_list.dataframe(table, hide_index=True, width="stretch",
                   column_config={"Confiance": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f")})

points = []
for r in reports:
    zone = assistant.gazetteer.get(r["zone_id"])
    if r["latitude"] is not None and r["longitude"] is not None:
        points.append({"lat": r["latitude"], "lon": r["longitude"]})
    elif zone and zone.lat is not None:
        points.append({"lat": zone.lat, "lon": zone.lon})
with tab_map:
    if points:
        st.map(pd.DataFrame(points), size=120)
        st.caption("Sans position GPS fournie par le citoyen, le point est placé au centre approximatif "
                   "de la commune, pas à l'adresse exacte.")
    else:
        st.info("Aucun de ces signalements n'a de lieu reconnu.")

# ---------------------------------------------------------------- détail et actions
st.subheader("Détail d'un signalement")
reference = st.selectbox("Référence", [r["reference"] for r in reports])
report = storage.get(reference)
history = storage.history(reference)

d1, d2 = st.columns(2)
with d1:
    st.markdown(f"**Description :** {report['description']}")
    st.markdown(f"**Lieu dit :** {report['location_text'] or '—'}  \n**Zone reconnue :** "
                f"{report['territorial_area'] or '—'}")
    st.markdown(f"**Langue :** {report['language']} · **Source :** {report['source']} · "
                f"**Priorité :** {URGENCY_LABELS.get(report['urgency'], report['urgency'])}")
    with st.expander("Message d'origine du citoyen"):
        st.text(report["transcript"] or "")
with d2:
    st.markdown(f"**Statut :** {STATUS_LABELS[report['status']]}")
    st.markdown(f"**Organisme :** {report['org_name'] or 'À déterminer'}"
                + (f" ({report['org_service']})" if report["org_service"] else ""))
    confidences = {"Problème": report["confidence_problem"], "Lieu": report["confidence_location"],
                   "Organisme": report["confidence_organization"]}
    st.markdown("**Confiance :** " + " · ".join(f"{k} {v:.2f}" if v is not None else f"{k} —"
                                                 for k, v in confidences.items()))

a1, a2 = st.columns(2)
with a1.form("status"):
    st.markdown("**Changer le statut**")
    allowed = sorted(TRANSITIONS[report["status"]])
    new_status = st.selectbox("Nouveau statut", allowed, format_func=STATUS_LABELS.get, disabled=not allowed)
    note = st.text_input("Note")
    if st.form_submit_button("Enregistrer", disabled=not allowed):
        try:
            storage.set_status(reference, new_status, actor, note)
            st.rerun()
        except StorageError as e:
            st.error(str(e))
with a2.form("reroute"):
    st.markdown("**Corriger ou réorienter l'organisme**")
    choices = assistant.organization_choices(report["zone_id"])
    target = st.selectbox("Organisme", [c[0] for c in choices], format_func=dict(choices).get)
    reason = st.text_input("Motif (obligatoire)")
    if st.form_submit_button("Réorienter"):
        try:
            assistant.reroute(reference, target, actor, reason)
            st.rerun()
        except StorageError as e:
            st.error(str(e))

h1, h2, h3 = st.tabs(["Historique de l'orientation", "Historique des statuts", "Transmissions"])
with h1:
    for row in reversed(history["routing"]):
        st.markdown(f"**{row['decided_at'][:16].replace('T', ' ')}** · {row['actor']} → "
                    f"{row['org_name'] or 'aucun organisme'}  \n{row['justification']}")
        candidates = json.loads(row["candidates_json"] or "[]")
        if len(candidates) > 1:
            st.caption("Candidats : " + " ; ".join(f"{c['org_name']} ({c['confidence']:.2f})" for c in candidates))
with h2:
    st.dataframe(pd.DataFrame([{"Date": s["changed_at"][:16].replace("T", " "),
                                "De": STATUS_LABELS.get(s["old_status"], "—"),
                                "Vers": STATUS_LABELS.get(s["new_status"], s["new_status"]),
                                "Par": s["actor"], "Note": s["note"]} for s in history["statuses"]]),
                 hide_index=True, width="stretch")
with h3:
    if history["transmissions"]:
        st.dataframe(pd.DataFrame([{"Date": t["sent_at"][:16].replace("T", " "), "Canal": t["channel"],
                                    "Destinataire": t["recipient"], "Réussie": bool(t["success"]),
                                    "Erreur": t["error"]} for t in history["transmissions"]]),
                     hide_index=True, width="stretch")
    else:
        st.info("Aucune transmission : le signalement attend une vérification humaine.")
