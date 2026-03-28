# SDK Rules (pharox-sdk)

## Scope

The SDK is the consumer-facing entry point to the pharox ecosystem.
It operates in two modes:

- **Remote mode:** HTTP calls to a running `pharox-service`.
- **Local mode:** Direct use of `pharox-toolkit` via `IAsyncStorage`.

Both modes expose the same async interface (`acquire_proxy`, `release_proxy`,
`with_lease`) so users can swap modes with a one-line change.

## Class Responsibilities

- `PharoxClient` — low-level typed async HTTP client for `pharox-service`.
  Returns toolkit models where possible. No business logic.
- `PharoxSDK` — high-level dual-mode class. Resolves pool names, manages
  lifecycle, exposes `with_lease` context manager. Delegates to client or
  storage backend.

## Dependency Rule

`pharox-sdk` depends on `pharox` (toolkit) as a **production** dependency.
Toolkit models (`Proxy`, `Lease`, `ProxyFilters`, etc.) are reused directly —
never redefined in the SDK.

## Testing

- Use `respx.mock(assert_all_called=False, using="httpx")` for HTTP mocking
  (the default `httpcore` backend has a compatibility issue with the current
  httpx version in this environment).
- Use `AsyncInMemoryStorage` for local mode tests — no real DB or service.
- Run `pytest` + `mypy src/pharox_sdk` before every commit.

## Auth

- `PharoxClient` sends API keys via `X-API-Key` header.
- Never hardcode keys; always inject at runtime.

## Reminders

- Make the GitHub repo **public** before publishing to PyPI.
