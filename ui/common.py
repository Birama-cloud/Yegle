"""Éléments partagés par les pages Streamlit : identité visuelle, barre du haut, composants.

Deux styles pour un même produit : sombre pour les pages du citoyen, clair (blanc et bleu marine)
pour l'espace services. Le thème de .streamlit/config.toml est clair ; les pages citoyen passent
en sombre par le CSS de DARK_CSS. Logo, police (Outfit) et bleu sont communs aux deux.
"""
import html
from urllib.parse import quote

import streamlit as st

from app.assistant import Assistant
from app.ratelimit import RateLimiter
from config import settings

STATUS_LABELS = {
    "RECEIVED": "Reçu", "ROUTED": "Orienté", "NEEDS_REVIEW": "En vérification", "ASSIGNED": "Affecté",
    "IN_PROGRESS": "En cours de traitement", "RESOLVED": "Résolu", "CLOSED": "Clôturé", "REJECTED": "Rejeté",
}
STATUS_TONE = {"RECEIVED": "neutral", "NEEDS_REVIEW": "warn", "ROUTED": "info", "ASSIGNED": "progress",
               "IN_PROGRESS": "progress", "RESOLVED": "ok", "CLOSED": "neutral", "REJECTED": "stop"}
URGENCY_LABELS = {"low": "Faible", "medium": "Moyenne", "high": "Élevée", "critical": "Critique"}
URGENCY_TONE = {"low": "neutral", "medium": "neutral", "high": "warn", "critical": "stop"}

PAGE_HOME = "Signaler.py"
PAGE_TRACK = "pages/1_Suivre_mon_signalement.py"
PAGE_ADMIN = "pages/2_Tableau_de_bord.py"

# Icônes au trait (24 x 24), dessinées en SVG : pas de dépendance, couleur héritée du texte.
ICONS = {
    "mic": "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z M19 11a7 7 0 0 1-14 0 M12 18v3",
    "search": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M21 21l-4.3-4.3",
    "check": "M5 12.5l4.5 4.5L19 7.5",
    "building": "M4 21V5l8-3v19 M12 9h8v12 M8 7v.01 M8 11v.01 M8 15v.01 M16 13v.01 M16 17v.01 M2 21h20",
    "shield": "M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z",
    "pin": "M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z M12 7.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
    "arrow": "M5 12h14 M13 6l6 6-6 6",
    "up": "M12 19V5 M6 11l6-6 6 6",
    "pen": "M4 20h4L19 9l-4-4L4 16z",
    "eau": "M12 2.7c-3 3.6-6 7-6 10.3a6 6 0 0 0 12 0c0-3.3-3-6.7-6-10.3z",
    "assainissement": "M2 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0 M2 14c2-2 4-2 6 0s4 2 6 0 4-2 6 0 M2 20c2-2 4-2 6 0",
    "electricite": "M13 2 4 14h7l-1 8 9-12h-7z",
    "eclairage_public": "M9 18h6 M10 22h4 M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 0 12 2z",
    "voirie": "M5 21 9.5 3 M19 21 14.5 3 M12 5v2 M12 10.5v2 M12 16v2.5",
    "proprete": "M3 6h18 M8 6V4h8v2 M6 6l1 15h10l1-15 M10 10v7 M14 10v7",
    "infrastructure": "M4 21V5l8-3v19 M12 9h8v12 M2 21h20",
    "autre": "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z M12 8v5 M12 16v.01",
}


def icon(name: str, cls: str = "yg-ico") -> str:
    path = ICONS.get(name, ICONS["autre"])
    return (f"<svg class='{cls}' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' "
            f"stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><path d='{path}'/></svg>")


def _waves(flip: bool) -> str:
    """Barres d'onde en dégradé de chaque côté du micro (image SVG en CSS, purement décorative)."""
    heights = [14, 26, 44, 30, 62, 88, 56, 110, 72, 40, 96, 52, 30, 18]
    if flip:
        heights = heights[::-1]
    bars = "".join(f"<rect x='{4 + i * 14}' y='{60 - h / 2}' width='5' height='{h}' rx='2.5'/>"
                   for i, h in enumerate(heights))
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 120'><defs><linearGradient id='g' x1='0' "
           "x2='1' y1='0' y2='1'><stop offset='0' stop-color='#19E3D0'/><stop offset='.55' stop-color='#8A8CFF'/>"
           f"<stop offset='1' stop-color='#C77DFF'/></linearGradient></defs><g fill='url(#g)'>{bars}</g></svg>")
    return "url(\"data:image/svg+xml," + quote(svg) + "\")"


# ---------------------------------------------------------------------------------- commun aux deux styles
BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap');
.stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded){
  font-family:'Outfit', system-ui, sans-serif;}
header[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], footer,
[data-testid="stHeaderActionElements"]{display:none !important;}
[data-testid="stMain"]{overflow-x:hidden;}
.block-container{padding-top:1.2rem; padding-bottom:3rem; padding-left:2rem !important; padding-right:2rem !important;}
@media (max-width:640px){.block-container{padding-left:1rem !important; padding-right:1rem !important;}}
.yg-ico{width:1.1em; height:1.1em; flex:none; vertical-align:-.18em;}

/* barre du haut : logo, menu au centre, lien à droite */
.st-key-yg_topbar{flex-wrap:nowrap !important; align-items:center; margin-bottom:1rem;}
.st-key-yg_brand, .st-key-yg_right{flex:1 1 0 !important; min-width:0;}
/* Streamlit enveloppe chaque élément de la ligne : la mise en page se règle sur ces enveloppes */
.st-key-yg_topbar > div:has(> .st-key-yg_brand), .st-key-yg_topbar > div:has(> .st-key-yg_right){flex:1 1 0 !important; min-width:0;}
.st-key-yg_topbar > div:has(> .st-key-yg_menu){flex:0 0 auto !important;}
.st-key-yg_right{justify-content:flex-end; align-items:center; flex-wrap:nowrap !important;}
.stApp .yg-logo{display:flex; align-items:center; gap:.65rem; margin:0; font-weight:700; font-size:1.65rem;
  letter-spacing:-.03em; color:var(--logo-text); line-height:1;}
.yg-logo i{width:2.4rem; height:2.4rem; border-radius:.75rem; display:grid; place-items:center;
  background:var(--logo-bg); color:var(--logo-icon); flex:none;}
.yg-logo i svg{width:1.2rem; height:1.2rem;}
.st-key-yg_menu{flex:0 0 auto !important; width:auto !important; padding:.3rem; gap:.15rem !important;
  border-radius:999px; background:var(--menu-bg); border:1px solid var(--menu-line);}
.st-key-yg_menu [data-testid="stPageLink"] a{padding:.5rem 1.15rem; border-radius:999px; background:transparent;}
.st-key-yg_menu [data-testid="stPageLink"] a p{color:var(--menu-text); font-weight:500; font-size:1rem; white-space:nowrap;}
.st-key-yg_menu [data-testid="stPageLink"] a:hover{background:var(--menu-hover);}
.stApp a:focus-visible, .stApp button:focus-visible, .stApp [role="tab"]:focus-visible{
  outline:3px solid var(--focus) !important; outline-offset:2px;}

/* étiquettes de statut : toujours un libellé, jamais la couleur seule */
.yg-badge{display:inline-flex; align-items:center; gap:.4rem; padding:.2rem .65rem; border-radius:999px;
  font-size:.86rem; font-weight:600; white-space:nowrap; background:var(--b-info-bg); color:var(--b-info);}
.yg-badge::before{content:""; width:.45rem; height:.45rem; border-radius:50%; background:currentColor;}
.yg-badge.warn{background:var(--b-warn-bg); color:var(--b-warn);}
.yg-badge.progress{background:var(--b-prog-bg); color:var(--b-prog);}
.yg-badge.ok{background:var(--b-ok-bg); color:var(--b-ok);}
.yg-badge.stop{background:var(--b-stop-bg); color:var(--b-stop);}
.yg-badge.neutral{background:var(--b-neu-bg); color:var(--b-neu);}

/* carte en direct (tableau de bord) : deck.gl place l'infobulle par rapport à ce conteneur, que
   Streamlit met sous la carte (hauteur nulle) ; ramené en haut, l'infobulle apparaît sous le curseur */
.stDeckGlJsonChart .deck-widgets-root{position:absolute; top:0; left:0; width:100%;}
.yg-legend{display:flex; flex-wrap:wrap; gap:.4rem 1.1rem; margin:.6rem 0 .2rem; font-size:.88rem; color:var(--muted);}
.yg-legend span{display:inline-flex; align-items:center; gap:.4rem;}
.yg-legend i{width:.8rem; height:.8rem; border-radius:50%; display:inline-block;}
.yg-legend i.ring{background:transparent; border:3px solid #FFC629;}
.yg-live{display:inline-flex; align-items:center; gap:.45rem; font-size:.9rem; color:var(--muted);}
.yg-live::before{content:""; width:.55rem; height:.55rem; border-radius:50%; background:#16A34A;
  animation:yg-live 2s ease-in-out infinite;}
@keyframes yg-live{50%{opacity:.3}}
@media (prefers-reduced-motion: reduce){.yg-live::before{animation:none;}}
"""

# ---------------------------------------------------------------------------------- style sombre : citoyen
DARK_CSS = """
:root{
  --bg:#070B1A; --text:#EEF2FF; --muted:#C3CBEA; --glass:rgba(255,255,255,.055); --glass-line:rgba(255,255,255,.10);
  --brand:linear-gradient(90deg,#19E3D0,#8A8CFF 55%,#C77DFF); --line:rgba(255,255,255,.12); --focus:#19E3D0;
  --logo-text:#fff; --logo-bg:linear-gradient(135deg,#19E3D0,#8A8CFF 55%,#C77DFF); --logo-icon:#fff;
  --menu-bg:rgba(255,255,255,.05); --menu-line:rgba(255,255,255,.12); --menu-text:#D7DDF5; --menu-hover:rgba(255,255,255,.08);
  --menu-active:#070B1A;
  --b-info-bg:rgba(138,140,255,.18); --b-info:#CDD0FF; --b-warn-bg:rgba(255,201,77,.15); --b-warn:#FFDB8A;
  --b-prog-bg:rgba(56,189,248,.16); --b-prog:#A6E1FA; --b-ok-bg:rgba(25,227,208,.14); --b-ok:#8FF3EA;
  --b-stop-bg:rgba(255,99,99,.16); --b-stop:#FFB8B3; --b-neu-bg:rgba(255,255,255,.09); --b-neu:#C3CBEA;
}
.stApp{color-scheme:dark; color:var(--text);
  background:radial-gradient(900px 620px at 6% -4%, rgba(0,214,201,.20), transparent 62%),
             radial-gradient(1000px 760px at 102% 104%, rgba(178,92,255,.26), transparent 62%), #070B1A;
  background-attachment:fixed;}
[data-testid="stMain"]{background:transparent !important;}
/* zone de saisie fixée en bas pendant la conversation : fondu sur toute la largeur, aucun fond opaque */
[data-testid="stBottom"]{background:linear-gradient(rgba(7,11,26,0), rgba(7,11,26,.88) 40%) !important;}
[data-testid="stBottom"] div:not([data-testid="stChatInput"]){background-color:transparent !important;}
[data-testid="stBottomBlockContainer"]{max-width:800px;}
.stApp [data-testid="stTooltipHoverTarget"] svg, .stApp [data-testid="stTooltipIcon"] svg{color:var(--muted) !important; stroke:var(--muted);}
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stMarkdownContainer"] p, .stApp label,
.stApp [data-testid="stWidgetLabel"] p, .stApp h1, .stApp h2, .stApp h3{color:var(--text);}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p{color:var(--muted);}
.stApp [data-testid="stSpinner"], .stApp [data-testid="stSpinner"] p{color:var(--muted);}

/* lien « Espace services » à droite */
.st-key-yg_right [data-testid="stPageLink"] a{border:1px solid rgba(255,255,255,.22); border-radius:999px;
  padding:.5rem 1.1rem; background:transparent;}
.st-key-yg_right [data-testid="stPageLink"] a:hover{background:rgba(255,255,255,.07);}
.st-key-yg_right [data-testid="stPageLink"] a p, .st-key-yg_right [data-testid="stPageLink"] span{color:var(--text);}
.stApp [data-testid="stPageLink"] a p{color:var(--text);}

/* accueil */
.yg-hero{text-align:center; margin:.6rem auto 0;}
.yg-pill{display:inline-flex; align-items:center; gap:.55rem; padding:.42rem 1.05rem; border-radius:999px;
  background:rgba(25,227,208,.10); border:1px solid rgba(25,227,208,.30); color:#8FF3EA; font-weight:500; font-size:1rem;}
.yg-pill::before{content:""; width:.55rem; height:.55rem; border-radius:50%; background:#19E3D0;
  box-shadow:0 0 0 4px rgba(25,227,208,.18);}
.stApp .yg-hero h1{font-size:clamp(2.2rem, 6.4vw, 4.7rem); line-height:1.04; font-weight:700; letter-spacing:-.04em;
  margin:1.4rem 0 1.1rem; padding:0; color:#fff;}
.yg-hero h1 .grad{display:block; background:var(--brand); -webkit-background-clip:text; background-clip:text;
  color:transparent;}
.stApp .yg-hero p{color:var(--muted); font-size:clamp(1.05rem, 2vw, 1.3rem); line-height:1.5; max-width:40rem;
  margin:0 auto;}

/* le micro : bouton de st.audio_input habillé */
[data-testid="stAudioInput"]{display:flex; flex-direction:column; align-items:center; position:relative; margin:1.4rem 0 .4rem;}
[data-testid="stAudioInput"]::before{content:""; position:absolute; left:50%; top:46%; width:min(620px, 100vw);
  height:520px; transform:translate(-50%,-50%); pointer-events:none;
  background:radial-gradient(closest-side, rgba(88,101,255,.42), rgba(88,101,255,.10) 55%, transparent);}
[data-testid="stAudioInput"] > *{position:relative;}
/* la lueur du micro dépasse de son bouton : aucun conteneur ne doit la découper */
[data-testid="stAudioInput"], [data-testid="stAudioInput"] > div:last-child, [data-testid="stAudioInput"] > div:last-child *:has([data-testid="stAudioInputActionButton"]){overflow:visible !important;}
[data-testid="stAudioInput"] > label{order:2; justify-content:center; width:100%; margin:1rem 0 0;}
[data-testid="stAudioInput"] > label p{font-weight:600; font-size:1.15rem; color:var(--text); text-align:center;}
[data-testid="stAudioInput"] > div:last-child{order:1; display:flex; flex-direction:column; align-items:center; gap:.3rem;
  background:transparent !important; border:none !important; box-shadow:none !important; height:auto !important;
  width:100%; padding:0 !important;}
[data-testid="stAudioInput"] [data-testid="stElementToolbar"]{display:none !important;}
[data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"]){position:relative; display:flex;
  align-items:center; justify-content:center; width:236px; height:236px; margin:0 !important;}
[data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"])::before,
[data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"])::after{content:""; position:absolute;
  top:50%; width:200px; height:120px; transform:translateY(-50%); background:WAVES_LEFT center/contain no-repeat;
  pointer-events:none;}
[data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"])::before{right:calc(100% + 10px);}
[data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"])::after{left:calc(100% + 10px);
  background-image:WAVES_RIGHT;}
[data-testid="stAudioInputActionButton"]{width:196px !important; height:196px !important; min-width:196px !important;
  min-height:196px; max-width:none !important; flex:0 0 196px !important; border-radius:50% !important; padding:0 !important;
  cursor:pointer; color:#fff !important; border:6px solid transparent !important;
  background:radial-gradient(circle at 50% 32%, #1E2766, #0B1030 72%) padding-box,
             linear-gradient(140deg,#19E3D0,#8A8CFF 55%,#C77DFF) border-box !important;
  box-shadow:0 0 0 16px rgba(88,101,255,.10), 0 0 70px rgba(88,101,255,.55); transition:transform .15s ease;}
[data-testid="stAudioInputActionButton"] svg{width:76px !important; height:76px !important;}
[data-testid="stAudioInputActionButton"]:hover{transform:scale(1.03);}
[data-testid="stAudioInputActionButton"]:focus-visible{outline:4px solid #19E3D0 !important; outline-offset:8px;}
[data-testid="stAudioInputActionButton"][aria-label="Stop recording"]{
  background:radial-gradient(circle at 50% 32%, #3A1430, #1A0B1E 72%) padding-box,
             linear-gradient(140deg,#FF6B6B,#FF2D55) border-box !important;
  animation:yg-rec 1.3s ease-in-out infinite;}
@keyframes yg-rec{0%,100%{box-shadow:0 0 0 10px rgba(255,45,85,.22), 0 0 50px rgba(255,45,85,.45)}
  50%{box-shadow:0 0 0 26px rgba(255,45,85,.05), 0 0 80px rgba(255,45,85,.25)}}
@media (prefers-reduced-motion: reduce){[data-testid="stAudioInputActionButton"]{animation:none !important; transition:none;}}
[data-testid="stAudioInput"] > div:last-child > div:has([data-testid="stAudioInputWaveSurfer"]){width:min(300px, 80%); min-height:26px;}
[data-testid="stAudioInputWaveformTimeCode"]{color:var(--muted); background:transparent !important; margin:0 !important;}
[data-testid="stAudioInput"]:not(:has([aria-label="Stop recording"])) [data-testid="stAudioInputWaveformTimeCode"],
[data-testid="stAudioInput"]:not(:has([aria-label="Stop recording"])) > div:last-child > div:has([data-testid="stAudioInputWaveSurfer"]){display:none;}
/* Vocal enregistré, analyse en cours : Streamlit ajoute un bouton de lecture à côté du micro.
   On le masque, et le micro reste seul, inactif, avec une pulsation, jusqu'à la réponse. */
[data-testid="stAudioInput"] span:has(> [aria-label="Play"]),
[data-testid="stAudioInput"] span:has(> [aria-label="Pause"]){display:none !important;}
[data-testid="stAudioInput"]:has([aria-label="Play"], [aria-label="Pause"]) [aria-label="Record"]{
  pointer-events:none; animation:yg-attente 1.2s ease-in-out infinite;}
@keyframes yg-attente{0%,100%{opacity:1} 50%{opacity:.45}}

/* barre de saisie en verre */
.st-key-yg_compose{max-width:760px; margin:0 auto;}
[data-testid="stChatInput"]{background:var(--glass) !important; border:1px solid var(--glass-line) !important;
  border-radius:22px !important; backdrop-filter:blur(14px); padding:.35rem .4rem .35rem .9rem;}
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] [data-baseweb], [data-testid="stChatInputTextArea"]{
  background:transparent !important; border-color:transparent !important;}
[data-testid="stChatInputTextArea"]{color:var(--text) !important; caret-color:#19E3D0; font-size:1.05rem !important;}
[data-testid="stChatInputTextArea"]::placeholder{color:var(--muted) !important; opacity:1;}
[data-testid="stChatInput"]:focus-within{border-color:#19E3D0 !important; box-shadow:0 0 0 3px rgba(25,227,208,.28);}
[data-testid="stChatInputSubmitButton"]{background:linear-gradient(135deg,#19E3D0,#4F8BFF) !important; color:#06122B !important;
  border-radius:14px !important; width:2.75rem !important; height:2.75rem !important; border:none !important;}
[data-testid="stChatInputSubmitButton"] svg{color:#06122B !important; fill:#06122B !important;}
[data-testid="stChatInputSubmitButton"]:disabled{opacity:.55;}
.st-key-yg_prefs{justify-content:center; margin-top:.4rem;}
.st-key-yg_prefs button{background:var(--glass) !important; border:1px solid var(--glass-line) !important; color:var(--text) !important;}
.st-key-yg_prefs button p{color:var(--text) !important;}
.st-key-yg_prefs button[aria-checked="true"]{background:rgba(255,255,255,.92) !important; border-color:#fff !important;}
.st-key-yg_prefs button[aria-checked="true"] p{color:#070B1A !important; font-weight:600;}
.st-key-yg_prefs button:first-child{border-radius:12px 0 0 12px;} .st-key-yg_prefs button:last-child{border-radius:0 12px 12px 0;}
.stApp [data-testid="stAlert"]{max-width:760px; margin:0 auto;}

/* cartes du bas */
.yg-cards{display:grid; grid-template-columns:1.35fr 1fr 1fr 1fr; gap:1rem; margin:2.6rem 0 .4rem;}
.yg-card{background:var(--glass); border:1px solid var(--glass-line); border-radius:20px; padding:1.15rem 1.25rem;
  display:flex; gap:.95rem; align-items:flex-start; color:var(--text);}
.yg-card .ic{width:2.6rem; height:2.6rem; border-radius:.8rem; background:rgba(255,255,255,.07); display:grid;
  place-items:center; flex:none; color:#D9DEFF;}
.yg-card .ic svg{width:1.25rem; height:1.25rem;}
.yg-card b{display:block; font-size:1.15rem; font-weight:600; margin-bottom:.2rem;}
.yg-card span{color:var(--muted); line-height:1.45;}
.yg-card.example{flex-direction:column; gap:.55rem;}
.yg-card.example small{color:var(--muted); font-size:.9rem;}
.yg-card.example q{font-size:1.12rem; font-weight:500; line-height:1.4; quotes:"« " " »";}
.yg-tags{display:flex; flex-wrap:wrap; align-items:center; gap:.35rem .8rem; color:#8FF3EA; font-weight:500;}
.yg-tags span{display:inline-flex; align-items:center; gap:.35rem; color:#8FF3EA;}
.yg-tags em{font-style:normal; background:rgba(25,227,208,.14); padding:.2rem .6rem; border-radius:.5rem; color:#8FF3EA;}
.yg-note{color:var(--muted); font-size:.92rem; text-align:center; margin:1.6rem 0 0;}

/* étapes, conversation, récépissé */
.yg-steps{display:flex; gap:.5rem; list-style:none; padding:0; margin:0 auto 1.2rem; max-width:760px;}
.yg-steps li{flex:1; font-size:.92rem; font-weight:500; color:var(--muted); padding-top:.55rem;
  border-top:3px solid rgba(255,255,255,.12); margin:0;}
.yg-steps li.done{border-image:var(--brand) 1; color:var(--text);}
.yg-steps li.now{border-top-color:#19E3D0; color:#fff; font-weight:600;}
.yg-chat{display:flex; flex-direction:column; gap:.65rem; margin:0 auto 1rem; max-width:760px;}
.yg-msg{max-width:86%; padding:.8rem 1.05rem; border-radius:20px; line-height:1.5; font-size:1.05rem; overflow-wrap:anywhere;}
.yg-msg.user{align-self:flex-end; background:linear-gradient(135deg,#4C5BFF,#8A5CFF); color:#fff; border-bottom-right-radius:6px;}
.yg-msg.bot{align-self:flex-start; background:var(--glass); border:1px solid var(--glass-line); color:var(--text);
  border-bottom-left-radius:6px;}
.yg-msg small{display:block; font-size:.78rem; font-weight:600; opacity:.8; margin-bottom:.15rem;}
.yg-ticket{background:var(--glass); border:1px solid var(--glass-line); border-radius:20px; margin:.4rem auto 1rem;
  max-width:760px; overflow:hidden; color:var(--text); backdrop-filter:blur(14px);}
.yg-ticket header{padding:1rem 1.3rem; font-weight:600; font-size:1.15rem; border-bottom:1px solid var(--glass-line);}
.yg-ticket dl{display:grid; grid-template-columns:minmax(6.5rem, max-content) 1fr; gap:.6rem 1rem; margin:0; padding:1.1rem 1.3rem;}
.yg-ticket dt{color:var(--muted);} .yg-ticket dd{margin:0; font-weight:600;}
.yg-ticket .dest{margin:0 1rem 1rem; padding:.95rem 1.1rem; display:flex; gap:.75rem; align-items:flex-start;
  border-radius:16px; border:1.5px solid transparent;
  background:linear-gradient(#10152E,#10152E) padding-box, var(--brand) border-box;}
.yg-ticket .dest span{color:var(--muted); font-size:.92rem; display:block;}
.yg-ticket .dest b{font-size:1.15rem; color:#fff;}
.yg-dot{flex:none; width:.8rem; height:.8rem; border-radius:50%; margin-top:.4rem; background:#19E3D0;}
.yg-dot.warn{background:#FFC94D;} .yg-dot.stop{background:#FF6B6B;}
.yg-ref{font-weight:800; font-size:clamp(1.6rem, 7vw, 2.4rem); letter-spacing:.03em; padding:1.2rem 1rem .4rem;
  text-align:center; user-select:all; background:var(--brand); -webkit-background-clip:text; background-clip:text; color:transparent;}
.yg-ref-help{text-align:center; color:var(--muted); font-size:.95rem; padding:0 1.2rem 1rem; margin:0;}
.yg-track{list-style:none; margin:0; padding:1.1rem 1.3rem; border-top:1px solid var(--glass-line);}
.yg-track li{position:relative; padding:0 0 1.15rem 2rem; color:var(--muted); margin:0;}
.yg-track li:last-child{padding-bottom:0;}
.yg-track li::before{content:""; position:absolute; left:0; top:.2rem; width:1rem; height:1rem; border-radius:50%;
  background:#0E1330; border:2px solid rgba(255,255,255,.22); box-sizing:border-box;}
.yg-track li::after{content:""; position:absolute; left:.44rem; top:1.25rem; bottom:-.15rem; width:2px; background:rgba(255,255,255,.14);}
.yg-track li:last-child::after{display:none;}
.yg-track li.done, .yg-track li.now{color:var(--text);}
.yg-track li.done::before{background:var(--brand); border:none;}
.yg-track li.done::after{background:linear-gradient(#19E3D0,#8A8CFF);}
.yg-track li.now{font-weight:600;}
.yg-track li.now::before{border:3px solid #19E3D0; box-shadow:0 0 0 4px rgba(25,227,208,.16);}
.yg-track li span{font-weight:400; color:var(--muted); font-size:.95rem;}

/* composants natifs sur fond sombre */
.stApp button[kind="primary"]{background:linear-gradient(90deg,#19E3D0,#4F8BFF) !important; border:none !important;
  color:#06122B !important; border-radius:14px; font-weight:700; min-height:3.1rem;}
.stApp button[kind="primary"] p{color:#06122B !important; font-weight:700; font-size:1.05rem;}
.stApp button[kind="secondary"]{background:transparent !important; border:1px solid rgba(255,255,255,.24) !important;
  color:var(--text) !important; border-radius:14px; min-height:3.1rem;}
.stApp button[kind="secondary"] p{color:var(--text) !important;}
.stApp button[kind="secondary"]:hover{border-color:#8A8CFF !important; background:rgba(255,255,255,.05) !important;}
.stApp [data-testid="stTextInputRootElement"]{background:var(--glass) !important; border:1px solid var(--glass-line) !important;
  border-radius:16px !important;}
.stApp [data-testid="stTextInputRootElement"] *{background:transparent !important;}
.stApp [data-testid="stTextInputRootElement"] input{color:var(--text) !important; font-size:1.1rem; letter-spacing:.02em;
  caret-color:#19E3D0;}
.stApp [data-testid="stTextInputRootElement"] input::placeholder{color:#8F99C4 !important; opacity:1;}
.stApp [data-testid="stTextInputRootElement"]:focus-within{border-color:#19E3D0 !important;}
.stApp [data-testid="stAlertContainer"]{background:rgba(255,255,255,.06) !important; border:1px solid var(--glass-line);
  border-left:4px solid #8A8CFF; border-radius:14px; color:var(--text) !important;}
.stApp [data-testid="stAlertContainer"] p{color:var(--text) !important;}
.stApp [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]){border-left-color:#FFC94D;}
.stApp [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]){border-left-color:#FF6B6B;}
.stApp [data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]){border-left-color:#19E3D0;}
.stApp [data-testid="stCheckbox"] label p, .stApp [data-testid="stCheckbox"] span{color:var(--text);}

.stApp .yg-page-title{font-size:clamp(2rem, 5vw, 3rem); font-weight:700; letter-spacing:-.03em; margin:.6rem 0 .3rem; padding:0; color:#fff;}
.yg-page-sub{color:var(--muted); font-size:1.1rem; margin:0 0 1.2rem;}

@media (max-width:900px){.yg-cards{grid-template-columns:1fr 1fr;}}
@media (max-width:640px){
  .yg-cards{grid-template-columns:1fr;}
  .yg-msg{max-width:94%;}
  .st-key-yg_topbar{flex-wrap:wrap !important; row-gap:.7rem;}
  .st-key-yg_topbar > div:has(> .st-key-yg_brand){order:1; flex:1 1 0 !important;}
  .st-key-yg_topbar > div:has(> .st-key-yg_right){order:2; flex:0 0 auto !important; width:auto !important;}
  .st-key-yg_right{width:auto !important; flex:0 0 auto !important;}
  .st-key-yg_topbar > div:has(> .st-key-yg_menu){order:3; flex:1 1 100% !important; display:flex; justify-content:center;}
  .st-key-yg_menu [data-testid="stPageLink"] a{padding:.42rem .75rem;}
  .st-key-yg_right [data-testid="stPageLink"] a{padding:.4rem .8rem;}
}
@media (max-width:560px){
  [data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"])::before,
  [data-testid="stAudioInput"] span:has(> [data-testid="stAudioInputActionButton"])::after{display:none;}
}
""".replace("WAVES_LEFT", _waves(False)).replace("WAVES_RIGHT", _waves(True))

# ---------------------------------------------------------------------------------- style clair : services
LIGHT_CSS = """
:root{
  --navy:#0B1F4B; --blue:#1E5BD8; --muted:#5B6B8C; --line:#DFE7F5; --paper:#F4F7FC; --focus:#1E5BD8;
  --logo-text:#fff; --logo-bg:#fff; --logo-icon:#1E5BD8;
  --menu-bg:rgba(255,255,255,.10); --menu-line:rgba(255,255,255,.20); --menu-text:rgba(255,255,255,.88);
  --menu-hover:rgba(255,255,255,.12); --menu-active:#0B1F4B;
  --b-info-bg:#E3ECFF; --b-info:#123A8C; --b-warn-bg:#FFF1CC; --b-warn:#7A4B00; --b-prog-bg:#DDF3FB; --b-prog:#075E7D;
  --b-ok-bg:#DDF5E7; --b-ok:#0B6B3D; --b-stop-bg:#FBE4E2; --b-stop:#B3261E; --b-neu-bg:#ECEFF6; --b-neu:#4A5878;
}
.stApp{background:#F4F7FC; color:var(--navy);}
.block-container{padding-top:0 !important;}
.stApp h1, .stApp h2, .stApp h3, .stApp h4{color:var(--navy);}

/* bandeau bleu marine sur toute la largeur ; les compteurs chevauchent son bas */
.st-key-yg_band{position:relative; isolation:isolate; padding:1.2rem 0 0;}
.st-key-yg_band::before{content:""; position:absolute; z-index:-1; top:-4rem; bottom:var(--band-overlap, 0px); left:50%;
  width:100vw; transform:translateX(-50%); background:linear-gradient(110deg,#0B1F4B 0%,#123A8C 48%,#1E5BD8 100%);}
.st-key-yg_band:has(.yg-kpis){--band-overlap:58px;}
.st-key-yg_band:not(:has(.yg-kpis)){padding-bottom:1.6rem;}
.st-key-yg_head{align-items:flex-end; margin:.4rem 0 1.3rem;}
.stApp .yg-band-title{font-size:clamp(2rem, 4vw, 2.7rem); font-weight:700; letter-spacing:-.03em; color:#fff; margin:0; padding:0;}
.yg-band-sub{color:rgba(255,255,255,.80); font-size:1.08rem; margin:.2rem 0 0;}
.yg-flag{display:inline-flex; align-items:center; gap:.55rem; background:#FFF1CC; color:#7A4B00; font-weight:600;
  padding:.65rem 1.1rem; border-radius:14px; white-space:nowrap;}
.yg-who{display:flex; align-items:center; gap:.7rem; color:rgba(255,255,255,.88); font-size:1rem; white-space:nowrap;}
.yg-who i{flex:none; min-width:2.4rem; width:2.4rem; height:2.4rem; border-radius:50%; background:#fff; color:var(--navy); display:grid;
  place-items:center; font-style:normal; font-weight:700;}
.st-key-yg_right button{background:transparent !important; border:1px solid rgba(255,255,255,.35) !important;
  min-height:2.4rem !important; border-radius:999px !important; padding:.2rem .9rem !important;}
.st-key-yg_right button p{color:#fff !important; font-size:.92rem !important;}
.st-key-yg_right button:hover{background:rgba(255,255,255,.10) !important;}

/* compteurs */
.yg-kpis{display:grid; grid-template-columns:repeat(4, 1fr); gap:1rem; margin:0 0 .3rem;}
.yg-kpi{background:#fff; border:1px solid var(--line); border-radius:20px; box-shadow:0 12px 30px rgba(11,31,75,.10);
  padding:1.15rem 1.3rem; display:flex; align-items:center; gap:1rem;}
.yg-kpi .ic{width:3.1rem; height:3.1rem; border-radius:14px; display:grid; place-items:center; flex:none;
  background:#E3ECFF; color:#1E5BD8;}
.yg-kpi .ic svg{width:1.45rem; height:1.45rem;}
.yg-kpi.warn .ic{background:#FFF1CC; color:#9A6100;} .yg-kpi.prog .ic{background:#DDF3FB; color:#075E7D;}
.yg-kpi.ok .ic{background:#DDF5E7; color:#0B6B3D;}
.yg-kpi b{display:block; font-size:2.25rem; font-weight:700; line-height:1; color:var(--navy);}
.yg-kpi span{color:var(--muted); font-size:1rem;}

/* cartes blanches : liste et détail */
.st-key-yg_listcard, .st-key-yg_detail, .st-key-yg_login{background:#fff; border:1px solid var(--line); border-radius:20px;
  box-shadow:0 12px 30px rgba(11,31,75,.06); padding:1.2rem 1.25rem;}
.yg-tablewrap{overflow-x:auto; margin:0 -.2rem;}
.yg-table{width:100%; border-collapse:collapse; font-size:.91rem; min-width:800px; margin:0;}
.yg-table th, .yg-table td{border:none !important; border-bottom:1px solid #EDF1F8 !important; padding:.75rem .45rem;
  text-align:left; vertical-align:middle; color:var(--navy);}
.yg-table th{font-weight:500; color:var(--muted); background:transparent; white-space:nowrap;}
.yg-table td.ref{font-weight:700; white-space:nowrap; color:#123A8C;}
.yg-table td.when{white-space:nowrap; color:var(--muted);}
.yg-table td.cat{white-space:nowrap;} .yg-table td.place{min-width:8rem;} .yg-table td.org{min-width:7rem;} .yg-table td.cat svg{color:#123A8C; margin-right:.35rem;}
.yg-table td.na, .yg-table .na{color:var(--muted);}
.yg-table em.urg{font-style:normal; font-weight:600; color:#B3261E;}
.yg-table tr.sel td{background:#EAF1FF;} .yg-table tr.sel td:first-child{box-shadow:inset 3px 0 0 #1E5BD8;}
.yg-conf{display:flex; align-items:center; gap:.55rem; white-space:nowrap;}
.yg-conf i{display:block; width:58px; height:6px; border-radius:3px; background:#E3E9F5; overflow:hidden;}
.yg-conf i u{display:block; height:100%; background:#1E5BD8; border-radius:3px;}
.yg-conf.low i u{background:#E0A800;}

/* détail */
.yg-dhead{display:flex; align-items:center; justify-content:space-between; gap:.6rem; margin:.2rem 0 .9rem;}
.yg-dhead b{font-size:1.2rem; font-weight:700; color:var(--navy); white-space:nowrap;}
.yg-quote{background:#F4F7FC; border-radius:16px; padding:.95rem 1.1rem; margin-bottom:.7rem;}
.yg-quote small{display:flex; align-items:center; gap:.4rem; color:var(--muted); font-size:.88rem;}
.yg-quote p{color:var(--navy); font-size:1.05rem; line-height:1.45; margin:.4rem 0 .35rem; white-space:pre-line;}
.yg-quote span{color:var(--muted);}
.yg-quote em{display:block; font-style:normal; color:var(--muted); font-size:.82rem; margin-top:.45rem;}
.yg-mini{display:grid; grid-template-columns:1fr 1fr; gap:.7rem; margin-bottom:.7rem;}
.yg-mini div{background:#F4F7FC; border-radius:14px; padding:.7rem .95rem;}
.yg-mini span{display:block; color:var(--muted); font-size:.88rem;} .yg-mini b{color:var(--navy); font-weight:600;}
.yg-org{background:var(--navy); color:#fff; border-radius:18px; padding:1rem 1.15rem; margin-bottom:.8rem;}
.yg-org small{color:rgba(255,255,255,.78); font-size:.9rem;}
.yg-org b{display:block; font-size:1.45rem; font-weight:700; margin:.1rem 0 .7rem; color:#fff;}
.yg-org em{font-style:normal; font-weight:400; font-size:.95rem; color:rgba(255,255,255,.78);}
.yg-bar{display:grid; grid-template-columns:5.8rem 1fr 4.6rem; align-items:center; gap:.6rem; margin:.3rem 0; font-size:.95rem;}
.yg-bar i{height:6px; border-radius:3px; background:rgba(255,255,255,.18); overflow:hidden; display:block;}
.yg-bar i u{display:block; height:100%; background:#6E97FF; border-radius:3px;}
.yg-bar.low i u{background:#FFC94D;} .yg-bar span:last-child{text-align:right;}
.yg-events{list-style:none; padding:0; margin:0 0 .6rem;}
.yg-events li{display:flex; gap:.55rem; align-items:flex-start; color:var(--muted); margin:.35rem 0; line-height:1.4;}
.yg-events li svg{color:#1E5BD8; margin-top:.15rem;} .yg-events b{color:var(--navy); font-weight:600;}
.yg-note-light{color:var(--muted); font-size:.92rem; margin:.4rem 0 .8rem;}
.yg-alert{background:#FBE4E2; border:1px solid #F3B9B4; border-left:6px solid #B3261E; border-radius:14px;
  padding:.75rem 1rem; color:var(--navy); line-height:1.45;}
.yg-alert b{color:#B3261E; margin-right:.35rem;}
.yg-alert span{display:block; color:#5B4A55; font-size:.92rem;}
.yg-log{border-left:3px solid #DCE6FA; padding:.1rem 0 .1rem .9rem; margin:0 0 .9rem; color:var(--navy);}
.yg-log b{display:block;} .yg-log span{color:var(--muted); font-size:.92rem;}

/* composants natifs */
.stApp [data-testid="stForm"]{background:#fff; border:1px solid var(--line); border-radius:16px; padding:1rem 1.05rem;}
.st-key-yg_login [data-testid="stForm"]{border:none; padding:0;}
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"]{background:#1E5BD8 !important; border:none !important;
  border-radius:12px; min-height:2.9rem; font-weight:600;}
.stApp button[kind="primary"] p, .stApp button[kind="primaryFormSubmit"] p{color:#fff !important; font-weight:600;}
.stApp button[kind="primary"]:hover, .stApp button[kind="primaryFormSubmit"]:hover{background:#174BB5 !important;}
.stApp button[kind="secondary"], .stApp button[kind="secondaryFormSubmit"]{background:#fff; border:1px solid #C9D6EE;
  border-radius:12px; min-height:2.9rem; color:var(--navy);}
.stApp button[kind="secondary"] p, .stApp button[kind="secondaryFormSubmit"] p{color:var(--navy); font-weight:600;}
.stApp [data-testid="stWidgetLabel"] p{color:var(--muted); font-weight:500;}

@media (max-width:900px){.yg-kpis{grid-template-columns:repeat(2, 1fr);} .st-key-yg_band:has(.yg-kpis){--band-overlap:150px;}}
@media (max-width:640px){
  .st-key-yg_topbar{flex-wrap:wrap !important; row-gap:.7rem;}
  .st-key-yg_topbar > div:has(> .st-key-yg_brand){order:1; flex:1 1 0 !important;}
  .st-key-yg_topbar > div:has(> .st-key-yg_right){order:2; flex:0 0 auto !important; width:auto !important;}
  .st-key-yg_right{width:auto !important; flex:0 0 auto !important;}
  .st-key-yg_topbar > div:has(> .st-key-yg_menu){order:3; flex:1 1 100% !important; display:flex; justify-content:center;}
  .st-key-yg_menu{flex-wrap:nowrap !important;}
  .st-key-yg_menu [data-testid="stPageLink"] a{padding:.4rem .55rem;}
  .st-key-yg_menu [data-testid="stPageLink"] a p{font-size:.86rem;}
  .yg-who span{display:none;}
  .st-key-yg_head{flex-direction:column; align-items:flex-start !important;}
  .yg-flag{white-space:normal;}
  .yg-kpi{padding:.9rem 1rem;} .yg-kpi b{font-size:1.8rem;}
}
"""


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def logo_html() -> str:
    return f"<p class='yg-logo'><i>{icon('mic')}</i>{esc(settings.APP_NAME)}</p>"


def setup(title: str, theme: str = "dark", width: str = "760px", active: str = PAGE_HOME):
    """Configure la page, injecte le style et dessine la barre du haut.

    Renvoie (bandeau, droite) : le bandeau (style clair) reçoit la suite de l'en-tête, la zone
    de droite de la barre reçoit le nom de l'administrateur. En style sombre, la droite
    contient le lien vers l'espace services.
    """
    st.set_page_config(page_title=f"{title} | {settings.APP_NAME}", page_icon="📣", layout="wide",
                       initial_sidebar_state="collapsed")
    # Streamlit ne marque pas le lien de la page courante de façon stable : on le repère par son adresse.
    href = {PAGE_HOME: "", PAGE_TRACK: "Suivre_mon_signalement", PAGE_ADMIN: "Tableau_de_bord"}[active]
    current = f'.st-key-yg_menu a[href="{href}"]'
    css = (BASE_CSS + (DARK_CSS if theme == "dark" else LIGHT_CSS) + f".block-container{{max-width:{width};}}"
           + f"{current}{{background:#fff !important;}} {current} p{{color:var(--menu-active) !important; font-weight:600;}}")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    band = st.container(key="yg_band") if theme == "light" else st.container()
    with band:
        with st.container(horizontal=True, vertical_alignment="center", key="yg_topbar"):
            with st.container(key="yg_brand"):
                st.markdown(logo_html(), unsafe_allow_html=True)
            menu = [(PAGE_HOME, "Signaler"), (PAGE_TRACK, "Suivre un signalement")]
            if theme == "light":
                menu.append((PAGE_ADMIN, "Espace services"))
            with st.container(horizontal=True, vertical_alignment="center", key="yg_menu", width="content"):
                for page, label in menu:
                    try:
                        st.page_link(page, label=label)
                    except Exception:  # noqa: BLE001  (page lancée seule, hors de l'application : pas de menu)
                        break
            right = st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="right",
                                 key="yg_right")
            if theme == "dark":
                with right:
                    try:
                        st.page_link(PAGE_ADMIN, label="Espace services", icon=":material/apartment:")
                    except Exception:  # noqa: BLE001
                        pass
    return band, right


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
