class SDKError(Exception):
    """Base error for pharox-sdk."""


class RemoteError(SDKError):
    """Raised when the pharox-service returns an unexpected HTTP error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")
