import pytest
from datetime import datetime
from istina.model.entities.bias_score import BiasScore


def make_valid_bias_score(**overrides):
    base = dict(
        article_id="abc123",
        provider="mock",
        overall_bias_label="center",
        rhetorical_bias=["framing", "loaded language"],
        claim_checks=[{"claim_text": "foo", "verdict": "supported", "evidence_citations": []}],
        confidence=0.85,
        timestamp=datetime(2026, 2, 19, 12, 0, 0),
        raw_response={"raw": True},
    )
    base.update(overrides)
    return BiasScore(**base)

def test_valid_bias_score_roundtrip():
    score = make_valid_bias_score()
    d = score.to_dict()
    score2 = BiasScore.from_dict(d)
    assert score.article_id == score2.article_id
    assert score.provider == score2.provider
    assert score.overall_bias_label == score2.overall_bias_label
    assert score.rhetorical_bias == score2.rhetorical_bias
    assert score.claim_checks == score2.claim_checks
    assert score.confidence == score2.confidence
    assert score.timestamp == score2.timestamp
    assert score.raw_response == score2.raw_response

def test_missing_required_fields():
    d = make_valid_bias_score().to_dict()
    for field in ["article_id", "provider", "overall_bias_label", "confidence", "timestamp"]:
        d2 = d.copy()
        d2.pop(field)
        with pytest.raises(ValueError):
            BiasScore.from_dict(d2)

def test_invalid_provider():
    with pytest.raises(ValueError):
        make_valid_bias_score(provider="not-a-provider")

def test_invalid_bias_label():
    with pytest.raises(ValueError):
        make_valid_bias_score(overall_bias_label="not-a-label")

def test_invalid_confidence():
    with pytest.raises(ValueError):
        make_valid_bias_score(confidence=1.5)
    with pytest.raises(ValueError):
        make_valid_bias_score(confidence=-0.1)

def test_invalid_rhetorical_bias_type():
    with pytest.raises(ValueError):
        make_valid_bias_score(rhetorical_bias="notalist")
    with pytest.raises(ValueError):
        make_valid_bias_score(rhetorical_bias=[123, "ok"])

def test_invalid_claim_checks_type():
    with pytest.raises(ValueError):
        make_valid_bias_score(claim_checks="notalist")
    with pytest.raises(ValueError):
        make_valid_bias_score(claim_checks=["notadict"])

def test_invalid_timestamp_type():
    with pytest.raises(ValueError):
        make_valid_bias_score(timestamp="2026-02-19T12:00:00")

def test_invalid_raw_response_type():
    with pytest.raises(ValueError):
        make_valid_bias_score(raw_response=[1,2,3])
