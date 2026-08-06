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

from lighthouse.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
