"""Base de données des signalements (SQLite) : signalements, décisions d'orientation,
historique des statuts et transmissions. Chaque modification est tracée."""
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import settings

STATUSES = ["RECEIVED", "ROUTED", "NEEDS_REVIEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "REJECTED"]
TRANSITIONS = {
    "RECEIVED": {"ROUTED", "NEEDS_REVIEW", "REJECTED"},
    "NEEDS_REVIEW": {"ROUTED", "REJECTED"},
    "ROUTED": {"ASSIGNED", "IN_PROGRESS", "NEEDS_REVIEW", "REJECTED"},
    "ASSIGNED": {"IN_PROGRESS", "NEEDS_REVIEW", "REJECTED"},
    "IN_PROGRESS": {"RESOLVED", "NEEDS_REVIEW"},
    "RESOLVED": {"CLOSED", "IN_PROGRESS"},
    "CLOSED": set(),
    "REJECTED": set(),
}
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans caractères ambigus (0/O, 1/I/L)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reference TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  category TEXT NOT NULL, subcategory TEXT,
  description TEXT NOT NULL, transcript TEXT,
  location_text TEXT, zone_id TEXT, territorial_area TEXT,
  latitude REAL, longitude REAL,
  urgency TEXT NOT NULL, language TEXT NOT NULL, source TEXT NOT NULL,
  confidence_problem REAL, confidence_location REAL,
  org_id TEXT, org_name TEXT, org_service TEXT, confidence_organization REAL,
  routing_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routing_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id),
  decided_at TEXT NOT NULL, actor TEXT NOT NULL,
  org_id TEXT, org_name TEXT, confidence REAL, rule_id TEXT,
  routing_status TEXT NOT NULL, justification TEXT, candidates_json TEXT
);
CREATE TABLE IF NOT EXISTS status_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id),
  changed_at TEXT NOT NULL, old_status TEXT, new_status TEXT NOT NULL,
  actor TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS transmissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id),
  sent_at TEXT NOT NULL, channel TEXT NOT NULL, recipient TEXT,
  success INTEGER NOT NULL, error TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StorageError(ValueError):
    pass


class Storage:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or settings.DB_PATH)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------------ création
    def _new_reference(self) -> str:
        day = datetime.now(timezone.utc).strftime("%y%m%d")
        while True:
            ref = f"{settings.REF_PREFIX}-{day}-" + "".join(secrets.choice(ALPHABET) for _ in range(6))
            if not self.db.execute("SELECT 1 FROM reports WHERE reference = ?", (ref,)).fetchone():
                return ref

    def create_report(self, draft: dict, decision) -> dict:
        t, ref, org = now(), self._new_reference(), decision.organization
        with self.db:
            cur = self.db.execute(
                """INSERT INTO reports (reference, created_at, updated_at, status, category, subcategory,
                   description, transcript, location_text, zone_id, territorial_area, latitude, longitude,
                   urgency, language, source, confidence_problem, confidence_location,
                   org_id, org_name, org_service, confidence_organization, routing_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ref, t, t, "RECEIVED", draft["category"], draft.get("subcategory"), draft["description"],
                 draft.get("transcript"), draft.get("location_text"), draft.get("zone_id"),
                 draft.get("territorial_area"), draft.get("latitude"), draft.get("longitude"),
                 draft.get("urgency", "medium"), draft.get("language", "fr"), draft.get("source", "voice"),
                 draft.get("confidence_problem"), draft.get("confidence_location"),
                 org.org_id if org else None, org.org_name if org else None, org.service if org else None,
                 org.confidence if org else None, decision.status))
            report_id = cur.lastrowid
            self.db.execute("INSERT INTO status_history (report_id, changed_at, old_status, new_status, actor, note)"
                            " VALUES (?,?,?,?,?,?)", (report_id, t, None, "RECEIVED", "system", "Création"))
            self._log_decision(report_id, "engine", org.org_id if org else None, org.org_name if org else None,
                               org.confidence if org else None, org.rule_id if org else None,
                               decision.status, decision.justification,
                               json.dumps([c.__dict__ for c in decision.candidates], ensure_ascii=False))
        return self.get(ref)

    def _log_decision(self, report_id, actor, org_id, org_name, confidence, rule_id, status, justification,
                      candidates_json="[]"):
        self.db.execute(
            "INSERT INTO routing_decisions (report_id, decided_at, actor, org_id, org_name, confidence, rule_id,"
            " routing_status, justification, candidates_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (report_id, now(), actor, org_id, org_name, confidence, rule_id, status, justification, candidates_json))

    # ------------------------------------------------------------------ lecture
    def get(self, reference: str) -> dict | None:
        row = self.db.execute("SELECT * FROM reports WHERE reference = ?",
                              ((reference or "").strip().upper(),)).fetchone()
        return dict(row) if row else None

    def public_view(self, reference: str) -> dict | None:
        """Ce que le citoyen peut consulter : le strict minimum, aucune donnée personnelle."""
        r = self.get(reference)
        if not r:
            return None
        decided = r["status"] not in ("RECEIVED", "NEEDS_REVIEW") and r["org_name"]
        return {"reference": r["reference"], "status": r["status"], "created_at": r["created_at"],
                "updated_at": r["updated_at"], "category": r["category"],
                "organization": r["org_name"] if decided else None}

    def list_reports(self, org_id=None, category=None, urgency=None, status=None, limit: int = 500) -> list[dict]:
        clauses, params = [], []
        for column, value in (("org_id", org_id), ("category", category), ("urgency", urgency), ("status", status)):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.execute(f"SELECT * FROM reports {where} ORDER BY created_at DESC, id DESC LIMIT ?",
                               (*params, int(limit)))
        return [dict(r) for r in rows]

    def history(self, reference: str) -> dict:
        r = self.get(reference)
        if not r:
            raise StorageError("Signalement introuvable")

        def rows(table, order):
            return [dict(x) for x in self.db.execute(
                f"SELECT * FROM {table} WHERE report_id = ? ORDER BY {order}, id", (r["id"],))]

        return {"routing": rows("routing_decisions", "decided_at"), "statuses": rows("status_history", "changed_at"),
                "transmissions": rows("transmissions", "sent_at")}

    def stats(self) -> dict:
        def count(column):
            return {row[0] or "—": row[1] for row in
                    self.db.execute(f"SELECT {column}, COUNT(*) FROM reports GROUP BY {column}")}

        return {"total": self.db.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
                "by_status": count("status"), "by_category": count("category"), "by_organization": count("org_name")}

    # ------------------------------------------------------------------ modification
    def set_status(self, reference: str, new_status: str, actor: str, note: str = "") -> dict:
        r = self.get(reference)
        if not r:
            raise StorageError("Signalement introuvable")
        if new_status not in STATUSES:
            raise StorageError(f"Statut inconnu : {new_status}")
        if new_status not in TRANSITIONS[r["status"]]:
            raise StorageError(f"Passage impossible de {r['status']} à {new_status}")
        t = now()
        with self.db:
            self.db.execute("UPDATE reports SET status = ?, updated_at = ? WHERE id = ?", (new_status, t, r["id"]))
            self.db.execute("INSERT INTO status_history (report_id, changed_at, old_status, new_status, actor, note)"
                            " VALUES (?,?,?,?,?,?)", (r["id"], t, r["status"], new_status, actor, note))
        return self.get(reference)

    def reassign(self, reference: str, org_id: str, org_name: str, service: str | None, actor: str,
                 reason: str) -> dict:
        """Correction manuelle de l'organisme par un administrateur (toujours tracée)."""
        r = self.get(reference)
        if not r:
            raise StorageError("Signalement introuvable")
        if not (reason or "").strip():
            raise StorageError("Un motif est obligatoire pour réorienter un signalement")
        with self.db:
            self.db.execute(
                "UPDATE reports SET org_id = ?, org_name = ?, org_service = ?, confidence_organization = ?,"
                " routing_status = ?, updated_at = ? WHERE id = ?",
                (org_id, org_name, service, 1.0, "ready_for_transmission", now(), r["id"]))
            self._log_decision(r["id"], actor, org_id, org_name, 1.0, None, "ready_for_transmission",
                               f"Orientation manuelle : {reason.strip()}")
        return self.get(reference)

    def add_transmission(self, reference: str, channel: str, recipient: str | None, success: bool,
                         error: str | None = None) -> None:
        r = self.get(reference)
        with self.db:
            self.db.execute("INSERT INTO transmissions (report_id, sent_at, channel, recipient, success, error)"
                            " VALUES (?,?,?,?,?,?)", (r["id"], now(), channel, recipient, int(success), error))
