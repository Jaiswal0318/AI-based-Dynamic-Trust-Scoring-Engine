from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AccessContext(BaseModel):
    """
    Single access request context used as input to the trust engine.

    All risk-related numeric values are normalized to the [0, 1] range,
    where 0 is no risk and 1 is maximum risk / highly suspicious.
    """

    user_id: str = Field(..., description="Unique user identifier")
    device_id: str = Field(..., description="Unique device identifier")
    device_type: str = Field(
        default="Unknown",
        description="Device type (e.g., Laptop, Desktop, Android, iOS, Mobile)",
    )
    location: str = Field(
        default="Unknown",
        description="Geographic location or city name (e.g., Delhi, Mumbai, New York)",
    )
    resource_id: str = Field(..., description="Resource or application being accessed")

    user_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="User-level risk score from identity provider / UEBA",
    )
    device_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Device posture risk (patch level, AV status, jailbreak, etc.)",
    )
    location_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Risk associated with geo / IP / ASN / region",
    )
    network_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Network risk (public Wi‑Fi, TOR, unknown network, etc.)",
    )
    behavior_risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Anomaly score from recent user behavior analytics",
    )

    time_of_day: int = Field(
        ...,
        ge=0,
        le=23,
        description="Hour of day in 24h format (0‑23) at which the request occurs",
    )

    past_incidents: int = Field(
        0,
        ge=0,
        description="Number of historical security incidents tied to this user/device",
    )

    sensitive_resource: bool = Field(
        False,
        description="Whether the target resource is particularly sensitive / privileged",
    )


class TrustScoreResponse(BaseModel):
    """
    Output of the dynamic trust scoring engine.
    """

    trust_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Continuous trust score in [0, 1]; higher is more trusted",
    )
    decision: str = Field(
        ...,
        description="Access decision derived from the trust score (allow / challenge / deny)",
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable explanation of why this decision was taken",
    )


class LoggedDecision(BaseModel):
    """
    Single logged trust decision, used for observability / audit.
    """

    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp when the decision was computed (UTC).",
    )
    user_id: str = Field(..., description="User identifier for this decision.")
    device_id: str = Field(..., description="Device identifier for this decision.")
    resource_id: str = Field(..., description="Resource identifier for this decision.")
    trust_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Trust score produced for this request.",
    )
    decision: str = Field(
        ...,
        description="Final decision: allow / challenge / deny.",
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Reasons that were returned to the caller.",
    )
    context: Optional[AccessContext] = Field(
        None, description="Original context that produced this decision."
    )
    contributions: Optional[Dict[str, float]] = Field(
        None,
        description="Approximate per-feature contribution values used for breakdown charts.",
    )


class DecisionLogResponse(BaseModel):
    """
    Wrapper for returning multiple logged decisions.
    """

    items: List[LoggedDecision] = Field(
        default_factory=list, description="Most recent logged decisions."
    )


class WeightsResponse(BaseModel):
    """
    Current model weight configuration.
    """

    weights: Dict[str, float] = Field(..., description="Feature->weight mapping in [0, 1].")


class WeightsUpdateRequest(BaseModel):
    """
    Update one or more model weights.
    """

    weights: Dict[str, float] = Field(
        ...,
        description="Partial feature->weight updates in [0, 1]. Unknown keys are rejected.",
    )


class MetricsResponse(BaseModel):
    """
    Real-time dashboard metrics computed from recent decisions.
    """

    window_seconds: int = Field(..., ge=1, description="Time window used for metrics.")
    active_sessions: int = Field(..., ge=0, description="Unique active sessions in window.")
    high_risk_users: int = Field(..., ge=0, description="Unique high-risk users in window.")
    average_trust_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Average trust score in window as a percentage (0-100).",
    )
    blocked_attempts: int = Field(
        ...,
        ge=0,
        description="Number of denied attempts in window.",
    )

