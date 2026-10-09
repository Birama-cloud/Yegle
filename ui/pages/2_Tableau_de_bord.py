"""Espace services : tous les signalements, leur orientation et leur suivi."""
import json
import math
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.storage import TRANSITIONS, StorageError  # noqa: E402
from config import settings  # noqa: E402
from ui.common import (STATUS_LABELS, URGENCY_LABELS, URGENCY_TONE, badge, category_label,  # noqa: E402
                       client_ip, esc, get_assistant, login_limiter, setup, when, when_short)

setup("Espace services", wide=True)
assistant = get_assistant()
storage = assistant.storage
state = st.session_state

# ---------------------------------------------------------------- accès
if not settings.DASHBOARD_PASSWORD:
    st.markdown("<h1>Espace services</h1>", unsafe_allow_html=True)
    st.error("Espace verrouillé. Définissez DASHBOARD_PASSWORD dans le fichier .env, puis relancez l'application.")
    st.stop()
if not state.get("admin"):
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle:
        st.markdown("<h1>Espace services</h1>", unsafe_allow_html=True)
        st.write("Réservé aux équipes qui traitent les signalements.")
        with st.form("login"):
            name = st.text_input("Votre nom", help="Il est inscrit à côté de chaque modification que vous faites.")
            password = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter", type="primary", width="stretch"):
                limiter, ip = login_limiter(), client_ip()
                if wait := limiter.check(ip):
                    st.error(f"Trop d'essais. Réessayez dans {math.ceil(wait / 60)} min.")
                elif name.strip() and secrets.compare_digest(password.encode(),
                                                             settings.DASHBOARD_PASSWORD.encode()):
                    state.admin = name.strip()[:60]
                    st.rerun()
                else:
                    limiter.hit(ip)
                    st.error("Nom manquant ou mot de passe incorrect.")
    st.stop()
actor = f"admin:{state.admin}"

# ---------------------------------------------------------------- en-tête
head, who = st.columns([4, 1], vertical_alignment="bottom")
head.markdown("<h1>Signalements</h1>", unsafe_allow_html=True)
if who.button(f"Se déconnecter ({state.admin})", width="stretch"):
    del state["admin"]
    st.rerun()

unverified = [o.display_name for o in assistant.knowledge.organizations if o.active and not o.verified]
if unverified and settings.ROUTING_REQUIRE_VERIFIED:
    st.warning("Fiches organismes à vérifier : " + ", ".join(unverified) + ". Sans date de vérification dans "
               "data/organismes.yaml, leurs signalements arrivent ici en vérification au lieu d'être orientés "
               "automatiquement.")
for error in assistant.knowledge.validate():
    st.error(f"Base de connaissances : {error}")

all_reports = storage.list_reports(limit=2000)
counts = {
    "total": len(all_reports),
    "review": sum(r["status"] == "NEEDS_REVIEW" for r in all_reports),
    "open": sum(r["status"] in ("ROUTED", "ASSIGNED", "IN_PROGRESS") for r in all_reports),
    "solved": sum(r["status"] in ("RESOLVED", "CLOSED") for r in all_reports),
}
st.markdown(
    "<div class='yg-kpis'>"
    f"<div class='yg-kpi'><b>{counts['total']}</b><span>Signalements reçus</span></div>"
    f"<div class='yg-kpi warn'><b>{counts['review']}</b><span>À vérifier par l'équipe</span></div>"
    f"<div class='yg-kpi'><b>{counts['open']}</b><span>Chez les services</span></div>"
    f"<div class='yg-kpi ok'><b>{counts['solved']}</b><span>Résolus</span></div></div>", unsafe_allow_html=True)

if not all_reports:
    st.info("Aucun signalement pour l'instant. Ils apparaîtront ici dès qu'un citoyen en enverra un.")
    st.stop()

# ---------------------------------------------------------------- filtres
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
if not reports:
    st.info("Aucun signalement ne correspond à ces filtres. Élargissez la sélection.")
    st.stop()


# ---------------------------------------------------------------- liste et carte
def confidence_cell(value) -> str:
    if value is None:
        return "<span style='color:var(--muted)'>Aucune</span>"
    low = " low" if value < settings.ROUTING_MIN_CONFIDENCE else ""
    return (f"<span class='yg-conf{low}'><i><u style='width:{round(value * 100)}%'></u></i>"
            f"{value:.2f}".replace(".", ",") + "</span>")


rows = "".join(
    f"<tr><td class='ref'>{esc(r['reference'])}</td><td class='when'>{esc(when_short(r['created_at']))}</td>"
    f"<td>{badge(r['status'])}</td><td>{esc(category_label(assistant, r['category']))}</td>"
    f"<td><span class='yg-badge {URGENCY_TONE.get(r['urgency'], 'neutral')}'>"
    f"{esc(URGENCY_LABELS.get(r['urgency'], r['urgency']))}</span></td>"
    f"<td class='place'>{esc(r['location_text'] or r['territorial_area'] or 'Non précisé')}</td>"
    f"<td>{esc(r['org_name'] or 'À déterminer')}</td><td>{confidence_cell(r['confidence_organization'])}</td></tr>"
    for r in reports)
tab_list, tab_map = st.tabs([f"Liste ({len(reports)})", "Carte"])
tab_list.markdown(
    "<div class='yg-tablewrap'><table class='yg-table'><thead><tr><th>Référence</th><th>Créé le</th><th>Statut</th>"
    "<th>Catégorie</th><th>Priorité</th><th>Lieu</th><th>Organisme</th><th>Confiance</th></tr></thead>"
    f"<tbody>{rows}</tbody></table></div>", unsafe_allow_html=True)

points = []
for r in reports:
    zone = assistant.gazetteer.get(r["zone_id"])
    if r["latitude"] is not None and r["longitude"] is not None:
        points.append({"lat": r["latitude"], "lon": r["longitude"]})
    elif zone and zone.lat is not None:
        points.append({"lat": zone.lat, "lon": zone.lon})
with tab_map:
    if points:
        st.map(pd.DataFrame(points), size=140, color="#1B2A6B")
        st.caption("Sans position GPS fournie par le citoyen, le point est placé au centre approximatif "
                   "de la commune, pas à l'adresse exacte.")
    else:
        st.info("Aucun de ces signalements n'a de lieu reconnu.")

# ---------------------------------------------------------------- détail et actions
st.markdown("<h3>Traiter un signalement</h3>", unsafe_allow_html=True)
reference = st.selectbox("Référence", [r["reference"] for r in reports], label_visibility="collapsed")
report = storage.get(reference)
history = storage.history(reference)


def number(value) -> str:
    return "non mesurée" if value is None else f"{value:.2f}".replace(".", ",")


d1, d2 = st.columns(2)
d1.markdown(
    "<div class='yg-panel'><h4>Ce que dit le citoyen</h4>"
    f"<p>{esc(report['description'])}</p>"
    f"<p><span>Lieu dit :</span> {esc(report['location_text'] or 'non précisé')}</p>"
    f"<p><span>Zone reconnue :</span> {esc(report['territorial_area'] or 'aucune')}</p>"
    f"<p><span>Priorité :</span> {esc(URGENCY_LABELS.get(report['urgency'], report['urgency']))}</p>"
    f"<p><span>Langue :</span> {esc(settings.LANGS.get(report['language'], report['language']))}, "
    f"<span>reçu par</span> {'la voix' if report['source'] == 'voice' else 'écrit'}</p></div>",
    unsafe_allow_html=True)
d2.markdown(
    "<div class='yg-panel'><h4>Orientation</h4>"
    f"<p>{badge(report['status'])}</p>"
    f"<p><span>Organisme :</span> <b>{esc(report['org_name'] or 'À déterminer')}</b>"
    + (f" ({esc(report['org_service'])})" if report["org_service"] else "") + "</p>"
    f"<p><span>Confiance dans l'organisme :</span> {number(report['confidence_organization'])}</p>"
    f"<p><span>Confiance dans le lieu :</span> {number(report['confidence_location'])}</p>"
    f"<p><span>Confiance dans le problème :</span> {number(report['confidence_problem'])}</p></div>",
    unsafe_allow_html=True)
with st.expander("Message d'origine du citoyen"):
    st.text(report["transcript"] or "")

a1, a2 = st.columns(2)
with a1.form("status"):
    st.markdown("**Changer le statut**")
    allowed = sorted(TRANSITIONS[report["status"]])
    new_status = st.selectbox("Nouveau statut", allowed, format_func=STATUS_LABELS.get, disabled=not allowed)
    note = st.text_input("Note")
    if st.form_submit_button("Enregistrer le statut", type="primary", disabled=not allowed):
        try:
            storage.set_status(reference, new_status, actor, note)
            st.rerun()
        except StorageError as e:
            st.error(str(e))
with a2.form("reroute"):
    st.markdown("**Réorienter vers un autre organisme**")
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
        candidates = json.loads(row["candidates_json"] or "[]")
        extra = ""
        if len(candidates) > 1:
            extra = "<span>Candidats : " + " ; ".join(
                f"{esc(c['org_name'])} ({c['confidence']:.2f})" for c in candidates) + "</span>"
        st.markdown(f"<div class='yg-log'><b>{esc(row['org_name'] or 'Aucun organisme')}</b>"
                    f"<span>{esc(when(row['decided_at']))}, par {esc(row['actor'])}</span><br>"
                    f"{esc(row['justification'])}{'<br>' + extra if extra else ''}</div>", unsafe_allow_html=True)
with h2:
    for s in reversed(history["statuses"]):
        st.markdown(f"<div class='yg-log'><b>{esc(STATUS_LABELS.get(s['new_status'], s['new_status']))}</b>"
                    f"<span>{esc(when(s['changed_at']))}, par {esc(s['actor'])}</span>"
                    + (f"<br>{esc(s['note'])}" if s["note"] else "") + "</div>", unsafe_allow_html=True)
with h3:
    if not history["transmissions"]:
        st.info("Rien n'a été transmis : ce signalement attend une vérification.")
    for t in reversed(history["transmissions"]):
        result = "Réussie" if t["success"] else f"Échec : {esc(t['error'])}"
        channel = {"internal_queue": "file interne", "webhook": "webhook"}.get(t["channel"], t["channel"])
        st.markdown(f"<div class='yg-log'><b>{esc(t['recipient'] or 'Destinataire inconnu')}</b>"
                    f"<span>{esc(when(t['sent_at']))}, par {esc(channel)}</span><br>{result}</div>",
                    unsafe_allow_html=True)
