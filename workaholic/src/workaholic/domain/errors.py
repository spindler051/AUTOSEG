class WorkaholicError(Exception):
    """User-facing domain error."""

class SchemaError(WorkaholicError):
    pass

class ValidationError(WorkaholicError):
    pass

class ConflictError(WorkaholicError):
    pass

class NotFoundError(WorkaholicError):
    pass
