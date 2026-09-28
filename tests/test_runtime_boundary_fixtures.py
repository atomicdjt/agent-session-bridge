import json
from pathlib import Path

FIXTURE = Path("fixtures/runtime/langgraph-cancel-negative-control.result.json")


def test_langgraph_stream_observation_does_not_claim_checkpoint_durability():
    result = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert result["schema"] == "tfb.runtime-boundary-observation.v1"
    assert result["observation"]["consumer_observed"] is True
    assert result["observation"]["observed_at_utc"] is None
    assert result["cancellation"]["requested_after_observation"] is True
    assert result["cancellation"]["node_returned"] is False
    assert result["checkpoint_readback"]["prior_state_readable"] is True
    assert result["checkpoint_readback"]["contains_partial_stream_output"] is False
    assert result["classification"] == {
        "observation": "OBSERVED",
        "checkpoint_persistence": "NOT_PROVEN",
        "outcome": "UNKNOWN",
    }
    assert "does not reproduce" in result["scope"]
