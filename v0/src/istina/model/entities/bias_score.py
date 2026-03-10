"""
BiasScore (analysis result) entity.

Represents:
- Structured output of the AI analysis layer for an Article.

Typical fields:
- article_id
- provider_name, provider_model (optional)
- overall_bias_label (e.g., left/center/right/unknown) OR multi-axis scores
- rhetorical_bias: list of flags (loaded language, framing, etc.)
- claim_checks: list of extracted claims with:
  - claim_text
  - verdict: supported/contradicted/insufficient
  - evidence_citations: urls/snippets/quotes references
- confidence and timestamps

Rules:
- Must be serializable.
- Keep it provider-agnostic: store normalized fields, not raw provider format.
- Optionally store raw_response for auditing/debugging.
"""

from dataclasses import dataclass
from typing import List, Dict, Any
from datetime import datetime


VALID_PROVIDERS = {"mock", "gemini", "gpt-3.5", "gpt-4"}
VALID_LABELS = ("left", "center", "right", "unknown")

@dataclass
class BiasScore:
    article_id: str
    provider: str
    overall_bias_label: str
    rhetorical_bias: List[str]
    claim_checks: List[Dict[str, Any]]
    confidence: float
    timestamp: datetime
    raw_response: Dict[str, Any] = None

    def __post_init__(self):
        if not isinstance(self.article_id, str) or not self.article_id:
            raise ValueError("article_id must be a non-empty string")
        if self.provider not in VALID_PROVIDERS:
            raise ValueError(f"Invalid provider: {self.provider}")
        if self.overall_bias_label not in VALID_LABELS:
            raise ValueError(f"Invalid bias label: {self.overall_bias_label}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        if not isinstance(self.rhetorical_bias, list) or not all(isinstance(x, str) for x in self.rhetorical_bias):
            raise ValueError("rhetorical_bias must be a list of strings")
        if not isinstance(self.claim_checks, list) or not all(isinstance(x, dict) for x in self.claim_checks):
            raise ValueError("claim_checks must be a list of dicts")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime object")
        if self.raw_response is not None and not isinstance(self.raw_response, dict):
            raise ValueError("raw_response must be a dict if provided")
        

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "provider": self.provider,
            "overall_bias_label": self.overall_bias_label,
            "rhetorical_bias": self.rhetorical_bias,
            "claim_checks": self.claim_checks,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "raw_response": self.raw_response,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BiasScore":
        required = [
            "article_id",
            "provider",
            "overall_bias_label",
            "confidence",
            "timestamp",
        ]
        for r in required:
            if r not in d:
                raise ValueError(f"Missing required field: {r}")
        try:
            timestamp = datetime.fromisoformat(d["timestamp"])
        except KeyError:
            raise ValueError("Missing required field: timestamp")
        except Exception as e:
            raise ValueError(f"Invalid timestamp format: {e}")
        return cls(
            article_id=d["article_id"],
            provider=d["provider"],
            overall_bias_label=d["overall_bias_label"],
            rhetorical_bias=d.get("rhetorical_bias", []),
            claim_checks=d.get("claim_checks", []),
            confidence=d["confidence"],
            timestamp=timestamp,
            raw_response=d.get("raw_response"),
        )


