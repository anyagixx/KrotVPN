import pytest

from app.cli import issue_internal_client


class DummyAsyncSession:
    def __init__(self):
        self.commit_calls = 0

    async def commit(self):
        self.commit_calls += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class DummyUser:
    def __init__(self, user_id: int):
        self.id = user_id


class DummySubscription:
    def __init__(self, subscription_id: int):
        self.id = subscription_id


class DummyClient:
    def __init__(self, client_id: int):
        self.id = client_id


class DummyConfig:
    def __init__(self):
        self.config = "[Interface]\nPrivateKey = test\n"
        self.address = "10.10.0.9"


@pytest.mark.asyncio
async def test_issue_internal_client_orchestrates_services(monkeypatch):
    session = DummyAsyncSession()

    class StubUserService:
        def __init__(self, current_session):
            assert current_session is session

        async def resolve_internal_user(self, identity, *, display_name=None):
            assert identity == "family-phone"
            assert display_name == "Family Phone"
            return DummyUser(10)

    class StubBillingService:
        def __init__(self, current_session):
            assert current_session is session

        async def ensure_complimentary_access(self, user_id, *, access_label):
            assert user_id == 10
            assert access_label == "family"
            return DummySubscription(20)

    class StubVPNService:
        def __init__(self, current_session):
            assert current_session is session

        async def provision_internal_client(self, user_id, *, reprovision):
            assert user_id == 10
            assert reprovision is True
            return DummyClient(30)

        async def get_client_config(self, client):
            assert client.id == 30
            return DummyConfig()

    monkeypatch.setattr("app.cli.async_session_maker", lambda: session)
    monkeypatch.setattr("app.cli.UserService", StubUserService)
    monkeypatch.setattr("app.cli.BillingService", StubBillingService)
    monkeypatch.setattr("app.cli.VPNService", StubVPNService)

    user, subscription, client, config = await issue_internal_client(
        "family-phone",
        output="/tmp/family-phone.conf",
        display_name="Family Phone",
        access_label="family",
        reprovision=True,
    )

    assert user.id == 10
    assert subscription.id == 20
    assert client.id == 30
    assert config.address == "10.10.0.9"
    assert session.commit_calls == 1
