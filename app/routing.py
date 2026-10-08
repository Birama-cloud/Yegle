"""Moteur d'orientation institutionnelle.

Entièrement déterministe : il ne s'appuie que sur la base de connaissances
(data/organismes.yaml) et jamais sur la mémoire du modèle d'IA.

Confiance d'un candidat = confiance de la règle
    x 0.6 si la zone est inconnue
    x 0.5 si l'organisme dépend de la commune et que la commune n'est pas identifiée
    x 0.7 si la fiche de l'organisme n'a pas été vérifiée
Un candidat hors de sa zone de couverture est écarté.
Le signalement part en vérification humaine si la confiance est sous le seuil,
si deux candidats sont trop proches, ou si le problème est mal compris.
"""
from dataclasses import asdict, dataclass, field

from app.knowledge import Knowledge, Organization
from app.zones import Zone, covers
from config import settings

READY = "ready_for_transmission"
REVIEW = "organization_to_verify"


@dataclass
class Candidate:
    org_id: str
    org_name: str
    service: str | None
    confidence: float
    rule_id: str
    verified: bool
    notes: list = field(default_factory=list)


@dataclass
class Decision:
    status: str                       # READY | REVIEW
    organization: Candidate | None    # meilleur candidat (même en REVIEW, à titre indicatif)
    candidates: list
    justification: str
    reasons: list = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == READY

    def to_dict(self) -> dict:
        return asdict(self)


def _resolve_name(org: Organization, zone: Zone | None) -> tuple[str, str]:
    if org.per_commune and zone is not None and zone.is_commune:
        return f"{org.id}:{zone.id}", org.name.format(commune=zone.name)
    if org.per_commune:
        return org.id, org.name.format(commune="la commune concernée")
    return org.id, org.name


def route(knowledge: Knowledge, category: str | None, subcategory: str | None = None,
          zone: Zone | None = None, confidence_problem: float = 1.0) -> Decision:
    candidates = []
    for org in knowledge.organizations:
        if not org.active:
            continue
        covered = covers(org.coverage, zone)
        if covered is False:
            continue
        for rule in org.rules:
            if rule.category != category:
                continue
            if rule.subcategories and subcategory not in rule.subcategories:
                continue
            if org.subcategories and subcategory not in org.subcategories:
                continue
            confidence, notes = rule.confidence, []
            if covered is None:
                confidence *= 0.6
                notes.append("zone inconnue")
            if org.per_commune and not (zone and zone.is_commune):
                confidence *= 0.5
                notes.append("commune non identifiée")
            if settings.ROUTING_REQUIRE_VERIFIED and not org.verified:
                confidence *= 0.7
                notes.append("fiche organisme non vérifiée")
            org_id, org_name = _resolve_name(org, zone)
            candidates.append(Candidate(org_id, org_name, org.service_for(subcategory),
                                        round(confidence, 2), rule.rule_id, org.verified, notes))
    candidates.sort(key=lambda c: c.confidence, reverse=True)

    if not candidates:
        where = f" dans la zone « {zone.name} »" if zone else ""
        return Decision(REVIEW, None, [], f"Aucun organisme configuré pour la catégorie « {category} »{where}.",
                        ["aucun organisme correspondant"])

    best, reasons = candidates[0], []
    if best.confidence < settings.ROUTING_MIN_CONFIDENCE:
        reasons.append(f"confiance {best.confidence:.2f} sous le seuil {settings.ROUTING_MIN_CONFIDENCE:.2f}"
                       + (f" ({', '.join(best.notes)})" if best.notes else ""))
    if len(candidates) > 1 and best.confidence - candidates[1].confidence < settings.ROUTING_AMBIGUITY_MARGIN:
        reasons.append(f"plusieurs organismes possibles ({best.org_name}, {candidates[1].org_name})")
    if confidence_problem < settings.MIN_CONFIDENCE_PROBLEM:
        reasons.append("problème insuffisamment compris")

    place = f", zone « {zone.name} »" if zone else ", zone inconnue"
    justification = (f"Règle {best.rule_id} : catégorie « {category} »{place} → {best.org_name} "
                     f"(confiance {best.confidence:.2f}).")
    if reasons:
        justification += " Vérification humaine demandée : " + " ; ".join(reasons) + "."
    return Decision(REVIEW if reasons else READY, best, candidates, justification, reasons)
