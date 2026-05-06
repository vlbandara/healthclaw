"""Tenant isolation integration tests.

Requires a running Postgres with the full schema applied.
Set DATABASE_URL env var or these tests are skipped.
"""

from __future__ import annotations

import os

import asyncpg
import pytest

from nanobot.auth.repository import AuthRepository

pytestmark = pytest.mark.asyncio

DATABASE_URL = os.environ.get("DATABASE_URL", "")


@pytest.fixture(scope="module")
async def pool():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set — skipping integration tests")
    p = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=3)
    yield p
    await p.close()


@pytest.fixture
async def repo(pool):
    return AuthRepository(pool)


@pytest.fixture
async def user_a(repo):
    user, key = await repo.create_user(
        email=f"alice_{os.urandom(4).hex()}@test.com",
        password="password-alice",
        name="Alice",
    )
    return user, key


@pytest.fixture
async def user_b(repo):
    user, key = await repo.create_user(
        email=f"bob_{os.urandom(4).hex()}@test.com",
        password="password-bob",
        name="Bob",
    )
    return user, key


async def test_api_key_resolves_correct_tenant(repo, user_a, user_b):
    user_a_obj, key_a = user_a
    user_b_obj, key_b = user_b

    resolved_a = await repo.verify_api_key(key_a)
    resolved_b = await repo.verify_api_key(key_b)

    assert resolved_a is not None
    assert resolved_b is not None
    assert resolved_a.tenant_id == user_a_obj.tenant_id
    assert resolved_b.tenant_id == user_b_obj.tenant_id
    assert resolved_a.tenant_id != resolved_b.tenant_id


async def test_revoked_key_returns_none(repo, user_a):
    user_obj, _ = user_a
    raw_key, row = await repo.create_api_key(user_id=user_obj.id, name="to-revoke")
    assert await repo.verify_api_key(raw_key) is not None
    await repo.revoke_api_key(key_id=row.id, user_id=user_obj.id)
    assert await repo.verify_api_key(raw_key) is None


async def test_cannot_revoke_other_users_key(repo, user_a, user_b):
    user_a_obj, _ = user_a
    user_b_obj, _ = user_b
    raw_key, row = await repo.create_api_key(user_id=user_a_obj.id, name="a-key")
    # User B tries to revoke user A's key — must fail
    revoked = await repo.revoke_api_key(key_id=row.id, user_id=user_b_obj.id)
    assert not revoked
    assert await repo.verify_api_key(raw_key) is not None


async def test_channel_link_isolation(repo, user_a, user_b):
    user_a_obj, _ = user_a
    user_b_obj, _ = user_b

    code_a = await repo.create_pairing_code(user_id=user_a_obj.id, channel="telegram")
    ok, detail = await repo.redeem_pairing_code(code=code_a, external_id="tg:111")
    assert ok, detail

    # User A's telegram channel should resolve to A's tenant
    tenant = await repo.resolve_tenant_for_channel("telegram", "tg:111")
    assert tenant == user_a_obj.tenant_id

    # User B's telegram not linked → None
    tenant_b = await repo.resolve_tenant_for_channel("telegram", "tg:999")
    assert tenant_b is None


async def test_pairing_code_cannot_be_redeemed_twice(repo, user_a):
    user_obj, _ = user_a
    code = await repo.create_pairing_code(user_id=user_obj.id, channel="telegram")
    ok1, _ = await repo.redeem_pairing_code(code=code, external_id="tg:222")
    ok2, detail2 = await repo.redeem_pairing_code(code=code, external_id="tg:222")
    assert ok1
    assert not ok2
    assert detail2 == "code_already_redeemed"
