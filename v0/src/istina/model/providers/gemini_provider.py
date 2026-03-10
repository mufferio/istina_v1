"""
Gemini provider implementation.

Purpose:
- Real AI-backed analysis using Google Gemini API.

Responsibilities:
- Build prompts for:
  - claim extraction + fact-check verdict scaffolding
  - rhetorical bias detection and structured scoring
- Call Gemini SDK/HTTP
- Parse/validate the model response
- Normalize output into BiasScore
- Enforce rate limiting + retries (use utils/rate_limiter.py and utils/retry.py)

Important:
- Keep prompts versioned and test parsing heavily.
- Always handle malformed outputs safely (fallback to “insufficient evidence”).
- Never leak API keys into logs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.base_provider import BaseProvider
from istina.utils.rate_limiter import RateLimiter, maybe_acquire
from istina.utils.retry import retry


VALID_LABELS = {"left", "center", "right", "unknown"}
VALID_VERDICTS = {"true", "false", "mixed", "unverified", "insufficient evidence"}


def _clamp01(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _extract_model_text(gemini_payload: Dict[str, Any]) -> str:
    """
    Pull the main text from a Gemini generateContent response.
    Robust against missing fields.
    """
    try:
        candidates = gemini_payload.get("candidates") or []
        if not candidates:
            return ""
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            return ""
        # Gemini often returns [{"text": "..."}]
        text = parts[0].get("text")
        return text if isinstance(text, str) else ""
    except Exception:
        return ""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"(\{.*\})", re.DOTALL)


def _safe_json_loads_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Try hard to parse a JSON object from model text:
    - handles ```json fenced blocks
    - handles extra prose before/after JSON
    - returns None if can't parse
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # 1) Try direct parse
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # 2) Try fenced JSON
    m = _JSON_FENCE_RE.search(text)
    if m:
        snippet = m.group(1)
        try:
            obj = json.loads(snippet)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    # 3) Try largest {...} block
    m = _JSON_OBJ_RE.search(text)
    if m:
        snippet = m.group(1).strip()
        # common trailing commas fix (minimal)
        snippet = re.sub(r",\s*}", "}", snippet)
        snippet = re.sub(r",\s*]", "]", snippet)
        try:
            obj = json.loads(snippet)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    return None


def _normalize_bias_obj(obj: Optional[Dict[str, Any]]) -> Tuple[str, List[str], float]:
    """
    Returns: (overall_bias_label, rhetorical_flags, confidence)
    Always safe.
    """
    if not obj:
        return ("unknown", [], 0.0)

    label = str(obj.get("overall_bias_label", "unknown")).strip().lower()
    if label not in VALID_LABELS:
        label = "unknown"

    flags = obj.get("rhetorical_flags", [])
    if not isinstance(flags, list):
        flags = []
    flags = [str(x).strip() for x in flags if isinstance(x, (str, int, float)) and str(x).strip()]
    # de-dupe while preserving order
    seen = set()
    deduped = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            deduped.append(f)

    conf = _clamp01(obj.get("confidence", 0.0), default=0.0)
    return (label, deduped, conf)


def _fallback_claim_check(reason: str = "insufficient evidence") -> Dict[str, Any]:
    return {
        "claim": "",
        "verdict": "insufficient evidence",
        "confidence": 0.0,
        "evidence": [reason],
    }


def _normalize_claims_obj(obj: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalizes claim_checks to a list of dicts:
      {claim:str, verdict:str, confidence:float, evidence:list[str]}
    If malformed, returns a single fallback entry (per issue).
    """
    if not obj:
        return [_fallback_claim_check("insufficient evidence")]

    claims = obj.get("claim_checks", None)
    if not isinstance(claims, list) or len(claims) == 0:
        return [_fallback_claim_check("insufficient evidence")]

    normalized: List[Dict[str, Any]] = []

    for item in claims:
        if not isinstance(item, dict):
            continue

        claim = item.get("claim", "")
        claim = claim if isinstance(claim, str) else str(claim)

        verdict = str(item.get("verdict", "unverified")).strip().lower()
        if verdict not in VALID_VERDICTS:
            verdict = "unverified"

        conf = _clamp01(item.get("confidence", 0.0), default=0.0)

        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        evidence = [str(e).strip() for e in evidence if str(e).strip()]

        # If it's basically empty/broken, turn into required fallback
        if not claim.strip() and verdict in {"unverified", "insufficient evidence"} and conf == 0.0 and not evidence:
            normalized.append(_fallback_claim_check("insufficient evidence"))
        else:
            normalized.append(
                {
                    "claim": claim.strip(),
                    "verdict": verdict,
                    "confidence": conf,
                    "evidence": evidence,
                }
            )

    if not normalized:
        return [_fallback_claim_check("insufficient evidence")]

    return normalized


def parse_and_normalize_gemini(
    bias_call: Dict[str, Any],
    claims_call: Dict[str, Any],
) -> Tuple[str, List[str], float, List[Dict[str, Any]]]:
    """
    Converts raw Gemini HTTP payloads into normalized fields for BiasScore.

    Returns:
      overall_label, rhetorical_flags, overall_confidence, claim_checks
    """
    bias_text = _extract_model_text(bias_call)
    claims_text = _extract_model_text(claims_call)

    bias_obj = _safe_json_loads_from_text(bias_text)
    claims_obj = _safe_json_loads_from_text(claims_text)

    label, flags, conf = _normalize_bias_obj(bias_obj)
    claim_checks = _normalize_claims_obj(claims_obj)

    return (label, flags, conf, claim_checks)




class ProviderError(RuntimeError):
    """Raised when the provider call fails (network/status/etc.)."""


def _get_setting(settings: Any, key: str, default: Any = None) -> Any:
    if settings is None:
        return default
    if isinstance(settings, dict):
        return settings.get(key, default)
    if hasattr(settings, key):
        return getattr(settings, key)
    get = getattr(settings, "get", None)
    if callable(get):
        return get(key, default)
    return default


def build_bias_prompt(article: Article) -> str:
    """
    Prompt template: bias detection + rhetorical flags.

    Output requirements (we'll parse later):
      - overall_bias_label: left|center|right|unknown
      - rhetorical_flags: list[str]
      - confidence: float 0..1
      - short justification
    """
    title = getattr(article, "title", "") or ""
    summary = getattr(article, "summary", "") or ""
    source = getattr(article, "source", "") or ""
    url = getattr(article, "url", "") or ""

    return f"""
You are Istina, an expert media bias analyst. Analyze the following news article for political bias and rhetorical manipulation techniques.

Article to analyze:
Source: {source}
Title: {title}
Summary: {summary}
URL: {url}

Analysis framework:

1. OVERALL BIAS CLASSIFICATION:
   - Determine if the article leans left, center, right, or unknown
   - Base assessment on:
     * Word choice and framing
     * Selection and omission of facts
     * Sources cited or ignored
     * Contextual emphasis

2. RHETORICAL FLAGS DETECTION:
   Identify any of these manipulation techniques present:
   - loaded_language: Emotionally charged words intended to influence
   - cherry_picking: Selective presentation of facts
   - ad_hominem: Attacking person rather than argument
   - appeal_to_fear: Using fear to influence opinion
   - strawman: Misrepresenting opposing viewpoint
   - whataboutism: Deflecting by pointing to other issues
   - false_dilemma: Presenting only two options when more exist
   - us_vs_them: Creating artificial divisions
   - assertion_without_evidence: Making claims without support
   - sensationalism: Exaggerating for dramatic effect

3. CONFIDENCE ASSESSMENT:
   - Rate your confidence in this analysis from 0.0 (uncertain) to 1.0 (very confident)
   - Consider article length, clarity, and available context

Return ONLY a valid JSON object with this exact structure:
{{
  "overall_bias_label": "left|center|right|unknown",
  "rhetorical_flags": ["flag1", "flag2"],
  "confidence": 0.0,
  "justification": "Brief explanation of your assessment"
}}
""".strip()


def build_claims_prompt(article: Article) -> str:
    """
    Prompt template: claim extraction + verdict scaffolding.

    Output requirements (we'll parse later):
      - claim_checks: list of objects with {claim, verdict, confidence, evidence}
    """
    title = getattr(article, "title", "") or ""
    summary = getattr(article, "summary", "") or ""
    source = getattr(article, "source", "") or ""
    url = getattr(article, "url", "") or ""

    return f"""
You are Istina, a fact-checking and claim verification expert. Extract and assess factual claims from the following news article.

Article to analyze:
Source: {source}
Title: {title}
Summary: {summary}
URL: {url}

Task: Extract up to 5 concrete, verifiable factual claims and provide preliminary assessment.

Claim extraction criteria:
- Focus on specific, verifiable assertions:
  * Numerical data (statistics, amounts, dates, quantities)
  * Attribution claims ("X said Y", "According to Z")
  * Causal relationships ("A caused B")
  * Event descriptions ("X happened on Y date")
  * Timeline assertions ("before/after X")
- Exclude opinions, predictions, or subjective statements
- If summary lacks detail, extract fewer claims rather than speculating

Verdict categories:
- "true": Claim appears accurate based on available information
- "false": Claim appears inaccurate or misleading
- "mixed": Claim is partially true/false or needs important context
- "unverified": Cannot assess without additional evidence (default for this phase)

Confidence scale:
- 0.0-0.3: Low confidence, substantial uncertainty
- 0.4-0.6: Moderate confidence, some uncertainty
- 0.7-1.0: High confidence, minimal uncertainty

Return ONLY a valid JSON object with this exact structure:
{{
  "claim_checks": [
    {{
      "claim": "Specific factual claim extracted from article",
      "verdict": "unverified",
      "confidence": 0.0,
      "evidence": ["Supporting information if available", "Context or caveats"]
    }}
  ]
}}
""".strip()


VALID_LABELS = {"left", "center", "right", "unknown"}
VALID_VERDICTS = {"true", "false", "mixed", "unverified", "insufficient evidence"}


def _clamp01(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _extract_model_text(gemini_payload: Dict[str, Any]) -> str:
    """
    Pull the main text from a Gemini generateContent response.
    Robust against missing fields.
    """
    try:
        candidates = gemini_payload.get("candidates") or []
        if not candidates:
            return ""
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            return ""
        # Gemini often returns [{"text": "..."}]
        text = parts[0].get("text")
        return text if isinstance(text, str) else ""
    except Exception:
        return ""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJ_RE = re.compile(r"(\{.*\})", re.DOTALL)


def _safe_json_loads_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Try hard to parse a JSON object from model text:
    - handles ```json fenced blocks
    - handles extra prose before/after JSON
    - returns None if can't parse
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()

    # 1) Try direct parse
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # 2) Try fenced JSON
    m = _JSON_FENCE_RE.search(text)
    if m:
        snippet = m.group(1)
        try:
            obj = json.loads(snippet)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    # 3) Try largest {...} block
    m = _JSON_OBJ_RE.search(text)
    if m:
        snippet = m.group(1).strip()
        # common trailing commas fix (minimal)
        snippet = re.sub(r",\s*}", "}", snippet)
        snippet = re.sub(r",\s*]", "]", snippet)
        try:
            obj = json.loads(snippet)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    return None


def _normalize_bias_obj(obj: Optional[Dict[str, Any]]) -> Tuple[str, List[str], float]:
    """
    Returns: (overall_bias_label, rhetorical_flags, confidence)
    Always safe.
    """
    if not obj:
        return ("unknown", [], 0.0)

    label = str(obj.get("overall_bias_label", "unknown")).strip().lower()
    if label not in VALID_LABELS:
        label = "unknown"

    flags = obj.get("rhetorical_flags", [])
    if not isinstance(flags, list):
        flags = []
    flags = [str(x).strip() for x in flags if isinstance(x, (str, int, float)) and str(x).strip()]
    # de-dupe while preserving order
    seen = set()
    deduped = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            deduped.append(f)

    conf = _clamp01(obj.get("confidence", 0.0), default=0.0)
    return (label, deduped, conf)


def _fallback_claim_check(reason: str = "insufficient evidence") -> Dict[str, Any]:
    return {
        "claim": "",
        "verdict": "insufficient evidence",
        "confidence": 0.0,
        "evidence": [reason],
    }


def _normalize_claims_obj(obj: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalizes claim_checks to a list of dicts:
      {claim:str, verdict:str, confidence:float, evidence:list[str]}
    If malformed, returns a single fallback entry (per issue).
    """
    if not obj:
        return [_fallback_claim_check("insufficient evidence")]

    claims = obj.get("claim_checks", None)
    if not isinstance(claims, list) or len(claims) == 0:
        return [_fallback_claim_check("insufficient evidence")]

    normalized: List[Dict[str, Any]] = []

    for item in claims:
        if not isinstance(item, dict):
            continue

        claim = item.get("claim", "")
        claim = claim if isinstance(claim, str) else str(claim)

        verdict = str(item.get("verdict", "unverified")).strip().lower()
        if verdict not in VALID_VERDICTS:
            verdict = "unverified"

        conf = _clamp01(item.get("confidence", 0.0), default=0.0)

        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        evidence = [str(e).strip() for e in evidence if str(e).strip()]

        # If it's basically empty/broken, turn into required fallback
        if not claim.strip() and verdict in {"unverified", "insufficient evidence"} and conf == 0.0 and not evidence:
            normalized.append(_fallback_claim_check("insufficient evidence"))
        else:
            normalized.append(
                {
                    "claim": claim.strip(),
                    "verdict": verdict,
                    "confidence": conf,
                    "evidence": evidence,
                }
            )

    if not normalized:
        return [_fallback_claim_check("insufficient evidence")]

    return normalized


def parse_and_normalize_gemini(
    bias_call: Dict[str, Any],
    claims_call: Dict[str, Any],
) -> Tuple[str, List[str], float, List[Dict[str, Any]]]:
    """
    Converts raw Gemini HTTP payloads into normalized fields for BiasScore.

    Returns:
      overall_label, rhetorical_flags, overall_confidence, claim_checks
    """
    bias_text = _extract_model_text(bias_call)
    claims_text = _extract_model_text(claims_call)

    bias_obj = _safe_json_loads_from_text(bias_text)
    claims_obj = _safe_json_loads_from_text(claims_text)

    label, flags, conf = _normalize_bias_obj(bias_obj)
    claim_checks = _normalize_claims_obj(claims_obj)

    return (label, flags, conf, claim_checks)


@dataclass
class GeminiProvider(BaseProvider):
    """
    Gemini provider scaffold.

    v0 behavior:
      - calls Gemini generateContent with prompts
      - does NOT require perfect parsing yet (stores raw_response)
      - returns a normalized BiasScore with conservative defaults (unknown/empty)
    """

    api_key: str = field(repr=False)
    model: str = "gemini-2.5-flash"
    timeout_seconds: float = 10.0
    limiter: Optional[RateLimiter] = None

    # For testability: allow injection of a request function
    _post: Optional[Callable[..., httpx.Response]] = field(default=None, repr=False)

    @classmethod
    def from_settings(cls, settings: Any, *, limiter: Optional[RateLimiter] = None) -> "GeminiProvider":
        api_key = _get_setting(settings, "gemini_api_key", None)
        model = _get_setting(settings, "gemini_model", "gemini-2.5-flash")
        if not api_key:
            raise ValueError("gemini_api_key is required to instantiate GeminiProvider")
        return cls(api_key=str(api_key), model=str(model), limiter=limiter)

    def analyze_article(self, article: Article) -> BiasScore:
        aid = getattr(article, "id", None)
        if not aid:
            raise ValueError("Article missing id")

        # Build prompts
        bias_prompt = build_bias_prompt(article)
        claims_prompt = build_claims_prompt(article)

        # Call provider and parse responses with robust error handling
        bias_raw = self._call_gemini(bias_prompt)
        claims_raw = self._call_gemini(claims_prompt)

        # Store raw_response for debugging/auditing; NEVER include api key.
        raw_response: Dict[str, Any] = {
            "bias_call": bias_raw,
            "claims_call": claims_raw,
            "model": self.model,
        }

        # Parse and normalize Gemini responses with robust error handling
        overall, rhetorical_flags, confidence, claim_checks = parse_and_normalize_gemini(
            bias_raw, claims_raw
        )


        # Timestamp should reflect analysis time (not deterministic like MockProvider)
        timestamp = datetime.now(timezone.utc)

        return BiasScore(
            article_id=aid,
            provider="gemini",
            overall_bias_label=overall,
            rhetorical_bias=rhetorical_flags,
            claim_checks=claim_checks,
            confidence=confidence,
            timestamp=timestamp,
            raw_response=raw_response,
        )

    def _call_gemini(self, prompt: str) -> Dict[str, Any]:
        """
        Wrapper for Gemini call.
        - Applies optional rate limiting + retry for transient network issues.
        - Does NOT log secrets.
        - Returns parsed JSON response payload (dict) from HTTP call (raw).
        """
        maybe_acquire(self.limiter)

        def _do_call() -> Dict[str, Any]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            params = {"key": self.api_key}  # Do not log this.
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
            }
            
            post = self._post
            if post is None:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(url, params=params, json=payload)
            else:
                resp = post(url, params=params, json=payload, timeout=self.timeout_seconds)

            if resp.status_code != 200:
                # Never include URL with key, API key, or response body in the message.
                raise ProviderError(f"Gemini API returned status {resp.status_code}")

            try:
                response_data = resp.json()
                # Security: remove API keys found in response
                if isinstance(response_data, dict) and "key" in str(response_data):
                    # Remove any potential API key leaks in response
                    response_data = {k: v for k, v in response_data.items() 
                                   if k not in ("key", "api_key", "apiKey")}
                return response_data
            except Exception as e:
                raise ProviderError(f"Gemini returned invalid JSON response") from e

        # Retry only on network-ish exceptions + ProviderError
        return retry(
            _do_call,
            exceptions=(httpx.TimeoutException, httpx.NetworkError, ProviderError),
            max_attempts=3,
            base_delay=0.5,
            backoff_factor=2.0,
        )