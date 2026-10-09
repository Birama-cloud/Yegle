"""Espace services : tous les signalements, leur orientation et leur suivi."""
import json
import math
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from app.storage import TRANSITIONS, StorageError  # noqa: E402
from config import settings  # noqa: E402
from ui import live_map  # noqa: E402
from ui.common import (PAGE_ADMIN, STATUS_LABELS, URGENCY_LABELS, badge, category_label, client_ip,  # noqa: E402
                       esc, get_assistant, icon, login_limiter, setup, when, when_short)

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]

band, right = setup("Espace services", theme="light", width="1320px", active=PAGE_ADMIN)
assistant = get_assistant()
storage = assistant.storage
state = st.session_state


def band_title(title: str, subtitle: str = "") -> str:
    return (f"<h1 class='yg-band-title'>{esc(title)}</h1>"
            + (f"<p class='yg-band-sub'>{esc(subtitle)}</p>" if subtitle else ""))


# ---------------------------------------------------------------- accès
if not settings.DASHBOARD_PASSWORD:
    with band:
        st.markdown(band_title("Espace services", "Réservé aux équipes qui traitent les signalements."),
                    unsafe_allow_html=True)
    st.write("")
    st.error("Espace verrouillé. Définissez DASHBOARD_PASSWORD dans le fichier .env, puis relancez l'application.")
    st.stop()
if not state.get("admin"):
    with band:
        st.markdown(band_title("Espace services", "Réservé aux équipes qui traitent les signalements."),
                    unsafe_allow_html=True)
    st.write("")
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle, st.container(key="yg_login"):
        st.markdown("<h3 style='margin:0 0 .2rem'>Connexion</h3>", unsafe_allow_html=True)
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

# ---------------------------------------------------------------- bandeau : personne connectée, titre, compteurs
with right:
    st.markdown(f"<div class='yg-who'><span>{esc(state.admin)}, administration</span>"
                f"<i>{esc(state.admin[:1].upper())}</i></div>", unsafe_allow_html=True)
    if st.button("Se déconnecter", key="logout"):
        del state["admin"]
        st.rerun()

all_reports = storage.list_reports(limit=2000)
counts = {
    "total": len(all_reports),
    "review": sum(r["status"] == "NEEDS_REVIEW" for r in all_reports),
    "open": sum(r["status"] in ("ROUTED", "ASSIGNED", "IN_PROGRESS") for r in all_reports),
    "solved": sum(r["status"] in ("RESOLVED", "CLOSED") for r in all_reports),
}
today = datetime.now(timezone.utc)                     # heure de Dakar = temps universel
with band:
    with st.container(horizontal=True, vertical_alignment="bottom", key="yg_head"):
        st.markdown(band_title("Signalements", f"{JOURS[today.weekday()].capitalize()} {today.day} "
                                               f"{MOIS[today.month - 1]} {today.year}, région de Dakar"),
                    unsafe_allow_html=True, width="stretch")
        if counts["review"]:
            plural = "s attendent" if counts["review"] > 1 else " attend"
            st.markdown(f"<span class='yg-flag'>{icon('shield')}{counts['review']} signalement{plural} "
                        "une vérification par l'équipe</span>", unsafe_allow_html=True, width="content")
    st.markdown(
        "<div class='yg-kpis'>"
        f"<div class='yg-kpi'><i class='ic'>{icon('mic')}</i><div><b>{counts['total']}</b>"
        "<span>Signalements reçus</span></div></div>"
        f"<div class='yg-kpi warn'><i class='ic'>{icon('search')}</i><div><b>{counts['review']}</b>"
        "<span>À vérifier</span></div></div>"
        f"<div class='yg-kpi prog'><i class='ic'>{icon('building')}</i><div><b>{counts['open']}</b>"
        "<span>Chez les services</span></div></div>"
        f"<div class='yg-kpi ok'><i class='ic'>{icon('check')}</i><div><b>{counts['solved']}</b>"
        "<span>Résolus</span></div></div></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- alertes d'urgence, avant tout le reste
for alert in storage.list_alerts():
    place = alert["location_text"] or alert["territorial_area"] or "lieu non précisé"
    notified = ""
    if alert["notify_error"]:
        notified = f"<span>Notification externe en échec : {esc(alert['notify_error'])}</span>"
    elif alert["notified"]:
        notified = "<span>Notification externe envoyée</span>"
    box, act = st.columns([5, 1], vertical_alignment="center")
    box.markdown(
        f"<div class='yg-alert'><b>Urgence · {esc(alert['reference'])}</b> {esc(alert['description'])}"
        f"<span>{esc(place)} · {esc(when(alert['created_at']))} · "
        f"{esc(alert['org_name'] or 'organisme à déterminer')}</span>"
        f"<span>{esc(alert['reason'])}</span>{notified}</div>", unsafe_allow_html=True)
    if act.button("Pris en charge", key=f"ack_{alert['id']}", type="primary", width="stretch"):
        try:
            storage.acknowledge_alert(alert["id"], actor)
        except StorageError as e:
            st.toast(str(e))
        st.rerun()

unverified = [o.display_name for o in assistant.knowledge.organizations if o.active and not o.verified]
if unverified and settings.ROUTING_REQUIRE_VERIFIED:
    st.markdown("<p class='yg-note-light'>Fiches organismes à vérifier : " + esc(", ".join(unverified))
                + ". Sans date de vérification dans data/organismes.yaml, leurs signalements arrivent ici en "
                "vérification au lieu d'être orientés automatiquement.</p>", unsafe_allow_html=True)
for error in assistant.knowledge.validate():
    st.error(f"Base de connaissances : {error}")

if not all_reports:
    @st.fragment(run_every=live_map.REFRESH_S)
    def wait_for_first_report():
        if storage.list_reports(limit=1):
            st.rerun(scope="app")
        st.info("Aucun signalement pour l'instant. Ils apparaîtront ici dès qu'un citoyen en enverra un.")

    wait_for_first_report()
    st.stop()

# ---------------------------------------------------------------- deux colonnes : liste à gauche, détail à droite
left, right_col = st.columns([2.3, 1], gap="medium")
list_card = left.container(key="yg_listcard")
detail_card = right_col.container(key="yg_detail")

with list_card:
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


def matches(r: dict) -> bool:
    return ((not org_filter or r["org_id"] == org_filter) and (not cat_filter or r["category"] == cat_filter)
            and (not urg_filter or r["urgency"] == urg_filter) and (not status_filter or r["status"] == status_filter))


reports = [r for r in all_reports if matches(r)]
if not reports:
    list_card.info("Aucun signalement ne correspond à ces filtres. Élargissez la sélection.")
    st.stop()

# Un tableau HTML n'est pas cliquable : le signalement affiché se choisit ici, et sa ligne est surlignée.
with detail_card:
    reference = st.selectbox("Signalement affiché", [r["reference"] for r in reports])
report = storage.get(reference)
history = storage.history(reference)


# ---------------------------------------------------------------- liste et carte
def confidence_cell(value) -> str:
    if value is None:
        return "<span class='na'>Aucune</span>"
    low = " low" if value < settings.ROUTING_MIN_CONFIDENCE else ""
    return (f"<span class='yg-conf{low}'><i><u style='width:{round(value * 100)}%'></u></i>"
            f"{value:.2f}".replace(".", ",") + "</span>")


def received(iso: str) -> str:
    """Heure pour les signalements du jour, date (jj/mm) pour les autres."""
    return iso[11:16] if iso[:10] == today.date().isoformat() else when_short(iso)[:5]


def urgency_mark(urgency: str) -> str:
    return {"critical": " <em class='urg'>· urgent</em>", "high": " <em class='urg'>· priorité élevée</em>"}.get(urgency, "")


def row(r: dict) -> str:
    place = r["location_text"] or r["territorial_area"]
    return (f"<tr class='{'sel' if r['reference'] == reference else ''}'>"
            f"<td class='ref'>{esc(r['reference'])}</td><td class='when'>{esc(received(r['created_at']))}</td>"
            f"<td>{badge(r['status'])}</td>"
            f"<td class='cat'>{icon(r['category'])}{esc(category_label(assistant, r['category']))}</td>"
            f"<td class='place'>{esc(place) if place else '<span class=na>Non précisé</span>'}{urgency_mark(r['urgency'])}</td>"
            f"<td class='org'>{esc(r['org_name']) if r['org_name'] else '<span class=na>À déterminer</span>'}</td>"
            f"<td>{confidence_cell(r['confidence_organization'])}</td></tr>")


with list_card:
    tab_list, tab_map = st.tabs([f"Liste ({len(reports)})", "Carte en direct"])
    tab_list.markdown(
        "<div class='yg-tablewrap'><table class='yg-table'><thead><tr><th>Référence</th><th>Reçu</th>"
        "<th>Statut</th><th>Catégorie</th><th>Lieu</th><th>Organisme</th><th>Confiance</th></tr></thead>"
        f"<tbody>{''.join(row(r) for r in reports)}</tbody></table></div>", unsafe_allow_html=True)


@st.fragment(run_every=live_map.REFRESH_S)
def show_live_map(known: frozenset):
    """Relit la base toutes les REFRESH_S secondes : seule la carte se redessine, pas la page."""
    fresh = [r for r in storage.list_reports(limit=2000) if matches(r)]
    alert_refs = {a["reference"] for a in storage.list_alerts()}
    points = live_map.map_points(fresh, assistant.gazetteer, alert_refs,
                                 {"status": STATUS_LABELS, "urgency": URGENCY_LABELS})
    head, action = st.columns([3, 1], vertical_alignment="center")
    head.markdown(f"<span class='yg-live'>En direct · {len(points)} signalement(s) sur la carte · "
                  f"mis à jour à {datetime.now(timezone.utc):%H:%M:%S}</span>", unsafe_allow_html=True)
    new = [r for r in fresh if r["reference"] not in known]
    if new and action.button(f"{len(new)} nouveau(x) · actualiser la liste", type="primary", width="stretch"):
        st.rerun(scope="app")
    if points:
        st.pydeck_chart(live_map.deck(points), height=520, key="carte_direct")
    else:
        st.info("Aucun de ces signalements n'a de lieu reconnu.")
    st.markdown(live_map.legend_html(), unsafe_allow_html=True)
    st.caption("Sans position GPS fournie par le citoyen, le point est placé près du centre de la commune, "
               "pas à l'adresse exacte. Heures en temps universel (heure de Dakar).")


with tab_map:
    show_live_map(frozenset(r["reference"] for r in reports))


# ---------------------------------------------------------------- détail du signalement affiché
def number(value) -> str:
    return "non mesurée" if value is None else f"{value:.2f}".replace(".", ",")


def bar(label: str, value, threshold: float | None) -> str:
    low = " low" if value is not None and threshold is not None and value < threshold else ""
    width = 0 if value is None else round(value * 100)
    return (f"<div class='yg-bar{low}'><span>{esc(label)}</span><i><u style='width:{width}%'></u></i>"
            f"<span>{number(value)}</span></div>")


if report["transcript_purged_at"]:
    said = (f"Message effacé le {when(report['transcript_purged_at'])}, à la fin de la durée de conservation "
            f"({settings.TRANSCRIPT_RETENTION_DAYS} jours).")
else:
    said = report["transcript"] or ""
kept = (f"Effacé automatiquement {settings.TRANSCRIPT_RETENTION_DAYS} jours après le signalement."
        if settings.TRANSCRIPT_RETENTION_DAYS > 0 and not report["transcript_purged_at"] else "")
source = "vocal" if report["source"] == "voice" else "écrit"
org_title = "Organisme recommandé" if report["status"] in ("RECEIVED", "NEEDS_REVIEW") else "Organisme"
alerts_html = "".join(
    f"<li>{icon('shield')}<span><b>Alerte d'urgence</b> : "
    + (f"prise en charge par {esc(a['acknowledged_by'])} le {esc(when(a['acknowledged_at']))}"
       if a["acknowledged_at"] else "en attente de prise en charge") + "</span></li>"
    for a in history["alerts"])
events_html = "".join(
    f"<li>{icon('check')}<span><b>{esc(s['changed_at'][11:16])}</b> "
    f"{esc(STATUS_LABELS.get(s['new_status'], s['new_status']))}"
    + (f" : {esc(s['note'])}" if s["note"] else "") + "</span></li>"
    for s in list(reversed(history["statuses"]))[:2])

with detail_card:
    st.markdown(
        f"<div class='yg-dhead'><b>{esc(report['reference'])}</b>{badge(report['status'])}</div>"
        f"<div class='yg-quote'><small>{icon('mic' if source == 'vocal' else 'pen')}Message {source}, "
        f"{esc(settings.LANGS.get(report['language'], report['language']))}</small>"
        f"<p>{esc(said)}</p><span>{esc(report['description'])}</span>"
        + (f"<em>{esc(kept)}</em>" if kept else "") + "</div>"
        "<div class='yg-mini'>"
        f"<div><span>Lieu reconnu</span><b>{esc(report['territorial_area'] or report['location_text'] or 'Non précisé')}</b></div>"
        f"<div><span>Priorité</span><b>{esc(URGENCY_LABELS.get(report['urgency'], report['urgency']))}</b></div></div>"
        f"<div class='yg-org'><small>{org_title}</small>"
        f"<b>{esc(report['org_name'] or 'À déterminer')}"
        + (f" <em>· {esc(report['org_service'])}</em>" if report["org_service"] else "") + "</b>"
        + bar("Problème", report["confidence_problem"], settings.MIN_CONFIDENCE_PROBLEM)
        + bar("Lieu", report["confidence_location"], None)
        + bar("Organisme", report["confidence_organization"], settings.ROUTING_MIN_CONFIDENCE) + "</div>"
        f"<ul class='yg-events'>{alerts_html}{events_html}</ul>", unsafe_allow_html=True)

    with st.form("status"):
        allowed = sorted(TRANSITIONS[report["status"]])
        new_status = st.selectbox("Nouveau statut", allowed, format_func=STATUS_LABELS.get, disabled=not allowed)
        note = st.text_input("Note")
        if st.form_submit_button("Changer le statut", type="primary", disabled=not allowed, width="stretch"):
            try:
                storage.set_status(reference, new_status, actor, note)
                st.rerun()
            except StorageError as e:
                st.error(str(e))
    with st.form("reroute"):
        choices = assistant.organization_choices(report["zone_id"])
        target = st.selectbox("Réorienter vers", [c[0] for c in choices], format_func=dict(choices).get)
        reason = st.text_input("Motif (obligatoire)")
        if st.form_submit_button("Réorienter", width="stretch"):
            try:
                assistant.reroute(reference, target, actor, reason)
                st.rerun()
            except StorageError as e:
                st.error(str(e))

# ---------------------------------------------------------------- historiques complets
st.write("")
h1, h2, h3 = st.tabs(["Historique de l'orientation", "Historique des statuts", "Transmissions"])
with h1:
    for row_ in reversed(history["routing"]):
        candidates = json.loads(row_["candidates_json"] or "[]")
        extra = ""
        if len(candidates) > 1:
            extra = "<span>Candidats : " + " ; ".join(
                f"{esc(c['org_name'])} ({c['confidence']:.2f})" for c in candidates) + "</span>"
        st.markdown(f"<div class='yg-log'><b>{esc(row_['org_name'] or 'Aucun organisme')}</b>"
                    f"<span>{esc(when(row_['decided_at']))}, par {esc(row_['actor'])}</span><br>"
                    f"{esc(row_['justification'])}{'<br>' + extra if extra else ''}</div>", unsafe_allow_html=True)
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
