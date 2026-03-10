"""Custom exceptions for Worker Router."""


class WorkerTimeout(Exception):
    """Raised when worker exceeds timeout."""
    pass


class RedisError(Exception):
    """Raised when Redis operation fails."""
    pass


class WorkerNotFound(Exception):
    """Raised when worker ID is not found."""
    pass


class TaskNotFound(Exception):
    """Raised when task ID is not found."""
    pass
