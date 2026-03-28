"""Async HTTP client for pharox-service (remote mode low-level API)."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx
from pharox import (
    Lease,
    LeaseStatus,
    ProxyFilters,
    ProxyPool,
    ProxyProtocol,
    ProxyStatus,
    SelectorStrategy,
)

from .exceptions import RemoteError


def _parse_pool(data: dict[str, Any]) -> ProxyPool:
    return ProxyPool(
        id=UUID(data["id"]),
        name=data["name"],
        description=data.get("description", ""),
    )


def _parse_lease(data: dict[str, Any]) -> Lease:
    pool_id_str = data.get("pool_id") or ""
    return Lease(
        id=UUID(data["id"]),
        proxy_id=UUID(data["proxy_id"]),
        consumer_id=UUID(data["consumer_id"]),
        pool_id=UUID(pool_id_str) if pool_id_str else None,
        status=LeaseStatus(data["status"]),
        acquired_at=datetime.fromisoformat(data["acquired_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]),
    )


class PharoxClient:
    """
    Low-level async HTTP client for pharox-service.

    Use as an async context manager or call ``aclose()`` when done.

    Parameters
    ----------
    base_url:
        Base URL of pharox-service (e.g. ``"http://localhost:8000"``).
    api_key:
        API key for authentication.
    timeout:
        Request timeout in seconds. Defaults to 30.
    """

    def __init__(
        self, base_url: str, api_key: str, timeout: float = 30.0
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "PharoxClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RemoteError(response.status_code, str(detail))

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request, wrapping network errors as RemoteError."""
        try:
            return await self._http.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise RemoteError(0, f"Request timed out: {exc}") from exc
        except httpx.NetworkError as exc:
            raise RemoteError(0, f"Network error: {exc}") from exc

    # ------------------------------------------------------------------
    # Pools
    # ------------------------------------------------------------------

    async def create_pool(
        self, name: str, description: str = ""
    ) -> ProxyPool:
        r = await self._request(
            "POST", "/v1/pools/", json={"name": name, "description": description}
        )
        self._raise_for_status(r)
        return _parse_pool(r.json())

    async def list_pools(self) -> list[ProxyPool]:
        r = await self._request("GET", "/v1/pools/")
        self._raise_for_status(r)
        return [_parse_pool(p) for p in r.json()]

    async def get_pool(self, pool_id: str) -> ProxyPool:
        r = await self._request("GET", f"/v1/pools/{pool_id}")
        self._raise_for_status(r)
        return _parse_pool(r.json())

    async def delete_pool(self, pool_id: str) -> None:
        r = await self._request("DELETE", f"/v1/pools/{pool_id}")
        self._raise_for_status(r)

    # ------------------------------------------------------------------
    # Proxies
    # ------------------------------------------------------------------

    async def add_proxy(
        self,
        pool_id: str,
        host: str,
        port: int,
        protocol: ProxyProtocol = ProxyProtocol.HTTP,
        username: Optional[str] = None,
        password: Optional[str] = None,
        country: Optional[str] = None,
        city: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "host": host,
            "port": port,
            "protocol": protocol.value,
        }
        if username:
            payload["username"] = username
        if password:
            payload["password"] = password
        if country:
            payload["country"] = country
        if city:
            payload["city"] = city
        if latitude is not None:
            payload["latitude"] = latitude
        if longitude is not None:
            payload["longitude"] = longitude

        r = await self._request(
            "POST", f"/v1/pools/{pool_id}/proxies/", json=payload
        )
        self._raise_for_status(r)
        return r.json()  # type: ignore[no-any-return]

    async def list_proxies(self, pool_id: str) -> list[dict[str, Any]]:
        r = await self._request("GET", f"/v1/pools/{pool_id}/proxies/")
        self._raise_for_status(r)
        return r.json()  # type: ignore[no-any-return]

    async def update_proxy_status(
        self, pool_id: str, proxy_id: str, status: ProxyStatus
    ) -> dict[str, Any]:
        r = await self._request(
            "PATCH",
            f"/v1/pools/{pool_id}/proxies/{proxy_id}",
            json={"status": status.value},
        )
        self._raise_for_status(r)
        return r.json()  # type: ignore[no-any-return]

    async def delete_proxy(self, pool_id: str, proxy_id: str) -> None:
        r = await self._request(
            "DELETE", f"/v1/pools/{pool_id}/proxies/{proxy_id}"
        )
        self._raise_for_status(r)

    # ------------------------------------------------------------------
    # Leases
    # ------------------------------------------------------------------

    async def acquire_lease(
        self,
        pool_id: str,
        consumer_id: str,
        ttl_seconds: int = 300,
        filters: Optional[ProxyFilters] = None,
        selector: Optional[SelectorStrategy] = None,
    ) -> Optional[Lease]:
        """
        Returns the acquired Lease or None if no proxy is available (HTTP 409).
        Raises RemoteError for any other non-2xx response.
        """
        payload: dict[str, Any] = {
            "pool_id": pool_id,
            "consumer_id": consumer_id,
            "ttl_seconds": ttl_seconds,
            "strategy": (
                selector.value
                if selector
                else SelectorStrategy.FIRST_AVAILABLE.value
            ),
        }
        if filters:
            payload["filters"] = filters.model_dump(exclude_none=True)

        r = await self._request("POST", "/v1/leases/", json=payload)
        if r.status_code == 409:
            return None
        self._raise_for_status(r)
        return _parse_lease(r.json())

    async def get_lease(self, lease_id: str) -> Optional[Lease]:
        r = await self._request("GET", f"/v1/leases/{lease_id}")
        if r.status_code == 404:
            return None
        self._raise_for_status(r)
        return _parse_lease(r.json())

    async def release_lease(self, lease_id: str) -> Lease:
        r = await self._request("POST", f"/v1/leases/{lease_id}/release", json={})
        self._raise_for_status(r)
        return _parse_lease(r.json())
