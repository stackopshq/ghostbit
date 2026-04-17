import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Tuple


@dataclass
class PasteData:
    id: str
    content: str            # base64 AES-256-GCM ciphertext (includes auth tag)
    nonce: str              # base64 12-byte GCM nonce
    kdf_salt: Optional[str] # base64 16-byte PBKDF2 salt — only for password-protected pastes (client-side key derivation)
    language: Optional[str]
    created_at: int
    expires_at: Optional[int]
    burn: bool
    has_password: bool
    delete_token_hash: str
    max_views: Optional[int] = None  # None = unlimited
    view_count: int = 0
    webhook_url: Optional[str] = None

    def is_expired(self, now: Optional[int] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else int(time.time())) > self.expires_at


class StorageBackend(ABC):
    @abstractmethod
    async def init(self) -> None:
        """Initialize the storage backend (create tables, connect, etc.)."""
        ...

    @abstractmethod
    async def save(self, paste: PasteData) -> bool:
        """Persist paste atomically. Returns False if the ID is already taken."""
        ...

    @abstractmethod
    async def get(self, paste_id: str) -> Optional[PasteData]: ...

    @abstractmethod
    async def increment_and_check_burn(
        self, paste_id: str
    ) -> Tuple[Optional[int], bool]:
        """Atomically increment view_count, then burn if burn=True or
        max_views reached.

        Returns (new_view_count, burned). Returns (None, False) if the paste
        no longer exists (deleted between caller's get() and this call).
        """
        ...

    @abstractmethod
    async def delete(self, paste_id: str, delete_token: str) -> bool: ...

    @abstractmethod
    async def force_delete(self, paste_id: str) -> None: ...

    @abstractmethod
    def iter_all(self) -> AsyncIterator[PasteData]:
        """Yield every stored paste (order unspecified). Used by the admin
        export command. Implementations are expected to stream rather than
        materialize the whole table in memory."""
        ...

    @abstractmethod
    async def ping(self) -> None:
        """Check storage connectivity. Raises if unavailable."""
        ...

    @abstractmethod
    async def close(self) -> None: ...
