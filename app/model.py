from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Tuple

from .schemas import AccessContext


@dataclass
class TrustPolicyThresholds:
    """
    Simple policy thresholds for converting a probability into a decision.
    """

    allow_min: float = 0.7      # >= allow_min  -> "allow"
    challenge_min: float = 0.4  # >= challenge_min and < allow_min -> "challenge"


class DynamicTrustModel:
    """
    Dynamic trust scoring model using a weighted risk aggregation.

    Pure Python implementation (no numpy) to avoid native-build issues.
    """

    def __init__(self, policy: TrustPolicyThresholds | None = None) -> None:
        self.policy = policy or TrustPolicyThresholds()
        self._feature_order = [
            "user_risk",
            "device_risk",
            "location_risk",
            "network_risk",
            "behavior_risk",
            "time_of_day_norm",
            "past_incidents_norm",
            "sensitive_resource",
        ]
        self._feature_index = {name: idx for idx, name in enumerate(self._feature_order)}
        # Weights reflect relative importance of each risk factor.
        # Higher values increase overall risk and therefore *decrease* trust.
        self._weights = [
            0.35,  # user_risk
            0.25,  # device_risk
            0.15,  # location_risk
            0.10,  # network_risk
            0.15,  # behavior_risk
            0.10,  # time_of_day_norm (off-hours slightly riskier)
            0.15,  # past_incidents_norm
            0.20,  # sensitive_resource
        ]
        # Bias to keep typical risk in a reasonable range.
        self._bias = 0.0

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    def score(self, ctx: AccessContext) -> Tuple[float, str, Dict[str, float]]:
        """
        Compute a trust score and decision for the given context.

        Returns:
            trust_score: value in [0, 1]
            decision: "allow", "challenge", or "deny"
            contributions: per-feature contribution proxy (not exact SHAP, but indicative)
        """
        x = self._encode(ctx)  # list[float]

        # Aggregate risk as weighted sum, then invert it to get trust.
        risk_raw = sum(w * v for w, v in zip(self._weights, x)) + self._bias
        risk = max(0.0, min(1.0, risk_raw))
        trust_score = max(0.0, min(1.0, 1.0 - risk))

        decision = self._to_decision(trust_score)
        contributions = self._approximate_feature_contributions(x, risk)
        return trust_score, decision, contributions

    def get_weights(self) -> Dict[str, float]:
        """
        Return the current weights as a feature->weight mapping.
        """
        return {name: float(self._weights[idx]) for idx, name in enumerate(self._feature_order)}

    def update_weights(self, updates: Mapping[str, float]) -> Dict[str, float]:
        """
        Update one or more feature weights in-place.

        Constraints:
        - Only known feature names are accepted.
        - Each weight must be in [0, 1].
        """
        for name, weight in updates.items():
            if name not in self._feature_index:
                raise ValueError(f"Unknown weight key: {name}")
            if not (0.0 <= float(weight) <= 1.0):
                raise ValueError(f"Weight for {name} must be in [0, 1]")
            self._weights[self._feature_index[name]] = float(weight)
        return self.get_weights()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _encode(self, ctx: AccessContext) -> list[float]:
        """
        Map AccessContext into the feature vector expected by the model.
        """
        time_of_day_norm = ctx.time_of_day / 23.0 if 23.0 != 0 else 0.0
        # cap at 10 for normalization; extra incidents saturate the risk
        past_incidents_norm = min(ctx.past_incidents, 10) / 10.0

        features = {
            "user_risk": ctx.user_risk,
            "device_risk": ctx.device_risk,
            "location_risk": ctx.location_risk,
            "network_risk": ctx.network_risk,
            "behavior_risk": ctx.behavior_risk,
            "time_of_day_norm": time_of_day_norm,
            "past_incidents_norm": past_incidents_norm,
            "sensitive_resource": 1.0 if ctx.sensitive_resource else 0.0,
        }

        return [features[name] for name in self._feature_order]

    def _to_decision(self, trust_score: float) -> str:
        """
        Convert continuous trust score into a discrete decision.
        """
        if trust_score >= self.policy.allow_min:
            return "allow"
        if trust_score >= self.policy.challenge_min:
            return "challenge"
        return "deny"

    def _approximate_feature_contributions(
        self, x: list[float], risk: float
    ) -> Dict[str, float]:
        """
        Provide a simple approximation of per-feature influence using model weights.

        Positive contribution values indicate factors that *increase* risk
        (and therefore reduce trust). Values are not probabilities but
        relative indicators useful for explanations.
        """
        contribs: Dict[str, float] = {}
        for name, value, weight in zip(self._feature_order, x, self._weights):
            contribs[name] = float(weight * value)
        contribs["_total_risk"] = float(risk)
        return contribs

