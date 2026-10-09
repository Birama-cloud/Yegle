"""API REST.  Lancer :  uvicorn api.main:app --reload   (documentation interactive sur /docs)"""
import json
import secrets
from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.assistant import MAX_TRANSCRIPT, Assistant, Turn
from app.storage import STATUSES, StorageError
from config import settings

app = FastAPI(title=f"{settings.APP_NAME} API", version="0.1.0",
              description="Signalement citoyen vocal et orientation vers le service public compétent.")
MAX_AUDIO_BYTES = 10 * 1024 * 1024


@lru_cache(maxsize=1)
def get_assistant() -> Assistant:
    return Assistant()


def require_admin(x_api_key: str = Header(default="")) -> str:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(503, "Administration désactivée : ADMIN_API_KEY n'est pas configurée")
    if not secrets.compare_digest(x_api_key.encode(), settings.ADMIN_API_KEY.encode()):
        raise HTTPException(401, "Clé d'administration invalide")
    return "admin:api"


class Draft(BaseModel):
    """Brouillon renvoyé par le client entre deux messages : types et longueurs contrôlés.
    Les clés inconnues sont ignorées ; l'organisme et la zone sont de toute façon recalculés."""
    model_config = ConfigDict(extra="ignore")

    category: str | None = Field(default=None, max_length=50)
    subcategory: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=300)
    description_user: str | None = Field(default=None, max_length=300)
    transcript: str = Field(default="", max_length=MAX_TRANSCRIPT)
    location_text: str | None = Field(default=None, max_length=200)
    zone_id: str | None = Field(default=None, max_length=64)
    territorial_area: str | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    urgency: Literal["low", "medium", "high", "critical"] = "medium"
    language: Literal["fr", "wo", "en"] = "fr"
    source: Literal["voice", "text"] = "voice"
    confidence_problem: float = Field(default=0.0, ge=0, le=1)
    confidence_location: float = Field(default=0.0, ge=0, le=1)
    asked: list[Literal["problem", "location", "commune"]] = Field(default_factory=list, max_length=50)


class AnalyzeIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    draft: Draft | None = None
    language: str | None = Field(default=None, pattern="^(fr|wo|en)$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class SubmitIn(BaseModel):
    draft: Draft


class StatusIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=500)


class RerouteIn(BaseModel):
    organization_id: str
    reason: str = Field(min_length=3, max_length=500)


def _turn(turn: Turn) -> dict:
    report = turn.report and get_assistant().storage.public_view(turn.report["reference"])
    return {"kind": turn.kind, "message": turn.message, "language": turn.language, "heard": turn.heard,
            "draft": turn.draft, "routing": turn.decision, "report": report}


# ---------------------------------------------------------------- public
@app.get("/health")
def health():
    a = get_assistant()
    return {"status": "ok", "mode": "offline" if a.offline else "gemini", "knowledge_errors": a.knowledge.validate()}


@app.get("/api/categories")
def categories():
    return [{"id": c.id, "label": c.label, "subcategories": c.subcategories}
            for c in get_assistant().knowledge.categories.values()]


@app.post("/api/analyze")
def analyze(body: AnalyzeIn):
    """Un message écrit du citoyen : renvoie une question, ou un résumé à confirmer."""
    draft = body.draft.model_dump() if body.draft else None
    return _turn(get_assistant().analyze(draft, text=body.text, lang=body.language,
                                         latitude=body.latitude, longitude=body.longitude))


@app.post("/api/analyze/audio")
async def analyze_audio(file: UploadFile = File(...), draft: str = Form(default=""),
                        language: str | None = Form(default=None)):
    """Un message vocal du citoyen. L'audio n'est pas conservé."""
    if not (file.content_type or "").startswith("audio/"):
        raise HTTPException(415, "Fichier audio attendu")
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Enregistrement trop long")
    if language not in (None, *settings.LANGS):
        raise HTTPException(422, "Langue inconnue")
    try:
        parsed = Draft.model_validate(json.loads(draft)).model_dump() if draft else None
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(422, "Brouillon illisible") from e
    return _turn(get_assistant().analyze(parsed, audio=data, mime_type=file.content_type, lang=language))


@app.post("/api/reports", status_code=201)
def create_report(body: SubmitIn):
    """Enregistre un signalement confirmé. L'organisme est recalculé par le serveur."""
    turn = get_assistant().submit(body.draft.model_dump())
    if turn.kind != "done":
        raise HTTPException(422, "Signalement incomplet : catégorie et description obligatoires")
    return _turn(turn)


@app.get("/api/reports/{reference}")
def track(reference: str):
    """Suivi citoyen : statut, organisme destinataire, dates."""
    view = get_assistant().storage.public_view(reference)
    if not view:
        raise HTTPException(404, "Référence inconnue")
    return view


# ---------------------------------------------------------------- administration
@app.get("/api/admin/reports")
def admin_list(organization_id: str | None = None, category: str | None = None, urgency: str | None = None,
               status: str | None = None, _: str = Depends(require_admin)):
    return get_assistant().storage.list_reports(organization_id, category, urgency, status)


@app.get("/api/admin/reports/{reference}")
def admin_detail(reference: str, _: str = Depends(require_admin)):
    storage = get_assistant().storage
    report = storage.get(reference)
    if not report:
        raise HTTPException(404, "Référence inconnue")
    return {"report": report, **storage.history(reference)}


@app.patch("/api/admin/reports/{reference}/status")
def admin_status(reference: str, body: StatusIn, actor: str = Depends(require_admin)):
    if body.status not in STATUSES:
        raise HTTPException(422, "Statut inconnu")
    try:
        return get_assistant().storage.set_status(reference, body.status, actor, body.note)
    except StorageError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/api/admin/reports/{reference}/reroute")
def admin_reroute(reference: str, body: RerouteIn, actor: str = Depends(require_admin)):
    try:
        return get_assistant().reroute(reference, body.organization_id, actor, body.reason)
    except StorageError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/admin/organizations")
def admin_organizations(_: str = Depends(require_admin)):
    return [{"id": o.id, "name": o.name, "type": o.type, "domains": o.domains, "coverage": o.coverage,
             "active": o.active, "last_verified_at": o.last_verified_at, "transmission_mode": o.transmission_mode}
            for o in get_assistant().knowledge.organizations]


@app.get("/api/admin/stats")
def admin_stats(_: str = Depends(require_admin)):
    return get_assistant().storage.stats()
