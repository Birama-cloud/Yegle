"""Orchestration du parcours citoyen :
écouter -> comprendre -> localiser -> orienter -> faire confirmer -> enregistrer -> transmettre.

Le brouillon (draft) est un simple dictionnaire : il vit côté interface entre deux messages.
Au moment de l'envoi, tout est recalculé côté serveur (zone, organisme) : on ne fait
jamais confiance à un organisme ou à un niveau de confiance venu du client.
"""
from dataclasses import dataclass, field

from app import routing, transmission
from app.knowledge import Knowledge
from app.messages import msg
from app.storage import Storage, StorageError
from app.understanding import extract_llm, extract_rules
from app.zones import Gazetteer
from config import settings

MAX_PROBLEM_QUESTIONS = 2
MAX_TRANSCRIPT = 8000         # on garde la fin de la conversation au-delà
FINAL_STATUSES = ("RESOLVED", "CLOSED", "REJECTED")


@dataclass
class Turn:
    kind: str                 # clarify | confirm | done | not_heard | error | cancelled
    message: str
    language: str = "fr"
    draft: dict = field(default_factory=dict)
    decision: dict | None = None
    report: dict | None = None
    heard: str = ""


def new_draft() -> dict:
    return {"category": None, "subcategory": None, "description": None, "description_user": None,
            "transcript": "", "location_text": None, "zone_id": None, "territorial_area": None,
            "latitude": None, "longitude": None, "urgency": "medium", "language": "fr", "source": "voice",
            "confidence_problem": 0.0, "confidence_location": 0.0, "asked": []}


class Assistant:
    def __init__(self, llm=None, knowledge: Knowledge | None = None, gazetteer: Gazetteer | None = None,
                 storage: Storage | None = None):
        self.knowledge = knowledge or Knowledge.load()
        self.gazetteer = gazetteer or Gazetteer.load()
        self.storage = storage or Storage()
        self.llm = llm
        if llm is None and settings.LLM_MODE == "gemini":
            from app.llm.client import LLMClient

            self.llm = LLMClient()

    @property
    def offline(self) -> bool:
        return self.llm is None

    # ------------------------------------------------------------------ compréhension
    def _extract(self, text, audio, mime_type, draft):
        from app.llm.client import LLMUnavailable

        if self.llm is not None:
            try:
                return extract_llm(self.llm, self.knowledge, text, audio, mime_type, draft), None
            except LLMUnavailable as e:
                if audio or not text:
                    return None, e
        if not text:
            return None, RuntimeError("Le mode hors ligne ne traite que le texte")
        return extract_rules(self.knowledge, self.gazetteer, text, draft), None

    def _locate(self, draft: dict):
        """Zone du signalement : GPS fourni par le citoyen, sinon lieu dit. Jamais de coordonnées inventées."""
        zone = None
        if draft.get("latitude") is not None and draft.get("longitude") is not None:
            zone = self.gazetteer.nearest(draft["latitude"], draft["longitude"])
            confidence = 0.9 if zone else 0.3
        if zone is None:
            zone, confidence = self.gazetteer.resolve(draft.get("location_text"))
        draft["zone_id"] = zone.id if zone else None
        draft["territorial_area"] = zone.name if zone else None
        draft["confidence_location"] = confidence
        return zone

    def _route(self, draft: dict):
        zone = self._locate(draft)
        return routing.route(self.knowledge, draft["category"], draft.get("subcategory"), zone,
                             draft.get("confidence_problem", 0.0))

    # ------------------------------------------------------------------ un message du citoyen
    def analyze(self, draft: dict | None = None, text: str | None = None, audio: bytes | None = None,
                mime_type: str = "audio/wav", lang: str | None = None,
                latitude: float | None = None, longitude: float | None = None) -> Turn:
        draft = {**new_draft(), **(draft or {})}
        draft["asked"] = list(draft.get("asked") or [])
        fallback_lang = lang or draft.get("language") or "fr"

        extraction, error = self._extract(text, audio, mime_type, draft)
        if error is not None:
            key = "quota" if getattr(error, "quota", False) else "error"
            return Turn("error", msg(key, fallback_lang), fallback_lang, draft)
        heard = extraction["transcription"]
        if audio and not heard:
            return Turn("not_heard", msg("not_heard", fallback_lang), fallback_lang, draft)

        language = lang or extraction["language"]
        draft["language"] = language
        if audio:
            draft["source"] = "voice"
        elif not draft["transcript"]:
            draft["source"] = "text"
        draft["transcript"] = (draft["transcript"] + "\n" + heard).strip()[-MAX_TRANSCRIPT:]
        if latitude is not None and longitude is not None:
            draft["latitude"], draft["longitude"] = float(latitude), float(longitude)

        # Un message de suivi (« à Grand-Yoff ») complète le brouillon même s'il ne décrit pas de problème.
        if extraction["is_report"] or draft["category"]:
            for key in ("category", "subcategory", "description", "description_user", "location_text"):
                if extraction.get(key):
                    draft[key] = extraction[key]
            if extraction.get("description"):
                draft["urgency"] = extraction["urgency"]
                draft["confidence_problem"] = extraction["confidence_problem"]

        # 1. Le problème est-il compris ?
        if not draft["category"] or not draft["description"]:
            asked = draft["asked"].count("problem")
            draft["asked"].append("problem")
            key = "not_report" if asked == 0 else "ask_problem"
            if asked >= MAX_PROBLEM_QUESTIONS:
                key = "not_report"
            return Turn("clarify", msg(key, language), language, draft, heard=heard)

        # 2. Le lieu est-il connu ? Une seule question à la fois, jamais deux fois la même.
        zone = self._locate(draft)
        has_gps = draft.get("latitude") is not None
        if not draft["location_text"] and not has_gps and "location" not in draft["asked"]:
            draft["asked"].append("location")
            return Turn("clarify", msg("ask_location", language), language, draft, heard=heard)
        # La commune n'est demandée que si elle peut changer l'orientation : inutile pour un
        # organisme qui couvre déjà la zone sans dépendre de la commune (ex. SONAGED).
        decision = self._route(draft)
        if not (zone and zone.is_commune) and not decision.ready and "commune" not in draft["asked"]:
            draft["asked"].append("commune")
            return Turn("clarify", msg("ask_commune", language), language, draft, heard=heard)

        # 3. Résumé à confirmer.
        place = draft["location_text"] or draft["territorial_area"] or msg("unknown_place", language)
        description = draft.get("description_user") or draft["description"]
        if decision.ready:
            text_out = msg("summary_known", language, description=description.rstrip("."), place=place,
                           org=decision.organization.org_name)
        else:
            text_out = msg("summary_review", language, description=description.rstrip("."), place=place)
        if draft["urgency"] == "critical":
            text_out += " " + msg("emergency", language)
        return Turn("confirm", text_out, language, draft, decision.to_dict(), heard=heard)

    # ------------------------------------------------------------------ confirmation du citoyen
    def submit(self, draft: dict) -> Turn:
        """Enregistre le signalement confirmé. L'orientation est recalculée ici."""
        draft = {**new_draft(), **(draft or {})}
        language = draft["language"] if draft.get("language") in settings.LANGS else "fr"
        if draft.get("category") not in self.knowledge.categories or not (draft.get("description") or "").strip():
            return Turn("error", msg("ask_problem", language), language, draft)
        draft["language"] = language
        if draft.get("urgency") not in ("low", "medium", "high", "critical"):
            draft["urgency"] = "medium"
        if draft.get("subcategory") not in self.knowledge.categories[draft["category"]].subcategories:
            draft["subcategory"] = None

        decision = self._route(draft)
        report = self.storage.create_report(draft, decision)
        sent = decision.ready and transmission.transmit(self.storage, self.knowledge, report)
        if not decision.ready:
            self.storage.set_status(report["reference"], "NEEDS_REVIEW", "system", decision.justification)
        report = self.storage.get(report["reference"])
        if sent:
            text_out = msg("done_routed", language, org=report["org_name"], ref=report["reference"])
        else:
            text_out = msg("done_review", language, ref=report["reference"])
        return Turn("done", text_out, language, draft, decision.to_dict(), report)

    # ------------------------------------------------------------------ administration
    def organization_choices(self, zone_id: str | None = None) -> list[tuple[str, str]]:
        """Organismes vers lesquels un administrateur peut réorienter (identifiant, nom)."""
        zone, choices = self.gazetteer.get(zone_id), []
        for org in self.knowledge.organizations:
            if not org.active:
                continue
            if org.per_commune:
                communes = [zone] if zone and zone.is_commune else [z for z in self.gazetteer.zones if z.is_commune]
                choices += [(f"{org.id}:{z.id}", org.name.format(commune=z.name)) for z in communes]
            else:
                choices.append((org.id, org.name))
        return choices

    def reroute(self, reference: str, org_id: str, actor: str, reason: str) -> dict:
        """Réorientation manuelle : la destination doit exister dans la base de connaissances."""
        report = self.storage.get(reference)
        if not report:
            raise StorageError("Signalement introuvable")
        if report["status"] in FINAL_STATUSES:
            raise StorageError("Ce signalement est terminé : il ne peut plus être réorienté")
        names = dict(self.organization_choices())
        org = self.knowledge.get_org(org_id)
        if org is None or org_id not in names:
            raise StorageError("Organisme inconnu de la base de connaissances")
        report = self.storage.reassign(reference, org_id, names[org_id], org.service_for(report["subcategory"]),
                                       actor, reason)
        transmission.transmit(self.storage, self.knowledge, report, actor)
        return self.storage.get(reference)
