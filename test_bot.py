from bot import crossover_signal

def test_buy_signal():
    s=crossover_signal(2650,2649,2648,2647,2648,4)
    assert s.action=="BUY" and s.stop_loss==2647 and s.tp1==2652 and s.tp2==2654

def test_no_signal():
    s=crossover_signal(2650,2648,2649,2648,2649,4)
    assert s.action=="NONE"
