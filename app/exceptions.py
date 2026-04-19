class CrawlerBaseError(Exception):
    pass


class YouTubeStructureChangedError(CrawlerBaseError):
    """
    Raised when YouTube's JSON response structure changes (missing/moved keys).
    Do NOT retry — retries will fail identically. Alert developer to fix parsing.
    """

    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.context = context or {}

    def __str__(self):
        base = super().__str__()
        if self.context:
            return f"{base} | context={self.context}"
        return base


class CrawlNetworkError(CrawlerBaseError):
    """Transient network error (timeout, connection refused, 429). Safe to retry."""
    pass
