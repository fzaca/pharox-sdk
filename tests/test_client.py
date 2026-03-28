"""Tests for PharoxClient (remote HTTP client) using respx to mock httpx."""
import pytest
import respx
from httpx import Response
from pharox_sdk import PharoxClient, RemoteError

BASE = "http://pharox-service"
API_KEY = "test-key"

POOL_ID = "aaaaaaaa-0000-0000-0000-000000000001"
POOL_PAYLOAD = {"id": POOL_ID, "name": "main", "description": ""}
LEASE_ID = "bbbbbbbb-0000-0000-0000-000000000001"
LEASE_PAYLOAD = {
    "id": LEASE_ID,
    "proxy_id": "cccccccc-0000-0000-0000-000000000001",
    "consumer_id": "dddddddd-0000-0000-0000-000000000001",
    "pool_id": POOL_ID,
    "status": "active",
    "acquired_at": "2026-01-01T00:00:00+00:00",
    "expires_at": "2026-01-01T00:05:00+00:00",
}

_mock = respx.mock(assert_all_called=False, using="httpx")


# ------------------------------------------------------------------
# Pool tests
# ------------------------------------------------------------------

async def test_create_pool() -> None:
    async with _mock as mock:
        mock.post(f"{BASE}/v1/pools/").mock(
            return_value=Response(201, json=POOL_PAYLOAD)
        )
        async with PharoxClient(BASE, API_KEY) as client:
            pool = await client.create_pool("main")
    assert pool.name == "main"
    assert str(pool.id) == POOL_ID


async def test_list_pools() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        async with PharoxClient(BASE, API_KEY) as client:
            pools = await client.list_pools()
    assert len(pools) == 1
    assert pools[0].name == "main"


async def test_get_pool() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/{POOL_ID}").mock(
            return_value=Response(200, json=POOL_PAYLOAD)
        )
        async with PharoxClient(BASE, API_KEY) as client:
            pool = await client.get_pool(POOL_ID)
    assert pool.name == "main"


async def test_delete_pool() -> None:
    async with _mock as mock:
        mock.delete(f"{BASE}/v1/pools/{POOL_ID}").mock(
            return_value=Response(204)
        )
        async with PharoxClient(BASE, API_KEY) as client:
            await client.delete_pool(POOL_ID)


# ------------------------------------------------------------------
# Lease tests
# ------------------------------------------------------------------

async def test_acquire_lease() -> None:
    async with _mock as mock:
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(201, json=LEASE_PAYLOAD)
        )
        async with PharoxClient(BASE, API_KEY) as client:
            lease = await client.acquire_lease(
                pool_id=POOL_ID, consumer_id="user1"
            )
    assert lease is not None
    assert str(lease.id) == LEASE_ID


async def test_acquire_lease_no_proxy_available() -> None:
    async with _mock as mock:
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(409, json={"detail": "No proxy available"})
        )
        async with PharoxClient(BASE, API_KEY) as client:
            lease = await client.acquire_lease(
                pool_id=POOL_ID, consumer_id="user1"
            )
    assert lease is None


async def test_acquire_lease_raises_on_unexpected_error() -> None:
    with pytest.raises(RemoteError) as exc_info:
        async with _mock as mock:
            mock.post(f"{BASE}/v1/leases/").mock(
                return_value=Response(
                    500, json={"detail": "Internal Server Error"}
                )
            )
            async with PharoxClient(BASE, API_KEY) as client:
                await client.acquire_lease(
                    pool_id=POOL_ID, consumer_id="user1"
                )
    assert exc_info.value.status_code == 500


async def test_release_lease() -> None:
    released = {**LEASE_PAYLOAD, "status": "released"}
    async with _mock as mock:
        mock.post(f"{BASE}/v1/leases/{LEASE_ID}/release").mock(
            return_value=Response(200, json=released)
        )
        async with PharoxClient(BASE, API_KEY) as client:
            lease = await client.release_lease(LEASE_ID)
    assert lease.status.value == "released"


async def test_get_lease() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/leases/{LEASE_ID}").mock(
            return_value=Response(200, json=LEASE_PAYLOAD)
        )
        async with PharoxClient(BASE, API_KEY) as client:
            lease = await client.get_lease(LEASE_ID)
    assert lease is not None
    assert str(lease.id) == LEASE_ID


async def test_get_lease_not_found() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/leases/nonexistent").mock(
            return_value=Response(404, json={"detail": "not found"})
        )
        async with PharoxClient(BASE, API_KEY) as client:
            lease = await client.get_lease("nonexistent")
    assert lease is None


# ------------------------------------------------------------------
# Auth header
# ------------------------------------------------------------------

async def test_api_key_header_sent() -> None:
    async with _mock as mock:
        route = mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[])
        )
        async with PharoxClient(BASE, API_KEY) as client:
            await client.list_pools()
    assert route.called
    sent_key = route.calls[0].request.headers.get("x-api-key")
    assert sent_key == API_KEY
