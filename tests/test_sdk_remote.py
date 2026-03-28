"""Tests for PharoxSDK in remote mode using respx to mock HTTP calls."""
import pytest
import respx
from httpx import Response
from pharox import LeaseStatus, PoolNotFoundError
from pharox_sdk import PharoxSDK

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
RELEASED_PAYLOAD = {**LEASE_PAYLOAD, "status": "released"}

_mock = respx.mock(assert_all_called=False, using="httpx")


async def test_acquire_proxy_resolves_pool_by_name() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(201, json=LEASE_PAYLOAD)
        )
        async with PharoxSDK.remote(BASE, API_KEY) as sdk:
            lease = await sdk.acquire_proxy("main", consumer_id="user1")
    assert lease is not None
    assert lease.status == LeaseStatus.ACTIVE


async def test_acquire_proxy_uses_cached_pool_id() -> None:
    async with _mock as mock:
        list_route = mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(201, json=LEASE_PAYLOAD)
        )
        async with PharoxSDK.remote(BASE, API_KEY) as sdk:
            await sdk.acquire_proxy("main", consumer_id="u1")
            await sdk.acquire_proxy("main", consumer_id="u2")

    assert list_route.call_count == 1


async def test_acquire_proxy_raises_pool_not_found() -> None:
    with pytest.raises(PoolNotFoundError):
        async with _mock as mock:
            mock.get(f"{BASE}/v1/pools/").mock(
                return_value=Response(200, json=[])
            )
            async with PharoxSDK.remote(BASE, API_KEY) as sdk:
                await sdk.acquire_proxy("nonexistent", consumer_id="u1")


async def test_acquire_proxy_returns_none_when_unavailable() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(409, json={"detail": "No proxy available"})
        )
        async with PharoxSDK.remote(BASE, API_KEY) as sdk:
            lease = await sdk.acquire_proxy("main", consumer_id="u1")
    assert lease is None


async def test_release_proxy() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(201, json=LEASE_PAYLOAD)
        )
        mock.post(f"{BASE}/v1/leases/{LEASE_ID}/release").mock(
            return_value=Response(200, json=RELEASED_PAYLOAD)
        )
        async with PharoxSDK.remote(BASE, API_KEY) as sdk:
            lease = await sdk.acquire_proxy("main", consumer_id="u1")
            assert lease is not None
            await sdk.release_proxy(lease)


async def test_with_lease_acquires_and_releases() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(201, json=LEASE_PAYLOAD)
        )
        release_route = mock.post(
            f"{BASE}/v1/leases/{LEASE_ID}/release"
        ).mock(return_value=Response(200, json=RELEASED_PAYLOAD))

        async with PharoxSDK.remote(BASE, API_KEY) as sdk:
            async with sdk.with_lease("main", consumer_id="u1") as lease:
                assert lease is not None

    assert release_route.called


async def test_with_lease_none_when_no_proxy() -> None:
    async with _mock as mock:
        mock.get(f"{BASE}/v1/pools/").mock(
            return_value=Response(200, json=[POOL_PAYLOAD])
        )
        mock.post(f"{BASE}/v1/leases/").mock(
            return_value=Response(409, json={"detail": "No proxy available"})
        )
        async with PharoxSDK.remote(BASE, API_KEY) as sdk:
            async with sdk.with_lease("main", consumer_id="u1") as lease:
                assert lease is None
