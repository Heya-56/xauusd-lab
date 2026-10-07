from src.engine.confluence import Vote, decide, should_trade

def test_two_buy_votes_create_decision():
    d = decide([
        Vote("sata", "normal-tendance", "buy", 90),
        Vote("sata", "normal-smc", "buy", 85),
        Vote("other", "candidate", "sell", 80),
    ], min_agreement=2)
    assert d.side == "buy"
    assert should_trade(d, True, True, True)

def test_disagreement_means_no_trade():
    d = decide([
        Vote("sata", "normal-tendance", "buy", 90),
        Vote("sata", "normal-smc", "sell", 90),
    ], min_agreement=2)
    assert d.side == "none"
    assert not should_trade(d, True, True, True)
