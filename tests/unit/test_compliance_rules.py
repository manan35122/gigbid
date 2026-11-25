from agent.nodes.compliance import RULES


def test_phone_rule_catches_real_numbers_not_metrics():
    r = RULES["phone"]
    assert r.search("Call +92 300 1234567.")
    assert r.search("Call me on 0300 1234567")
    assert not r.search("I lifted recall from 0.52 to 0.68 and cut time by 31%.")