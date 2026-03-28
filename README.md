# pharox-sdk

Python SDK for the [Pharox](https://github.com/fzaca/pharox) proxy lifecycle management ecosystem.

Works in two interchangeable modes:

- **Remote mode** — HTTP client for a running `pharox-service`
- **Local mode** — direct access to `pharox-toolkit` via `IAsyncStorage` (no service required)

## Installation

```bash
pip install pharox-sdk
```

## Quick start

```python
from pharox_sdk import PharoxSDK

# Remote mode
sdk = PharoxSDK.remote("http://localhost:8000", api_key="my-key")

# Local mode (no service needed)
from pharox import AsyncInMemoryStorage
sdk = PharoxSDK.local(AsyncInMemoryStorage())

# Same interface in both modes
async with sdk.with_lease("my-pool") as lease:
    if lease:
        print(lease.proxy_id)
```

## Links

- [pharox-toolkit](https://github.com/fzaca/pharox) — core library
- [pharox-service](https://github.com/fzaca/pharox-service) — FastAPI service
