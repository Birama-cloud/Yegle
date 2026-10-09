"""Transmission d'un signalement à l'organisme retenu.

La destination vient toujours de la base de connaissances, jamais du citoyen ni du modèle d'IA.
Chaque tentative est enregistrée (date, canal, destinataire, résultat, erreur), y compris
quand l'envoi échoue de façon imprévue : la fonction ne lève jamais d'exception d'envoi.
Le statut est mis à jour en une transaction, à partir du statut relu à ce moment-là.
"""
import httpx

from app.knowledge import Knowledge
from app.storage import Storage


def payload_for(report: dict) -> dict:
    """Données envoyées à l'organisme : pas de transcription brute, pas de donnée personnelle."""
    keys = ("reference", "created_at", "category", "subcategory", "description", "location_text",
            "territorial_area", "latitude", "longitude", "urgency", "language")
    return {k: report.get(k) for k in keys}


def _send(org, report: dict) -> tuple[str, bool, str | None]:
    if org.transmission_mode != "webhook":
        # file d'attente interne : l'organisme consulte ses signalements dans le tableau de bord
        return "internal_queue", True, None
    if not str(org.api_endpoint or "").startswith("https://"):
        return "webhook", False, "adresse de webhook absente ou non sécurisée"
    try:
        response = httpx.post(org.api_endpoint, json=payload_for(report), timeout=10)
    except Exception as e:  # noqa: BLE001  (réseau, adresse invalide... : tout échec est tracé)
        return "webhook", False, type(e).__name__
    return "webhook", response.is_success, None if response.is_success else f"HTTP {response.status_code}"


def transmit(storage: Storage, knowledge: Knowledge, report: dict, actor: str = "system") -> bool:
    """Tente la transmission et met à jour le statut. Renvoie True si elle est confirmée."""
    ref, org = report["reference"], knowledge.get_org(report.get("org_id") or "")
    if org is None or not org.active:
        channel, ok, error = "none", False, "organisme inconnu ou inactif"
    else:
        channel, ok, error = _send(org, report)       # hors transaction : l'envoi peut prendre du temps

    with storage.transaction():
        storage.add_transmission(ref, channel, report.get("org_name"), ok, error)
        current = storage.get(ref)["status"]
        if ok:
            if current in ("ASSIGNED", "IN_PROGRESS"):      # réorientation en cours de traitement
                storage.set_status(ref, "NEEDS_REVIEW", actor, "Réorientation")
                current = "NEEDS_REVIEW"
            if current in ("RECEIVED", "NEEDS_REVIEW"):
                storage.set_status(ref, "ROUTED", actor, f"Transmis par {channel} à {report.get('org_name')}")
        elif current in ("RECEIVED", "ROUTED", "ASSIGNED", "IN_PROGRESS"):
            note = "Destination non contrôlée" if channel == "none" else f"Transmission échouée ({error})"
            storage.set_status(ref, "NEEDS_REVIEW", actor, note)
    return ok
