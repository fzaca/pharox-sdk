"""Shared fixtures for pharox-sdk tests."""
import pytest
from pharox import AsyncInMemoryStorage, ProxyProtocol, ProxyStatus
from pharox_sdk import PharoxSDK


@pytest.fixture
async def storage() -> AsyncInMemoryStorage:
    return AsyncInMemoryStorage()


@pytest.fixture
async def local_sdk(storage: AsyncInMemoryStorage) -> PharoxSDK:
    return PharoxSDK.local(storage)


@pytest.fixture
async def seeded_sdk(storage: AsyncInMemoryStorage) -> PharoxSDK:
    """SDK with one pool containing one active proxy."""
    from pharox import Proxy
    from pharox.models import ProxyPool

    pool = ProxyPool(name="test-pool")
    await storage.save_pool(pool)

    proxy = Proxy(
        host="1.2.3.4",
        port=8080,
        protocol=ProxyProtocol.HTTP,
        pool_id=pool.id,
        status=ProxyStatus.ACTIVE,
    )
    await storage.save_proxy(proxy)

    return PharoxSDK.local(storage)
