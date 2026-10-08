"""Base de connaissances institutionnelle : catégories et organismes (fichiers YAML)."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from config import settings

COVERAGE_PREFIXES = ("region:", "departement:", "zone:")
TRANSMISSION_MODES = ("internal_queue", "webhook")


@dataclass
class Category:
    id: str
    label: dict
    subcategories: list
    keywords: list

    def name(self, lang: str = "fr") -> str:
        return self.label.get(lang) or self.label.get("fr") or self.id


@dataclass
class Rule:
    rule_id: str
    category: str
    confidence: float = 0.8
    subcategories: list = field(default_factory=list)


@dataclass
class Organization:
    id: str
    name: str
    type: str
    domains: list
    coverage: list
    rules: list
    services: list = field(default_factory=list)
    subcategories: list = field(default_factory=list)
    contact_channels: list = field(default_factory=list)
    api_endpoint: str | None = None
    transmission_mode: str = "internal_queue"
    escalation_rules: list = field(default_factory=list)
    active: bool = True
    last_verified_at: str | None = None
    per_commune: bool = False
    source_url: str | None = None

    @property
    def display_name(self) -> str:
        return self.name.format(commune="chaque commune") if self.per_commune else self.name

    @property
    def verified(self) -> bool:
        return bool(self.last_verified_at)

    def service_for(self, subcategory: str | None) -> str | None:
        for s in self.services:
            if not s.get("subcategories") or subcategory in s["subcategories"]:
                return s.get("name")
        return None


class Knowledge:
    def __init__(self, categories: list[Category], organizations: list[Organization]):
        self.categories = {c.id: c for c in categories}
        self.organizations = organizations
        self._category_list = categories

    @classmethod
    def load(cls, categories_file: Path | None = None, organismes_file: Path | None = None) -> "Knowledge":
        cats_raw = yaml.safe_load(Path(categories_file or settings.CATEGORIES_FILE).read_text(encoding="utf-8")) or []
        orgs_raw = yaml.safe_load(Path(organismes_file or settings.ORGANISMES_FILE).read_text(encoding="utf-8")) or []
        categories = [Category(c["id"], c.get("label") or {}, c.get("subcategories") or ["autre"],
                               c.get("keywords") or []) for c in cats_raw]
        organizations = []
        for o in orgs_raw:
            verified = o.get("last_verified_at")
            organizations.append(Organization(
                id=o["organization_id"], name=o["organization_name"], type=o.get("organization_type", ""),
                domains=o.get("domains") or [], coverage=o.get("territorial_coverage") or [],
                rules=[Rule(r["rule_id"], r["category"], float(r.get("confidence", 0.8)),
                            r.get("subcategories") or []) for r in o.get("routing_rules") or []],
                services=o.get("responsible_services") or [], subcategories=o.get("subcategories") or [],
                contact_channels=o.get("contact_channels") or [],
                api_endpoint=o.get("api_endpoint_if_available"),
                transmission_mode=o.get("transmission_mode", "internal_queue"),
                escalation_rules=o.get("escalation_rules") or [], active=bool(o.get("active_status", True)),
                last_verified_at=str(verified) if verified else None,
                per_commune=bool(o.get("per_commune", False)), source_url=o.get("source_url")))
        return cls(categories, organizations)

    def category_ids(self) -> list[str]:
        return [c.id for c in self._category_list]

    def get_org(self, org_id: str) -> Organization | None:
        """Accepte aussi un identifiant résolu par commune, ex. ORG_MAIRIE:grand-yoff."""
        base = (org_id or "").split(":", 1)[0]
        return next((o for o in self.organizations if o.id == base), None)

    def validate(self) -> list[str]:
        """Renvoie la liste des erreurs de configuration (vide si tout est cohérent)."""
        errors, seen_orgs, seen_rules = [], set(), set()
        if "autre" not in self.categories:
            errors.append("categories.yaml : la catégorie 'autre' est obligatoire")
        for o in self.organizations:
            where = f"organismes.yaml [{o.id}]"
            if o.id in seen_orgs:
                errors.append(f"{where} : identifiant en double")
            seen_orgs.add(o.id)
            if ":" in o.id:
                errors.append(f"{where} : ':' interdit dans organization_id")
            for d in o.domains:
                if d not in self.categories:
                    errors.append(f"{where} : domaine inconnu '{d}'")
            if not o.coverage:
                errors.append(f"{where} : territorial_coverage vide")
            for c in o.coverage:
                if c != "national" and not c.startswith(COVERAGE_PREFIXES):
                    errors.append(f"{where} : couverture invalide '{c}'")
            if o.transmission_mode not in TRANSMISSION_MODES:
                errors.append(f"{where} : transmission_mode invalide '{o.transmission_mode}'")
            if o.transmission_mode == "webhook" and not str(o.api_endpoint or "").startswith("https://"):
                errors.append(f"{where} : le mode webhook exige une adresse https")
            if o.per_commune and "{commune}" not in o.name:
                errors.append(f"{where} : per_commune exige '{{commune}}' dans organization_name")
            if o.last_verified_at:
                try:
                    date.fromisoformat(o.last_verified_at)
                except ValueError:
                    errors.append(f"{where} : last_verified_at doit être au format AAAA-MM-JJ")
            for r in o.rules:
                if r.rule_id in seen_rules:
                    errors.append(f"{where} : règle en double '{r.rule_id}'")
                seen_rules.add(r.rule_id)
                if r.category not in self.categories:
                    errors.append(f"{where} : règle {r.rule_id}, catégorie inconnue '{r.category}'")
                if r.category not in o.domains:
                    errors.append(f"{where} : règle {r.rule_id}, catégorie hors des domaines de l'organisme")
                if not 0 < r.confidence <= 1:
                    errors.append(f"{where} : règle {r.rule_id}, confidence doit être entre 0 et 1")
        return errors
