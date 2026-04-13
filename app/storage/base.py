from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


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


class StorageBackend(ABC):
    @abstractmethod
    async def init(self) -> None:
        """Initialize the storage backend (create tables, connect, etc.)."""
        ...

    @abstractmethod
    async def save(self, paste: PasteData) -> None: ...

    @abstractmethod
    async def get(self, paste_id: str) -> Optional[PasteData]: ...

    @abstractmethod
    async def increment_views(self, paste_id: str) -> int:
        """Increment view_count and return the new value."""
        ...

    @abstractmethod
    async def delete(self, paste_id: str, delete_token: str) -> bool: ...

    @abstractmethod
    async def force_delete(self, paste_id: str) -> None: ...

    @abstractmethod
    async def ping(self) -> None:
        """Check storage connectivity. Raises if unavailable."""
        ...

    @abstractmethod
    async def close(self) -> None: ...
