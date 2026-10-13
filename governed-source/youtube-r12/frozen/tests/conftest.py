from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def make_test_client(request):
    clients = []

    def factory(*args, **kwargs):
        client = TestClient(*args, **kwargs)
        client.__enter__()
        clients.append(client)
        return client

    def close_all():
        for client in reversed(clients):
            client.__exit__(None, None, None)

    request.addfinalizer(close_all)
    return factory


@pytest.fixture(autouse=True)
def cleanup_governance_clones_after_test():
    """Prevent isolated governance stores from accumulating across a full pytest session."""
    yield
    from tests._governance_template import cleanup_isolated_governance_ledgers
    cleanup_isolated_governance_ledgers()
