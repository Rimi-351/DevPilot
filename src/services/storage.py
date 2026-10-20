"""Local filesystem storage service for document uploads."""

import hashlib
from pathlib import Path
from typing import Optional

import aiofiles

from src.core.config import settings
from src.core.exceptions import FileTooLargeError, UnsupportedFileExtensionError


class LocalStorageService:
    """Handles secure asynchronous storage, hashing, and retrieval of uploaded files."""

    def __init__(
        self,
        upload_dir: Optional[str] = None,
        max_size_bytes: Optional[int] = None,
        allowed_extensions: Optional[list[str]] = None,
    ) -> None:
        self.upload_dir = Path(upload_dir or settings.UPLOAD_DIR)
        self.max_size_bytes = max_size_bytes or settings.MAX_UPLOAD_SIZE_BYTES
        self.allowed_extensions = [
            ext.lower() for ext in (allowed_extensions or settings.ALLOWED_EXTENSIONS)
        ]
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> None:
        """Ensure the target upload directory exists with a .gitkeep file."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        gitkeep_path = self.upload_dir / ".gitkeep"
        if not gitkeep_path.exists():
            gitkeep_path.touch()

    def validate_extension(self, filename: str) -> str:
        """Validate filename extension against allowed list."""
        ext = Path(filename).suffix.lower()
        if not ext or ext not in self.allowed_extensions:
            raise UnsupportedFileExtensionError(ext or "(none)", self.allowed_extensions)
        return ext

    def validate_size(self, file_size: int) -> None:
        """Validate that file size does not exceed the maximum allowed threshold."""
        if file_size > self.max_size_bytes:
            raise FileTooLargeError(file_size, self.max_size_bytes)

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Calculate hexadecimal SHA-256 digest of content."""
        return hashlib.sha256(content).hexdigest()

    async def save_file(self, filename: str, content: bytes) -> tuple[str, str, int]:
        """Validate, hash, and persist file binary to disk asynchronously.

        Returns:
            Tuple of (file_path_str, sha256_hash, file_size_bytes)
        """
        ext = self.validate_extension(filename)
        file_size = len(content)
        self.validate_size(file_size)

        content_hash = self.compute_sha256(content)
        destination_filename = f"{content_hash}{ext}"
        destination_path = self.upload_dir / destination_filename

        # Write binary asynchronously
        async with aiofiles.open(destination_path, "wb") as f:
            await f.write(content)

        normalized_path = str(destination_path).replace("\\", "/")
        return normalized_path, content_hash, file_size

    async def read_file(self, file_path: str | Path) -> bytes:
        """Read file binary asynchronously."""
        path = Path(file_path)
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete_file(self, file_path: str | Path) -> bool:
        """Delete file if it exists."""
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
            return True
        return False


StorageService = LocalStorageService


def get_storage_service() -> LocalStorageService:
    """Provide a default storage service instance."""
    return LocalStorageService()

