from src.engine.score import weighted_consensus

def test_consensus_is_deterministic():
    result = weighted_consensus([
        {"direction": "LONG", "weight": 0.3},
        {"direction": "LONG", "weight": 0.2},
        {"direction": "SHORT", "weight": 0.1},
    ])
    assert result["direction"] == "LONG"
