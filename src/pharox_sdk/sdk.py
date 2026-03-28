"""Unified dual-mode PharoxSDK — remote (HTTP) or local (direct toolkit)."""
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from pharox import (
    IAsyncStorage,
    Lease,
    ProxyFilters,
    ProxyPool,
    SelectorStrategy,
)

from .client import PharoxClient
from .exceptions import RemoteError


class PharoxSDK:
    """
    Dual-mode SDK that mirrors the async ProxyManager semantics.

    Use the class methods to create an instance:

    .. code-block:: python

        # Remote mode — talks to a running pharox-service
        sdk = PharoxSDK.remote("http://localhost:8000", api_key="secret")

        # Local mode — uses an IAsyncStorage directly (no HTTP overhead)
        sdk = PharoxSDK.local(storage)

    Both modes expose the same interface:
    ``acquire_proxy``, ``release_proxy``, ``with_lease``.
    """

    def __init__(
        self,
        *,
        client: Optional[PharoxClient] = None,
        storage: Optional[IAsyncStorage] = None,
    ) -> None:
        if (client is None) == (storage is None):
            raise ValueError(
                "Provide exactly one of client= (remote) or storage= (local)."
            )
        self._client = client
        self._storage = storage
        # name → id cache used only in remote mode
        self._pool_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def remote(
        cls, base_url: str, api_key: str, timeout: float = 30.0
    ) -> "PharoxSDK":
        """Create an SDK instance that calls a remote pharox-service."""
        return cls(client=PharoxClient(base_url, api_key, timeout=timeout))

    @classmethod
    def local(cls, storage: IAsyncStorage) -> "PharoxSDK":
        """Create an SDK instance that uses a local storage backend directly."""
        return cls(storage=storage)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()

    async def __aenter__(self) -> "PharoxSDK":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Pool helpers (remote mode)
    # ------------------------------------------------------------------

    async def _resolve_pool_id(self, pool_name: str) -> Optional[str]:
        """Look up pool_id by name, using a local name cache."""
        if pool_name in self._pool_cache:
            return self._pool_cache[pool_name]
        if self._client is None:  # pragma: no cover
            raise RuntimeError("_resolve_pool_id called in local mode")
        pools = await self._client.list_pools()
        self._pool_cache = {p.name: str(p.id) for p in pools}
        return self._pool_cache.get(pool_name)

    # ------------------------------------------------------------------
    # Public API — mirrors ProxyManager async semantics
    # ------------------------------------------------------------------

    async def acquire_proxy(
        self,
        pool_name: str,
        consumer_id: str = "default",
        ttl_seconds: int = 300,
        filters: Optional[ProxyFilters] = None,
        selector: Optional[SelectorStrategy] = None,
    ) -> Optional[Lease]:
        """
        Acquire a proxy lease from the named pool.

        Returns the Lease on success, or None if no proxy is available.
        """
        if self._client is not None:
            return await self._acquire_remote(
                pool_name, consumer_id, ttl_seconds, filters, selector
            )
        return await self._acquire_local(
            pool_name, consumer_id, ttl_seconds, filters, selector
        )

    async def release_proxy(self, lease: Lease) -> None:
        """Release a previously acquired lease."""
        if self._client is not None:
            await self._client.release_lease(str(lease.id))
        elif self._storage is not None:
            await self._storage.release_lease(lease)
        else:  # pragma: no cover
            raise RuntimeError("SDK has neither client nor storage")

    @asynccontextmanager
    async def with_lease(
        self,
        pool_name: str,
        consumer_id: str = "default",
        ttl_seconds: int = 300,
        filters: Optional[ProxyFilters] = None,
        selector: Optional[SelectorStrategy] = None,
    ) -> AsyncIterator[Optional[Lease]]:
        """
        Async context manager that acquires a lease and releases it on exit.

        .. code-block:: python

            async with sdk.with_lease("my-pool") as lease:
                if lease:
                    print(lease.proxy_id)
        """
        lease = await self.acquire_proxy(
            pool_name,
            consumer_id=consumer_id,
            ttl_seconds=ttl_seconds,
            filters=filters,
            selector=selector,
        )
        try:
            yield lease
        finally:
            if lease is not None:
                await self.release_proxy(lease)

    # ------------------------------------------------------------------
    # Admin helpers (remote mode only)
    # ------------------------------------------------------------------

    async def create_pool(
        self, name: str, description: str = ""
    ) -> ProxyPool:
        """Create a pool in the remote service."""
        self._require_remote()
        assert self._client is not None
        pool = await self._client.create_pool(name, description)
        self._pool_cache[pool.name] = str(pool.id)
        return pool

    async def list_pools(self) -> list[ProxyPool]:
        """List all pools from the remote service."""
        self._require_remote()
        assert self._client is not None
        pools = await self._client.list_pools()
        self._pool_cache = {p.name: str(p.id) for p in pools}
        return pools

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_remote(self) -> None:
        if self._client is None:
            raise RuntimeError(
                "This method is only available in remote mode."
            )

    async def _acquire_remote(
        self,
        pool_name: str,
        consumer_id: str,
        ttl_seconds: int,
        filters: Optional[ProxyFilters],
        selector: Optional[SelectorStrategy],
    ) -> Optional[Lease]:
        if self._client is None:  # pragma: no cover
            raise RuntimeError("_acquire_remote called in local mode")
        pool_id = await self._resolve_pool_id(pool_name)
        if pool_id is None:
            from pharox import PoolNotFoundError
            raise PoolNotFoundError(pool_name)
        try:
            return await self._client.acquire_lease(
                pool_id=pool_id,
                consumer_id=consumer_id,
                ttl_seconds=ttl_seconds,
                filters=filters,
                selector=selector,
            )
        except RemoteError as exc:
            if exc.status_code == 404:
                # Pool was in cache but no longer exists — evict and raise
                self._pool_cache.pop(pool_name, None)
                from pharox import PoolNotFoundError
                raise PoolNotFoundError(pool_name) from exc
            raise

    async def _acquire_local(
        self,
        pool_name: str,
        consumer_id: str,
        ttl_seconds: int,
        filters: Optional[ProxyFilters],
        selector: Optional[SelectorStrategy],
    ) -> Optional[Lease]:
        if self._storage is None:  # pragma: no cover
            raise RuntimeError("_acquire_local called in remote mode")
        await self._storage.ensure_consumer(consumer_id)
        await self._storage.cleanup_expired_leases()
        strategy = selector or SelectorStrategy.FIRST_AVAILABLE
        proxy = await self._storage.find_available_proxy(
            pool_name, filters, strategy
        )
        if proxy is None:
            return None
        return await self._storage.create_lease(
            proxy, consumer_id, ttl_seconds
        )
