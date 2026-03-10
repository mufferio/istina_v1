class AdapterError(RuntimeError):
    """
    Raised when an adapter fails to perform its job (e.g., RSS fetch fails).

    Use this to keep service-layer code clean:
    services can catch AdapterError without caring about the underlying library (requests/httpx/etc).
    """