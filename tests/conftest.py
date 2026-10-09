"""Les tests n'appellent aucun service extérieur : mode hors ligne et base en mémoire."""
import os

os.environ.update({"LLM_MODE": "offline", "GEMINI_API_KEY": "", "ADMIN_API_KEY": "cle-de-test",
                   "DB_PATH": ":memory:", "ROUTING_REQUIRE_VERIFIED": "true", "REF_PREFIX": "YGL"})

import pytest  # noqa: E402

from app.assistant import Assistant  # noqa: E402
from app.knowledge import Knowledge  # noqa: E402
from app.storage import Storage  # noqa: E402
from app.zones import Gazetteer  # noqa: E402


@pytest.fixture
def knowledge():
    return Knowledge.load()


@pytest.fixture
def unverified(knowledge):
    """Base de connaissances dont aucune fiche n'a été vérifiée."""
    for org in knowledge.organizations:
        org.last_verified_at = None
    return knowledge


@pytest.fixture
def verified(knowledge):
    """Base de connaissances dont toutes les fiches ont été vérifiées."""
    for org in knowledge.organizations:
        org.last_verified_at = "2026-10-08"
    return knowledge


@pytest.fixture
def gazetteer():
    return Gazetteer.load()


@pytest.fixture
def assistant(verified, gazetteer):
    return Assistant(llm=None, knowledge=verified, gazetteer=gazetteer, storage=Storage(":memory:"))
