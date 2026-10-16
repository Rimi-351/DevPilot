"""Custom application exceptions and error handling utilities."""

from typing import Any, Optional


class DevPilotException(Exception):
    """Base exception for all DevPilot domain errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EntityNotFoundError(DevPilotException):
    """Raised when an entity is not found in the database."""

    def __init__(self, entity_name: str, entity_id: Any):
        super().__init__(
            message=f"{entity_name} with identifier '{entity_id}' was not found.",
            details={"entity_name": entity_name, "entity_id": str(entity_id)},
        )


class EntityConflictError(DevPilotException):
    """Raised when an entity conflict occurs (e.g. duplicate key)."""

    def __init__(self, entity_name: str, conflict_reason: str):
        super().__init__(
            message=f"{entity_name} conflict: {conflict_reason}",
            details={"entity_name": entity_name, "conflict_reason": conflict_reason},
        )
