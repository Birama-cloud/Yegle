"""Vérifie l'installation.  Lancer :  python -m scripts.check_setup"""
import sys

from app.knowledge import Knowledge
from app.storage import Storage
from app.zones import Gazetteer
from config import settings


def main() -> int:
    problems = 0

    def line(ok, text):
        nonlocal problems
        problems += 0 if ok else 1
        print(("  OK    " if ok else "  ERREUR ") + text)

    print(f"{settings.APP_NAME} : vérification de l'installation\n")
    knowledge = Knowledge.load()
    errors = knowledge.validate()
    line(not errors, f"Base de connaissances : {len(knowledge.organizations)} organismes, "
                     f"{len(knowledge.categories)} catégories")
    for e in errors:
        print(f"          - {e}")
    gazetteer = Gazetteer.load()
    line(bool(gazetteer.zones), f"Répertoire des zones : {len(gazetteer.zones)} zones")
    Storage()
    line(True, f"Base de données : {settings.DB_PATH}")

    print()
    unverified = [o.display_name for o in knowledge.organizations if o.active and not o.verified]
    if unverified:
        print("  À FAIRE  Fiches organismes sans date de vérification : " + ", ".join(unverified))
        print("           -> leurs signalements passent en vérification humaine (data/organismes.yaml)")
    approx = sum(not z.coords_verified for z in gazetteer.zones)
    if approx:
        print(f"  À FAIRE  {approx} zones ont des coordonnées non contrôlées (python -m scripts.verifier_zones)")
    print("  INFO     Mode : " + ("Gemini (voix et texte)" if settings.LLM_MODE == "gemini" and settings.GEMINI_API_KEY
                                  else "hors ligne (texte et mots-clés) : ajoutez GEMINI_API_KEY pour la voix"))
    if not settings.DASHBOARD_PASSWORD:
        print("  INFO     DASHBOARD_PASSWORD vide : le tableau de bord est verrouillé")
    if not settings.ADMIN_API_KEY:
        print("  INFO     ADMIN_API_KEY vide : l'API d'administration est désactivée")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
