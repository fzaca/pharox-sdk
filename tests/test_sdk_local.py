"""Tests for PharoxSDK in local mode using AsyncInMemoryStorage."""
from pharox import AsyncInMemoryStorage, LeaseStatus
from pharox_sdk import PharoxSDK


async def test_acquire_proxy_returns_lease(seeded_sdk: PharoxSDK) -> None:
    lease = await seeded_sdk.acquire_proxy("test-pool", consumer_id="user1")
    assert lease is not None
    assert lease.status == LeaseStatus.ACTIVE


async def test_acquire_proxy_returns_none_when_no_proxy(
    storage: AsyncInMemoryStorage,
) -> None:
    from pharox.models import ProxyPool

    pool = ProxyPool(name="empty-pool")
    await storage.save_pool(pool)
    sdk = PharoxSDK.local(storage)

    lease = await sdk.acquire_proxy("empty-pool", consumer_id="user1")
    assert lease is None


async def test_acquire_proxy_nonexistent_pool_returns_none(
    local_sdk: PharoxSDK,
) -> None:
    # AsyncInMemoryStorage returns None for unknown pools (no PoolNotFoundError)
    lease = await local_sdk.acquire_proxy("nonexistent", consumer_id="user1")
    assert lease is None


async def test_release_proxy(seeded_sdk: PharoxSDK) -> None:
    lease = await seeded_sdk.acquire_proxy("test-pool", consumer_id="user1")
    assert lease is not None
    await seeded_sdk.release_proxy(lease)

    # second acquire should succeed (proxy freed)
    lease2 = await seeded_sdk.acquire_proxy("test-pool", consumer_id="user2")
    assert lease2 is not None


async def test_with_lease_acquires_and_releases(seeded_sdk: PharoxSDK) -> None:
    async with seeded_sdk.with_lease("test-pool", consumer_id="u1") as lease:
        assert lease is not None
        assert lease.status == LeaseStatus.ACTIVE

    # proxy should be free again
    async with seeded_sdk.with_lease("test-pool", consumer_id="u2") as lease2:
        assert lease2 is not None


async def test_with_lease_yields_none_when_unavailable(
    storage: AsyncInMemoryStorage,
) -> None:
    from pharox.models import ProxyPool

    pool = ProxyPool(name="empty")
    await storage.save_pool(pool)
    sdk = PharoxSDK.local(storage)

    async with sdk.with_lease("empty", consumer_id="u1") as lease:
        assert lease is None


async def test_with_lease_releases_on_exception(seeded_sdk: PharoxSDK) -> None:
    captured_lease = None
    try:
        async with seeded_sdk.with_lease("test-pool", consumer_id="u1") as lease:
            captured_lease = lease
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    # proxy should be available again after the exception
    assert captured_lease is not None
    lease2 = await seeded_sdk.acquire_proxy("test-pool", consumer_id="u2")
    assert lease2 is not None


async def test_local_sdk_as_async_context_manager(
    storage: AsyncInMemoryStorage,
) -> None:
    async with PharoxSDK.local(storage) as sdk:
        assert sdk is not None
