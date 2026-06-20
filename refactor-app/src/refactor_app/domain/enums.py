from __future__ import annotations

from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    INVALID = "invalid"


class WorkspaceStatus(StrEnum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    ERROR = "error"


class MembershipStatus(StrEnum):
    UNKNOWN = "unknown"
    INVITED = "invited"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    LEFT = "left"
    DISABLED = "disabled"
    BANNED = "banned"
    FAILED = "failed"


class InvitePermission(StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    NO_PERMISSION = "no_permission"
    ERROR = "error"


class SeatStatus(StrEnum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    FULL = "full"
    ERROR = "error"


class TokenStatus(StrEnum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    EXPIRED = "expired"
    REFRESHING = "refreshing"
    REVOKED = "revoked"
    INVALID = "invalid"
    DEAD = "dead"
    ERROR = "error"


class BatchStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActivationStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVATING = "activating"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class BatchItemStatus(StrEnum):
    PENDING = "pending"
    JOINED = "joined"
    TOKEN_GENERATED = "token_generated"
    PUSHED = "pushed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CredentialStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REFRESHING = "refreshing"
    INVALID = "invalid"
    ERROR = "error"


class HeartbeatStatus(StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class PushStatus(StrEnum):
    PENDING = "pending"
    PUSHED = "pushed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ProxyStatus(StrEnum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    BOUND = "bound"
    INVALID = "invalid"
    COOLDOWN = "cooldown"
    RETIRED = "retired"
    ERROR = "error"


class ProxyBindStatus(StrEnum):
    ACTIVE = "active"
    REPAIRING = "repairing"
    DISABLED = "disabled"
    RELEASED = "released"
    ERROR = "error"


class MailLeaseStatus(StrEnum):
    ALLOCATED = "allocated"
    USED = "used"
    RELEASED = "released"
    EXPIRED = "expired"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class EventLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class DownstreamProvider(StrEnum):
    CPA = "cpa"
    SUB2API = "sub2api"
