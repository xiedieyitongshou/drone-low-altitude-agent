import json
from pathlib import Path

from app.agent import get_business_route


SAMPLE_PATH = Path("data/agent_input_samples.json")


def test_agent_input_samples_are_valid_business_routes():
    samples = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

    assert len(samples) >= 8
    sample_ids = {sample["id"] for sample in samples}
    assert len(sample_ids) == len(samples)
    for sample in samples:
        assert sample["query"]
        if sample["expected_route"] == "ask_clarification":
            continue
        route = get_business_route(sample["expected_intent"])
        assert route is not None
        assert route.primary_tool == sample["expected_route"]
