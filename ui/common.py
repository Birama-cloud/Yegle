"""Éléments partagés par les pages Streamlit : identité visuelle, barre du haut, composants."""
import html

import streamlit as st

from app.assistant import Assistant
from app.ratelimit import RateLimiter
from config import settings

STATUS_LABELS = {
    "RECEIVED": "Reçu", "ROUTED": "Orienté", "NEEDS_REVIEW": "En vérification", "ASSIGNED": "Affecté",
    "IN_PROGRESS": "En cours de traitement", "RESOLVED": "Résolu", "CLOSED": "Clôturé", "REJECTED": "Rejeté",
}
STATUS_TONE = {"RECEIVED": "neutral", "NEEDS_REVIEW": "warn", "ROUTED": "info", "ASSIGNED": "info",
               "IN_PROGRESS": "info", "RESOLVED": "ok", "CLOSED": "neutral", "REJECTED": "stop"}
URGENCY_LABELS = {"low": "Faible", "medium": "Moyenne", "high": "Élevée", "critical": "Critique"}
URGENCY_TONE = {"low": "neutral", "medium": "neutral", "high": "warn", "critical": "stop"}

PAGE_HOME = "Signaler.py"
PAGE_TRACK = "pages/1_Suivre_mon_signalement.py"
PAGE_ADMIN = "pages/2_Tableau_de_bord.py"

# Identité : indigo des teintures d'Afrique de l'Ouest pour l'institution, jaune des taxis
# de Dakar pour la seule action qui compte, le micro. Atkinson Hyperlegible pour le texte :
# une police dessinée pour rester lisible par tous.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&display=swap');
:root{
  --indigo:#1B2A6B; --indigo-soft:#E8EBF5; --ink:#141A33; --muted:#5C6480; --paper:#F4F5FA;
  --surface:#FFFFFF; --line:#D9DEEC; --signal:#FFC629; --signal-deep:#E0A800;
  --ok:#17794C; --ok-soft:#E2F3EA; --warn:#9A5B00; --warn-soft:#FFF1D6; --stop:#B3261E; --stop-soft:#FBE4E2;
  --body:'Atkinson Hyperlegible', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --display:'Bricolage Grotesque', 'Atkinson Hyperlegible', system-ui, sans-serif;
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button p,
.stApp [data-testid="stMarkdownContainer"]{font-family:var(--body);}
.stApp h1, .stApp h2, .stApp h3{font-family:var(--display); letter-spacing:-.01em; color:var(--ink);}
.stApp h1{font-weight:800; font-size:2rem;} .stApp h3{font-weight:600; font-size:1.2rem;}

/* habillage Streamlit retiré : l'application a sa propre barre */
header[data-testid="stHeader"]{display:none;}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], footer{display:none !important;}
.block-container{padding-top:1.1rem; padding-bottom:3rem;}

/* --- barre du haut --- */
.st-key-yg_topbar{border-bottom:1px solid var(--line); padding-bottom:.55rem; margin-bottom:1.1rem;
  align-items:center; row-gap:.2rem;}
.yg-mark{font-family:var(--display); font-weight:800; font-size:1.5rem; color:var(--indigo);
  letter-spacing:-.02em; line-height:1; display:flex; align-items:center; gap:.5rem; margin:0;}
.yg-mark i{width:.8rem; height:.8rem; border-radius:50%; background:var(--signal);
  box-shadow:0 0 0 3px var(--indigo); display:inline-block;}
.st-key-yg_topbar{flex-wrap:nowrap !important;}
.st-key-yg_topbar [data-testid="stPageLink"] a{padding:.3rem .6rem; border-radius:999px;}
.st-key-yg_topbar [data-testid="stPageLink"] a p{font-size:.92rem; color:var(--muted); font-weight:700;}
.st-key-yg_topbar [data-testid="stPageLink"] a:hover{background:var(--indigo-soft);}
.st-key-yg_topbar [data-testid="stPageLink"] a:hover p{color:var(--indigo);}
.st-key-yg_topbar [data-testid="stPageLink"] a[aria-current="page"]{background:var(--indigo);}
.st-key-yg_topbar [data-testid="stPageLink"] a[aria-current="page"] p{color:#fff;}

/* --- étapes du parcours (une vraie séquence) --- */
.yg-steps{display:flex; gap:.4rem; list-style:none; padding:0; margin:0 0 1rem;}
.yg-steps li{flex:1; font-size:.86rem; font-weight:700; color:var(--muted); padding-top:.5rem;
  border-top:4px solid var(--line); margin:0;}
.yg-steps li.done{border-top-color:var(--indigo); color:var(--indigo);}
.yg-steps li.now{border-top-color:var(--signal-deep); color:var(--ink);}

/* --- accueil citoyen --- */
.yg-hero{text-align:center; margin:.4rem 0 .2rem;}
.yg-hero h1{font-size:clamp(1.9rem, 7vw, 2.9rem); line-height:1.05; margin:0 0 .7rem; padding:0;}
.yg-hero p{color:var(--muted); font-size:1.08rem; line-height:1.5; max-width:34rem; margin:0 auto;}
.yg-note{color:var(--muted); font-size:.86rem; text-align:center; margin:.2rem 0 0;}

/* --- le micro : la seule chose voyante de la page --- */
[data-testid="stAudioInput"]{display:flex; flex-direction:column; align-items:center; margin:.8rem 0 .2rem;}
[data-testid="stAudioInput"] > label{justify-content:center; width:100%; margin-bottom:.6rem;}
[data-testid="stAudioInput"] > label p{font-weight:700; color:var(--ink); font-size:1.02rem; text-align:center;}
[data-testid="stAudioInput"] > div:last-child{display:flex; flex-direction:column; align-items:center; gap:.3rem;
  background:transparent !important; border:none !important; box-shadow:none !important;
  height:auto !important; width:100%; padding:0 !important;}
[data-testid="stAudioInput"] [data-testid="stElementToolbar"]{display:none !important;}
[data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"]){
  display:flex; align-items:center; justify-content:center; width:156px; height:156px; margin:0 !important;}
[data-testid="stAudioInputActionButton"]{width:136px !important; height:136px !important; min-height:136px;
  min-width:136px !important; max-width:none !important; flex:0 0 136px !important; border-radius:50% !important;
  padding:0 !important; cursor:pointer; background:var(--signal) !important; color:var(--indigo) !important;
  border:5px solid var(--indigo) !important; box-shadow:0 0 0 10px rgba(27,42,107,.08), 0 10px 0 -2px var(--indigo);
  transition:transform .12s ease, box-shadow .12s ease;}
[data-testid="stAudioInputActionButton"] svg{width:70px !important; height:70px !important;}
[data-testid="stAudioInputActionButton"]:hover{transform:translateY(-2px);
  box-shadow:0 0 0 12px rgba(27,42,107,.10), 0 12px 0 -2px var(--indigo);}
[data-testid="stAudioInputActionButton"]:active{transform:translateY(6px);
  box-shadow:0 0 0 10px rgba(27,42,107,.08), 0 3px 0 -2px var(--indigo);}
[data-testid="stAudioInputActionButton"]:focus-visible{outline:4px solid var(--indigo); outline-offset:8px;}
[data-testid="stAudioInputActionButton"][aria-label="Stop recording"]{background:var(--stop) !important;
  color:#fff !important; border-color:var(--stop) !important; animation:yg-rec 1.3s ease-in-out infinite;}
@keyframes yg-rec{0%,100%{box-shadow:0 0 0 8px rgba(179,38,30,.20)} 50%{box-shadow:0 0 0 24px rgba(179,38,30,.04)}}
@media (prefers-reduced-motion: reduce){[data-testid="stAudioInputActionButton"]{animation:none !important; transition:none;}}
[data-testid="stAudioInput"] > div:last-child > div:has([data-testid="stAudioInputWaveSurfer"]){
  width:min(300px, 80%); min-height:26px;}
[data-testid="stAudioInputWaveformTimeCode"]{color:var(--muted); background:transparent !important; margin:0 !important;}
/* au repos, seul le bouton est visible ; l'onde et le minuteur apparaissent pendant l'enregistrement */
[data-testid="stAudioInput"]:not(:has([aria-label="Stop recording"])) [data-testid="stAudioInputWaveformTimeCode"],
[data-testid="stAudioInput"]:not(:has([aria-label="Stop recording"])) > div:last-child > div:has([data-testid="stAudioInputWaveSurfer"]){display:none;}
.st-key-yg_prefs{justify-content:center; margin-top:.2rem;}

/* --- conversation --- */
.yg-chat{display:flex; flex-direction:column; gap:.6rem; margin:0 0 1rem;}
.yg-msg{max-width:86%; padding:.75rem 1rem; border-radius:18px; line-height:1.5; font-size:1.02rem;
  overflow-wrap:anywhere;}
.yg-msg.user{align-self:flex-end; background:var(--indigo); color:#fff; border-bottom-right-radius:4px;}
.yg-msg.bot{align-self:flex-start; background:var(--surface); color:var(--ink); border:1px solid var(--line);
  border-bottom-left-radius:4px;}
.yg-msg small{display:block; font-size:.76rem; font-weight:700; opacity:.7; margin-bottom:.15rem;}

/* --- récépissé : le résumé à confirmer et la référence remise au citoyen --- */
.yg-ticket{background:var(--surface); border:1px solid var(--line); border-radius:14px; margin:.4rem 0 1rem;
  overflow:hidden;}
.yg-ticket header{background:var(--indigo); color:#fff; padding:.8rem 1.1rem; font-family:var(--display);
  font-weight:600; font-size:1.05rem;}
.yg-ticket dl{display:grid; grid-template-columns:minmax(6.5rem, max-content) 1fr; gap:.55rem 1rem;
  margin:0; padding:1rem 1.1rem;}
.yg-ticket dt{color:var(--muted); font-size:.92rem;} .yg-ticket dd{margin:0; font-weight:700; color:var(--ink);}
.yg-ticket .dest{border-top:2px dashed var(--line); padding:.9rem 1.1rem; display:flex; gap:.7rem;
  align-items:flex-start;}
.yg-ticket .dest span{color:var(--muted); font-size:.92rem; display:block;}
.yg-ticket .dest b{font-size:1.1rem; color:var(--ink);}
.yg-dot{flex:none; width:.8rem; height:.8rem; border-radius:50%; margin-top:.35rem; background:var(--ok);}
.yg-dot.warn{background:var(--signal-deep);} .yg-dot.stop{background:var(--stop);} .yg-dot.neutral{background:var(--muted);}
.yg-dot.info{background:var(--indigo);}
.yg-ref{font-family:var(--display); font-weight:800; font-size:clamp(1.5rem, 7vw, 2.1rem); letter-spacing:.03em;
  color:var(--indigo); padding:1.1rem; text-align:center; user-select:all;}
.yg-ref-help{text-align:center; color:var(--muted); font-size:.92rem; padding:0 1.1rem 1rem; margin:0;}

/* --- suivi : où en est le signalement --- */
.yg-track{list-style:none; margin:0; padding:1rem 1.1rem;}
.yg-track li{position:relative; padding:0 0 1.1rem 1.9rem; color:var(--muted); margin:0;}
.yg-track li:last-child{padding-bottom:0;}
.yg-track li::before{content:""; position:absolute; left:0; top:.2rem; width:.95rem; height:.95rem; border-radius:50%;
  background:var(--surface); border:3px solid var(--line); box-sizing:border-box;}
.yg-track li::after{content:""; position:absolute; left:.42rem; top:1.15rem; bottom:-.2rem; width:2px; background:var(--line);}
.yg-track li:last-child::after{display:none;}
.yg-track li.done{color:var(--ink);} .yg-track li.done::before{background:var(--indigo); border-color:var(--indigo);}
.yg-track li.done::after{background:var(--indigo);}
.yg-track li.now{color:var(--ink); font-weight:700;}
.yg-track li span{font-weight:400; color:var(--muted); font-size:.92rem;}
.yg-track li.now::before{background:var(--signal); border-color:var(--indigo);}

/* --- étiquettes de statut --- */
.yg-badge{display:inline-flex; align-items:center; gap:.4rem; padding:.18rem .6rem; border-radius:999px;
  font-size:.84rem; font-weight:700; white-space:nowrap; background:var(--indigo-soft); color:var(--indigo);}
.yg-badge::before{content:""; width:.5rem; height:.5rem; border-radius:50%; background:currentColor;}
.yg-badge.ok{background:var(--ok-soft); color:var(--ok);} .yg-badge.warn{background:var(--warn-soft); color:var(--warn);}
.yg-badge.stop{background:var(--stop-soft); color:var(--stop);} .yg-badge.neutral{background:#ECEEF4; color:var(--muted);}

/* --- tableau de bord --- */
.yg-kpis{display:grid; grid-template-columns:repeat(4, 1fr); gap:.8rem; margin:.2rem 0 1.4rem;}
.yg-kpi{background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:.9rem 1rem;
  border-top:4px solid var(--indigo);}
.yg-kpi.warn{border-top-color:var(--signal-deep);} .yg-kpi.ok{border-top-color:var(--ok);}
.yg-kpi b{font-family:var(--display); font-weight:800; font-size:2.1rem; line-height:1; display:block; color:var(--ink);}
.yg-kpi span{color:var(--muted); font-size:.92rem;}
.yg-tablewrap{overflow-x:auto; background:var(--surface); border:1px solid var(--line); border-radius:12px;}
.yg-table{width:100%; border-collapse:collapse; font-size:.9rem; min-width:900px; margin:0;}
.yg-table th, .yg-table td{border:none !important; border-bottom:1px solid #ECEFF7 !important; padding:.6rem .7rem;
  text-align:left; vertical-align:top; color:var(--ink);}
.yg-table th{font-weight:700; color:var(--muted); background:#FAFBFE; border-bottom:1px solid var(--line) !important;
  white-space:nowrap;}
.yg-table tr:last-child td{border-bottom:none !important;}
.yg-table td.ref{font-weight:700; white-space:nowrap; color:var(--indigo);}
.yg-table td.when{white-space:nowrap; color:var(--muted);}
.yg-table td.place{min-width:11rem;}
.yg-conf{display:flex; align-items:center; gap:.45rem; white-space:nowrap;}
.yg-conf i{display:block; width:54px; height:6px; border-radius:3px; background:#E3E7F2; overflow:hidden;}
.yg-conf i u{display:block; height:100%; background:var(--indigo);}
.yg-conf.low i u{background:var(--signal-deep);}
.yg-panel{background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:1rem 1.1rem; height:100%;}
.yg-panel h4{font-family:var(--display); font-weight:600; font-size:1rem; margin:0 0 .6rem; padding:0; color:var(--indigo);}
.yg-panel p{margin:.25rem 0; line-height:1.5;} .yg-panel p span{color:var(--muted);}
.yg-legend{display:flex; flex-wrap:wrap; gap:.4rem 1.1rem; margin:.6rem 0 .2rem; font-size:.88rem; color:var(--muted);}
.yg-legend span{display:inline-flex; align-items:center; gap:.4rem;}
.yg-legend i{width:.8rem; height:.8rem; border-radius:50%; display:inline-block;}
.yg-legend i.ring{background:transparent; border:3px solid var(--signal);}
.yg-live{display:inline-flex; align-items:center; gap:.45rem; font-size:.88rem; color:var(--muted);}
.yg-live::before{content:""; width:.55rem; height:.55rem; border-radius:50%; background:var(--ok);
  animation:yg-live 2s ease-in-out infinite;}
@keyframes yg-live{50%{opacity:.3}}
@media (prefers-reduced-motion: reduce){.yg-live::before{animation:none;}}
.yg-alert{background:var(--stop-soft); border:1px solid var(--stop); border-left:6px solid var(--stop);
  border-radius:12px; padding:.75rem 1rem; color:var(--ink); line-height:1.45;}
.yg-alert b{color:var(--stop); margin-right:.35rem;}
.yg-alert span{display:block; color:var(--muted); font-size:.9rem;}
.yg-log{border-left:3px solid var(--indigo-soft); padding:.1rem 0 .1rem .9rem; margin:0 0 .9rem;}
.yg-log b{display:block;} .yg-log span{color:var(--muted); font-size:.9rem;}

.stApp [data-testid="stForm"]{background:var(--surface); border:1px solid var(--line); border-radius:12px;}
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"]{border-radius:10px; font-weight:700; min-height:2.9rem;}
.stApp button[kind="secondary"], .stApp button[kind="secondaryFormSubmit"]{border-radius:10px; min-height:2.9rem;
  background:var(--surface); border:1px solid var(--line);}
.stApp button:focus-visible{outline:3px solid var(--signal-deep); outline-offset:2px;}
@media (max-width:640px){
  .yg-kpis{grid-template-columns:repeat(2, 1fr);}
  .yg-msg{max-width:94%;}
}
</style>
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def setup(title: str, wide: bool = False) -> None:
    st.set_page_config(page_title=f"{title} | {settings.APP_NAME}", page_icon="📣",
                       layout="wide" if wide else "centered", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    width = "1280px" if wide else "720px"
    st.markdown(f"<style>.block-container{{max-width:{width};}}</style>", unsafe_allow_html=True)
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="yg_topbar"):
        st.markdown(f"<p class='yg-mark'><i></i>{esc(settings.APP_NAME)}</p>", unsafe_allow_html=True, width="stretch")
        for page, label in ((PAGE_HOME, "Signaler"), (PAGE_TRACK, "Suivre"), (PAGE_ADMIN, "Services")):
            try:
                st.page_link(page, label=label, width="content")
            except Exception:  # noqa: BLE001  (page lancée seule, hors de l'application : pas de menu)
                break


def steps(current: int, labels=("Décrire", "Vérifier", "Envoyé")) -> None:
    items = "".join(f"<li class='{'done' if i < current else 'now' if i == current else ''}'>{i + 1}. {esc(label)}</li>"
                    for i, label in enumerate(labels))
    st.markdown(f"<ol class='yg-steps'>{items}</ol>", unsafe_allow_html=True)


def badge(status: str) -> str:
    return f"<span class='yg-badge {STATUS_TONE.get(status, 'info')}'>{esc(STATUS_LABELS.get(status, status))}</span>"


def when_short(iso: str) -> str:
    """Version compacte pour les tableaux : 08/10 17:56"""
    try:
        return f"{iso[8:10]}/{iso[5:7]} {iso[11:16]}"
    except (TypeError, IndexError):
        return ""


def when(iso: str) -> str:
    """2026-10-08T17:56:00+00:00 -> 08/10/2026 à 17:56"""
    try:
        return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]} à {iso[11:16]}"
    except (TypeError, IndexError):
        return ""


@st.cache_resource(show_spinner="Démarrage…")
def get_assistant() -> Assistant:
    return Assistant()


@st.cache_resource
def analyze_limiter() -> RateLimiter:
    """Messages analysés par adresse IP (chacun peut appeler le modèle d'IA), toutes sessions confondues."""
    return RateLimiter(settings.RATE_ANALYZE_PER_MINUTE, 60)


@st.cache_resource
def login_limiter() -> RateLimiter:
    """Échecs de connexion au tableau de bord, partagés entre toutes les sessions."""
    return RateLimiter(settings.LOGIN_MAX_FAILURES, 15 * 60)


def client_ip() -> str:
    try:
        ip = st.context.ip_address
    except Exception:  # noqa: BLE001  (hors d'une session Streamlit)
        ip = None
    return ip if isinstance(ip, str) and ip else "local"


def category_label(assistant: Assistant, category_id: str, lang: str = "fr") -> str:
    category = assistant.knowledge.categories.get(category_id)
    return category.name(lang) if category else category_id
