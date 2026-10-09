"""Configuration centrale. Tout réglage modifiable passe par le fichier .env."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "oui", "yes")


APP_NAME = os.getenv("APP_NAME", "Yëgle")
REF_PREFIX = os.getenv("REF_PREFIX", "YGL")

# Données
DATA_DIR = BASE_DIR / "data"
ORGANISMES_FILE = DATA_DIR / "organismes.yaml"
CATEGORIES_FILE = DATA_DIR / "categories.yaml"
ZONES_FILE = DATA_DIR / "zones.yaml"
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "signalements.sqlite"))

# LLM (Gemini) : modèle principal + modèle de secours
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "").strip().upper()
GEMINI_TIMEOUT_S = int(os.getenv("GEMINI_TIMEOUT_S", "30"))
TIMEOUT_UNDERSTAND_S = 25
TIMEOUT_TTS_S = 20

# OpenAI : secours facultatif si Gemini est saturé
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

# Voix
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore")

# Mode de compréhension : "gemini" (voix + texte) ou "offline" (mots-clés, texte seulement).
# Sans clé Gemini, l'application démarre en mode offline pour rester testable.
LLM_MODE = os.getenv("LLM_MODE", "gemini" if GEMINI_API_KEY else "offline").strip().lower()

# Moteur d'orientation
ROUTING_MIN_CONFIDENCE = float(os.getenv("ROUTING_MIN_CONFIDENCE", "0.75"))
ROUTING_AMBIGUITY_MARGIN = float(os.getenv("ROUTING_AMBIGUITY_MARGIN", "0.10"))
# Une fiche organisme sans date de vérification ne reçoit rien automatiquement.
ROUTING_REQUIRE_VERIFIED = _bool("ROUTING_REQUIRE_VERIFIED", True)
MIN_CONFIDENCE_PROBLEM = float(os.getenv("MIN_CONFIDENCE_PROBLEM", "0.5"))

# Accès à l'administration (tableau de bord et API). Vide = accès refusé.
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

# Signature des brouillons renvoyés par l'API : le client ne peut pas les modifier entre
# deux messages. Vide = secret tiré au démarrage (les brouillons en cours expirent au
# redémarrage ; à fixer si l'API tourne sur plusieurs processus).
DRAFT_SECRET = os.getenv("DRAFT_SECRET", "") or secrets.token_hex(32)

# Limites de débit par adresse IP (0 = pas de limite). Chaque analyse peut appeler le modèle d'IA.
RATE_ANALYZE_PER_MINUTE = int(os.getenv("RATE_ANALYZE_PER_MINUTE", "20"))
RATE_REPORTS_PER_HOUR = int(os.getenv("RATE_REPORTS_PER_HOUR", "10"))
RATE_TRACK_PER_MINUTE = int(os.getenv("RATE_TRACK_PER_MINUTE", "60"))
# Alertes d'urgence : en plus du tableau de bord, envoi facultatif à un webhook https
# (Slack, Teams, passerelle SMS...). Vide = tableau de bord uniquement.
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "").strip()

# Tableau de bord : échecs de connexion tolérés par adresse IP sur 15 minutes.
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))

LANGS = {"fr": "français", "wo": "wolof", "en": "anglais"}
