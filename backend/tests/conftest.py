"""Test-wide configuration.

Pins the suite to a local database regardless of what ``.env`` holds. Once
``.env`` points at Supabase — which it does as soon as anyone sets up
deployment — an unpinned suite runs every assertion over the network against
the production database. That is slow enough to stop being run and dangerous
enough that it should not be possible by accident.

This must happen before ``lighthouse.core.db`` is imported, since the engine is
created at module import from the cached settings. pytest loads conftest first,
so setting the environment here is early enough.
"""

import os

os.environ["LIGHTHOUSE_DATABASE_URL"] = os.environ.get(
    "LIGHTHOUSE_TEST_DATABASE_URL", "postgresql+psycopg://localhost/lighthouse"
)

import uuid  # noqa: E402

import pytest  # noqa: E402

from lighthouse.core.config import get_settings  # noqa: E402

get_settings.cache_clear()


_SCRATCH_OPERATORS: list[uuid.UUID] = []


@pytest.fixture
def scratch_operator(monkeypatch):
    """Send this test's writes to an operator that exists nowhere else.

    Tests that go through the app rather than the service layer cannot be
    wrapped in a transaction the test controls — the request handler owns it and
    commits. So isolation has to be by identity instead: a throwaway ``user_id``
    nothing else can see.

    Handing out the id is all this does. The delete happens once for the whole
    run (below), because sweeping eleven tables after every request-level test
    took the suite from five seconds to thirty, and a suite that is slow enough
    to skip protects nothing.
    """
    settings = get_settings()
    scratch = uuid.uuid4()
    _SCRATCH_OPERATORS.append(scratch)
    monkeypatch.setattr(settings, "operator_id", scratch, raising=False)
    return scratch


@pytest.fixture(scope="session", autouse=True)
def _sweep_scratch_operators():
    """Delete everything the scratch operators wrote, once, at the end.

    Every personal table is swept rather than the ones today's tests happen to
    touch, so a table added next month is covered the day it is added rather
    than the day someone notices the orphans. Children before parents, so a
    foreign key never blocks it.

    Until this existed each suite run left one committed row per write endpoint
    behind in whatever database the suite was pointed at — invisible,
    individually harmless, and unbounded.
    """
    yield

    if not _SCRATCH_OPERATORS:
        return

    from sqlalchemy import delete

    from lighthouse.core.db import SessionLocal
    from lighthouse.core.models import Base

    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            if "user_id" in table.c:
                session.execute(
                    delete(table).where(table.c.user_id.in_(_SCRATCH_OPERATORS))
                )
        session.commit()
