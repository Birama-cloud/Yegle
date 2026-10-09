"""Alertes d'urgence : un signalement dangereux ne doit pas attendre dans une file.

Déclenchement :
- toujours pour l'urgence « critical » (danger immédiat pour des personnes), même sans
  organisme identifié : c'est justement là qu'une équipe doit intervenir vite ;
- en plus, selon les escalation_rules de l'organisme retenu dans data/organismes.yaml
  ({when_urgency: [...], action: notify_admin}).

Chaque alerte est enregistrée et reste en tête du tableau de bord jusqu'à sa prise en charge.
Si ALERT_WEBHOOK_URL est configurée (https), elle y est aussi envoyée ; le résultat est tracé.
"""
import httpx

from app.knowledge import Knowledge
from app.storage import Storage
from config import settings

ALWAYS = ("critical",)


def reason_for(knowledge: Knowledge, report: dict) -> str | None:
    """Pourquoi ce signalement déclenche une alerte, ou None."""
    urgency = report.get("urgency")
    if urgency in ALWAYS:
        return "Urgence critique : danger immédiat signalé"
    org = knowledge.get_org(report.get("org_id") or "")
    for rule in (org.escalation_rules if org else []):
        if rule.get("action") == "notify_admin" and urgency in (rule.get("when_urgency") or []):
            return f"Règle d'escalade de {report.get('org_name') or org.name} : urgence « {urgency} »"
    return None


def payload_for(alert: dict) -> dict:
    """Message envoyé au webhook : pas de transcription brute, pas de donnée personnelle."""
    place = alert.get("location_text") or alert.get("territorial_area") or "lieu non précisé"
    text = (f"Alerte {settings.APP_NAME} — {alert['reference']} : {alert.get('description')} ({place}). "
            f"Organisme : {alert.get('org_name') or 'à déterminer'}. {alert['reason']}.")
    keys = ("reference", "category", "urgency", "status", "location_text", "territorial_area", "org_name", "reason")
    return {"text": text, **{k: alert.get(k) for k in keys}}


def escalate(storage: Storage, knowledge: Knowledge, report: dict) -> dict | None:
    """Crée l'alerte si nécessaire et tente de la notifier. Ne lève jamais d'exception réseau."""
    reason = reason_for(knowledge, report)
    if not reason:
        return None
    alert = storage.add_alert(report["reference"], reason)
    if alert is None:                                    # déjà alerté
        return None
    url = settings.ALERT_WEBHOOK_URL
    if url:
        ok, error = False, None
        if not url.startswith("https://"):
            error = "ALERT_WEBHOOK_URL doit commencer par https://"
        else:
            try:
                response = httpx.post(url, json=payload_for(alert), timeout=5)
                ok, error = response.is_success, None if response.is_success else f"HTTP {response.status_code}"
            except httpx.HTTPError as e:
                error = type(e).__name__
        storage.set_alert_notified(alert["id"], ok, error)
    return storage.get_alert(alert["id"])
