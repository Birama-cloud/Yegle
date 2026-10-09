"""Accès concurrents à la base : threads (FastAPI, sessions Streamlit) et deux processus sur un même fichier."""
import threading

import pytest

from app.routing import Decision
from app.storage import Storage, StorageError

DECISION = Decision("organization_to_verify", None, [], "test")
DRAFT = {"category": "eau", "description": "Fuite", "urgency": "medium", "language": "fr", "source": "text"}


def _parcours(storage, n, errors):
    for _ in range(n):
        try:
            ref = storage.create_report(DRAFT, DECISION)["reference"]
            storage.set_status(ref, "NEEDS_REVIEW", "t")
            storage.set_status(ref, "ROUTED", "t")
            storage.add_transmission(ref, "internal_queue", "x", True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)


@pytest.mark.parametrize("instances", [1, 2])     # 2 instances = deux processus sur le même fichier
def test_ecritures_concurrentes_coherentes(tmp_path, instances):
    path = tmp_path / "base.sqlite"
    storages = [Storage(path) for _ in range(instances)]
    errors = []
    threads = [threading.Thread(target=_parcours, args=(storages[i % instances], 15, errors)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    reports = storages[0].list_reports(limit=1000)
    assert len(reports) == 90 and len({r["reference"] for r in reports}) == 90
    for r in reports:
        h = storages[0].history(r["reference"])
        assert [s["new_status"] for s in h["statuses"]] == ["RECEIVED", "NEEDS_REVIEW", "ROUTED"]
        assert len(h["transmissions"]) == 1


def test_deux_changements_de_statut_simultanes_un_seul_passe(tmp_path):
    """IN_PROGRESS -> RESOLVED et IN_PROGRESS -> NEEDS_REVIEW sont incompatibles entre eux."""
    path = tmp_path / "base.sqlite"
    a, b = Storage(path), Storage(path)
    ref = a.create_report(DRAFT, DECISION)["reference"]
    for status in ("NEEDS_REVIEW", "ROUTED", "IN_PROGRESS"):
        a.set_status(ref, status, "t")

    barrier, results = threading.Barrier(2), []

    def change(storage, status):
        barrier.wait()
        try:
            storage.set_status(ref, status, "t")
            results.append(status)
        except StorageError:
            results.append("refusé")

    threads = [threading.Thread(target=change, args=(a, "RESOLVED")),
               threading.Thread(target=change, args=(b, "NEEDS_REVIEW"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results).count("refusé") == 1
    statuses = a.history(ref)["statuses"]
    assert [s["old_status"] for s in statuses].count("IN_PROGRESS") == 1
    assert statuses[-1]["old_status"] == "IN_PROGRESS" and a.get(ref)["status"] == statuses[-1]["new_status"]


def test_erreur_dans_une_ecriture_tout_est_annule():
    storage = Storage(":memory:")
    ref = storage.create_report(DRAFT, DECISION)["reference"]
    with pytest.raises(RuntimeError), storage._write():
        storage.db.execute("UPDATE reports SET status = 'CLOSED' WHERE reference = ?", (ref,))
        raise RuntimeError("panne au milieu")
    assert storage.get(ref)["status"] == "RECEIVED"
    storage.set_status(ref, "NEEDS_REVIEW", "t")      # la connexion reste utilisable
    assert storage.get(ref)["status"] == "NEEDS_REVIEW"


def _vieillir(storage, ref, date="2026-01-01T00:00:00+00:00"):
    with storage.transaction():
        storage.db.execute("UPDATE reports SET created_at = ? WHERE reference = ?", (date, ref))


def test_effacement_des_transcriptions_anciennes():
    storage = Storage(":memory:")
    old = storage.create_report({**DRAFT, "transcript": "Fuite devant chez Awa, 77 000 00 00"}, DECISION)["reference"]
    recent = storage.create_report({**DRAFT, "transcript": "Fuite rue 10"}, DECISION)["reference"]
    _vieillir(storage, old)

    assert storage.purge_transcripts(90) == 1
    assert storage.get(old)["transcript"] is None and storage.get(old)["transcript_purged_at"]
    assert storage.get(old)["description"] == "Fuite"                 # description neutre conservée
    assert storage.get(recent)["transcript"] == "Fuite rue 10"
    assert storage.purge_transcripts(90) == 0                         # une seule fois
    assert storage.purge_transcripts(0) == 0                          # 0 = conservation sans limite


def test_message_envoye_tel_quel_description_effacee_aussi():
    storage = Storage(":memory:")
    words = "Un chien mort devant chez Moussa Diop"
    ref = storage.create_report({**DRAFT, "category": "autre", "description": words, "transcript": words,
                                 "confidence_problem": 0.0}, DECISION)["reference"]
    _vieillir(storage, ref)
    storage.purge_transcripts(90)
    assert "Moussa" not in storage.get(ref)["description"] and "effacé" in storage.get(ref)["description"]


def test_effacement_au_demarrage(verified, gazetteer, tmp_path):
    from app.assistant import Assistant

    path = tmp_path / "base.sqlite"
    storage = Storage(path)
    ref = storage.create_report({**DRAFT, "transcript": "Fuite"}, DECISION)["reference"]
    _vieillir(storage, ref)
    Assistant(llm=None, knowledge=verified, gazetteer=gazetteer, storage=Storage(path))
    assert storage.get(ref)["transcript"] is None


def test_ancienne_base_migree_sans_perte(tmp_path):
    import sqlite3

    path = tmp_path / "ancienne.sqlite"
    old = sqlite3.connect(path)
    old.executescript("""CREATE TABLE reports (id INTEGER PRIMARY KEY AUTOINCREMENT, reference TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, status TEXT NOT NULL, category TEXT NOT NULL,
        subcategory TEXT, description TEXT NOT NULL, transcript TEXT, location_text TEXT, zone_id TEXT,
        territorial_area TEXT, latitude REAL, longitude REAL, urgency TEXT NOT NULL, language TEXT NOT NULL,
        source TEXT NOT NULL, confidence_problem REAL, confidence_location REAL, org_id TEXT, org_name TEXT,
        org_service TEXT, confidence_organization REAL, routing_status TEXT NOT NULL);
        INSERT INTO reports (reference, created_at, updated_at, status, category, description, transcript, urgency,
        language, source, routing_status) VALUES ('YGL-260101-AAAAAA', '2026-01-01T00:00:00+00:00',
        '2026-01-01T00:00:00+00:00', 'ROUTED', 'eau', 'Fuite', 'Message', 'medium', 'fr', 'text', 'x');""")
    old.close()

    storage = Storage(path)
    assert storage.get("YGL-260101-AAAAAA")["transcript"] == "Message"
    assert storage.purge_transcripts(90) == 1 and storage.get("YGL-260101-AAAAAA")["transcript"] is None


def test_journal_wal_sur_fichier(tmp_path):
    storage = Storage(tmp_path / "base.sqlite")
    assert storage._query("PRAGMA journal_mode")[0]["journal_mode"] == "wal"
