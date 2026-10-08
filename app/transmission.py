"""Transmission d'un signalement à l'organisme retenu.

La destination vient toujours de la base de connaissances, jamais du citoyen ni du modèle d'IA.
Chaque tentative est enregistrée (date, canal, destinataire, résultat, erreur).
"""
import httpx

from app.knowledge import Knowledge
from app.storage import Storage


def payload_for(report: dict) -> dict:
    """Données envoyées à l'organisme : pas de transcription brute, pas de donnée personnelle."""
    keys = ("reference", "created_at", "category", "subcategory", "description", "location_text",
            "territorial_area", "latitude", "longitude", "urgency", "language")
    return {k: report.get(k) for k in keys}


def transmit(storage: Storage, knowledge: Knowledge, report: dict, actor: str = "system") -> bool:
    """Tente la transmission et met à jour le statut. Renvoie True si elle est confirmée."""
    ref, org = report["reference"], knowledge.get_org(report.get("org_id") or "")
    if org is None or not org.active:
        storage.add_transmission(ref, "none", report.get("org_name"), False, "organisme inconnu ou inactif")
        _to_review(storage, report, actor, "Destination non contrôlée")
        return False

    if org.transmission_mode == "webhook":
        channel, ok, error = "webhook", False, None
        if not str(org.api_endpoint or "").startswith("https://"):
            error = "adresse de webhook absente ou non sécurisée"
        else:
            try:
                response = httpx.post(org.api_endpoint, json=payload_for(report), timeout=10)
                ok = response.is_success
                error = None if ok else f"HTTP {response.status_code}"
            except httpx.HTTPError as e:
                error = type(e).__name__
    else:   # file d'attente interne : l'organisme consulte ses signalements dans le tableau de bord
        channel, ok, error = "internal_queue", True, None

    storage.add_transmission(ref, channel, report.get("org_name"), ok, error)
    if ok:
        current = storage.get(ref)["status"]
        if current in ("ASSIGNED", "IN_PROGRESS"):      # réorientation en cours de traitement
            storage.set_status(ref, "NEEDS_REVIEW", actor, "Réorientation")
            current = "NEEDS_REVIEW"
        if current in ("RECEIVED", "NEEDS_REVIEW"):
            storage.set_status(ref, "ROUTED", actor, f"Transmis par {channel} à {report.get('org_name')}")
    else:
        _to_review(storage, report, actor, f"Transmission échouée ({error})")
    return ok


def _to_review(storage: Storage, report: dict, actor: str, note: str) -> None:
    if storage.get(report["reference"])["status"] in ("RECEIVED", "ROUTED", "ASSIGNED", "IN_PROGRESS"):
        storage.set_status(report["reference"], "NEEDS_REVIEW", actor, note)
