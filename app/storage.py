"""Base de données des signalements (SQLite) : signalements, décisions d'orientation,
historique des statuts et transmissions. Chaque modification est tracée.

Accès concurrents : une instance est partagée par les threads de FastAPI et par toutes les
sessions Streamlit, et l'API et l'interface sont deux processus sur le même fichier.
- un verrou par instance : une seule opération à la fois sur la connexion ;
- chaque écriture est une transaction BEGIN IMMEDIATE : la lecture qui la précède (statut
  actuel, existence du signalement) et l'écriture forment un tout, même entre processus ;
- journal WAL et délai d'attente : les lectures ne bloquent pas, les écritures patientent.
"""
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
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
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL UNIQUE REFERENCES reports(id),
  created_at TEXT NOT NULL, reason TEXT NOT NULL,
  notified INTEGER NOT NULL DEFAULT 0, notify_error TEXT,
  acknowledged_at TEXT, acknowledged_by TEXT
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
        # isolation_level=None : les transactions sont ouvertes explicitement par _write().
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        self.db.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self.db.execute("PRAGMA journal_mode = WAL")
        with self._write():
            for statement in filter(str.strip, SCHEMA.split(";")):
                self.db.execute(statement)

    @contextmanager
    def _write(self):
        """Transaction d'écriture. Réentrante : un appel imbriqué rejoint la transaction en cours."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self.db.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self.db.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outer:
                self.db.execute("COMMIT")

    def _query(self, sql: str, params=()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    # ------------------------------------------------------------------ création
    def _new_reference(self) -> str:
        day = datetime.now(timezone.utc).strftime("%y%m%d")
        while True:
            ref = f"{settings.REF_PREFIX}-{day}-" + "".join(secrets.choice(ALPHABET) for _ in range(6))
            if not self._query("SELECT 1 FROM reports WHERE reference = ?", (ref,)):
                return ref

    def create_report(self, draft: dict, decision) -> dict:
        org = decision.organization
        with self._write():
            t, ref = now(), self._new_reference()     # référence tirée dans la transaction : unique
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
        rows = self._query("SELECT * FROM reports WHERE reference = ?", ((reference or "").strip().upper(),))
        return rows[0] if rows else None

    def _require(self, reference: str) -> dict:
        r = self.get(reference)
        if not r:
            raise StorageError("Signalement introuvable")
        return r

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
        return self._query(f"SELECT * FROM reports {where} ORDER BY created_at DESC, id DESC LIMIT ?",
                           (*params, int(limit)))

    def history(self, reference: str) -> dict:
        with self._lock:
            r = self._require(reference)

            def rows(table, order):
                return self._query(f"SELECT * FROM {table} WHERE report_id = ? ORDER BY {order}, id", (r["id"],))

            return {"routing": rows("routing_decisions", "decided_at"),
                    "statuses": rows("status_history", "changed_at"), "transmissions": rows("transmissions", "sent_at"),
                    "alerts": rows("alerts", "created_at")}

    def stats(self) -> dict:
        with self._lock:
            def count(column):
                return {row[column] or "—": row["n"] for row in
                        self._query(f"SELECT {column}, COUNT(*) AS n FROM reports GROUP BY {column}")}

            return {"total": self._query("SELECT COUNT(*) AS n FROM reports")[0]["n"],
                    "by_status": count("status"), "by_category": count("category"),
                    "by_organization": count("org_name")}

    # ------------------------------------------------------------------ modification
    def set_status(self, reference: str, new_status: str, actor: str, note: str = "") -> dict:
        """Le statut actuel est relu dans la transaction : deux changements simultanés ne peuvent
        pas partir du même statut, le second est contrôlé par rapport au résultat du premier."""
        if new_status not in STATUSES:
            raise StorageError(f"Statut inconnu : {new_status}")
        with self._write():
            r = self._require(reference)
            if new_status not in TRANSITIONS[r["status"]]:
                raise StorageError(f"Passage impossible de {r['status']} à {new_status}")
            t = now()
            self.db.execute("UPDATE reports SET status = ?, updated_at = ? WHERE id = ?", (new_status, t, r["id"]))
            self.db.execute("INSERT INTO status_history (report_id, changed_at, old_status, new_status, actor, note)"
                            " VALUES (?,?,?,?,?,?)", (r["id"], t, r["status"], new_status, actor, note))
            return self.get(reference)

    def reassign(self, reference: str, org_id: str, org_name: str, service: str | None, actor: str,
                 reason: str) -> dict:
        """Correction manuelle de l'organisme par un administrateur (toujours tracée)."""
        if not (reason or "").strip():
            raise StorageError("Un motif est obligatoire pour réorienter un signalement")
        with self._write():
            r = self._require(reference)
            self.db.execute(
                "UPDATE reports SET org_id = ?, org_name = ?, org_service = ?, confidence_organization = ?,"
                " routing_status = ?, updated_at = ? WHERE id = ?",
                (org_id, org_name, service, 1.0, "ready_for_transmission", now(), r["id"]))
            self._log_decision(r["id"], actor, org_id, org_name, 1.0, None, "ready_for_transmission",
                               f"Orientation manuelle : {reason.strip()}")
            return self.get(reference)

    # ------------------------------------------------------------------ alertes
    def add_alert(self, reference: str, reason: str) -> dict | None:
        """Une alerte par signalement au plus. Renvoie None si elle existait déjà."""
        with self._write():
            r = self._require(reference)
            cur = self.db.execute("INSERT OR IGNORE INTO alerts (report_id, created_at, reason) VALUES (?,?,?)",
                                  (r["id"], now(), reason))
            return self.get_alert(cur.lastrowid) if cur.rowcount else None

    def set_alert_notified(self, alert_id: int, ok: bool, error: str | None = None) -> None:
        with self._write():
            self.db.execute("UPDATE alerts SET notified = ?, notify_error = ? WHERE id = ?",
                            (int(ok), error, alert_id))

    def acknowledge_alert(self, alert_id: int, actor: str) -> dict:
        """Prise en charge par un administrateur, tracée. Une seule fois par alerte."""
        with self._write():
            alert = self.get_alert(alert_id)
            if not alert:
                raise StorageError("Alerte introuvable")
            if alert["acknowledged_at"]:
                raise StorageError(f"Alerte déjà prise en charge par {alert['acknowledged_by']}")
            self.db.execute("UPDATE alerts SET acknowledged_at = ?, acknowledged_by = ? WHERE id = ?",
                            (now(), actor, alert_id))
            return self.get_alert(alert_id)

    _ALERTS = ("SELECT a.*, r.reference, r.category, r.urgency, r.status, r.location_text, r.territorial_area,"
               " r.org_name, r.description FROM alerts a JOIN reports r ON r.id = a.report_id")

    def get_alert(self, alert_id: int) -> dict | None:
        rows = self._query(self._ALERTS + " WHERE a.id = ?", (alert_id,))
        return rows[0] if rows else None

    def list_alerts(self, open_only: bool = True) -> list[dict]:
        where = " WHERE a.acknowledged_at IS NULL" if open_only else ""
        return self._query(self._ALERTS + where + " ORDER BY a.created_at DESC, a.id DESC")

    def add_transmission(self, reference: str, channel: str, recipient: str | None, success: bool,
                         error: str | None = None) -> None:
        with self._write():
            r = self._require(reference)
            self.db.execute("INSERT INTO transmissions (report_id, sent_at, channel, recipient, success, error)"
                            " VALUES (?,?,?,?,?,?)", (r["id"], now(), channel, recipient, int(success), error))
