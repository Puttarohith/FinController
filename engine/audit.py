from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class AuditEntry:
    payment_id: str
    decision: str
    confidence: float
    signals_used: str
    reason: str
    method: str
    timestamp: str

    @classmethod
    def create(
        cls,
        payment_id: str,
        decision: str,
        confidence: float,
        signals_used: str,
        reason: str,
        method: str,
    ) -> "AuditEntry":
        return cls(
            payment_id=payment_id,
            decision=decision,
            confidence=round(float(confidence), 4),
            signals_used=signals_used,
            reason=reason,
            method=method,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict:
        return asdict(self)

