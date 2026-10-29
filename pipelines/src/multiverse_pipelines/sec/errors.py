"""Errors of SEC ingestion. Each one says what the operator has to do next."""


class IngestionError(Exception):
    """Base class: the request or the stored file cannot be trusted."""


class PermissionRefusedError(IngestionError):
    """Downloads are not allowed by settings or by the owner's decision in the catalog."""


class HostNotAllowedError(IngestionError):
    """A URL or redirect points outside the official hosts of the source."""


class AccessDeniedError(IngestionError):
    """HTTP 403: the SEC access policy may have been violated. The whole run stops."""


class RetriesExhaustedError(IngestionError):
    """A transient failure (429, 5xx, cut connection, short body) did not clear."""


class HttpStatusError(IngestionError):
    """A status that retrying will not fix, for example 404."""


class TooLargeError(IngestionError):
    """The response is larger than the space left in the disk budget."""


class InvalidPayloadError(IngestionError):
    """The body is not the JSON or ZIP the dataset promises."""


class ArchiveCorruptedError(IngestionError):
    """A stored file no longer matches the checksum in the index."""
