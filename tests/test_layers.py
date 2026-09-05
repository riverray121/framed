import time

from framed.layers import Layer, LayerStack


def test_priority_then_recency_wins():
    stack = LayerStack()
    stack.upsert(Layer("base", 0, {"type": "photos"}))
    stack.upsert(Layer("art", 40, {"type": "image"}))
    stack.upsert(Layer("greet", 80, {"type": "greeting"}, ttl=60))
    assert stack.top().id == "greet"
    stack.remove("greet")
    assert stack.top().id == "art"
    stack.upsert(Layer("other", 40, {"type": "text"}))
    assert stack.top().id == "other"


def test_ttl_expires_and_falls_through():
    stack = LayerStack()
    stack.upsert(Layer("base", 0, {"type": "photos"}))
    greet = Layer("greet", 80, {"type": "greeting"}, ttl=1)
    greet.created = time.time() - 2
    stack.upsert(greet)
    assert stack.top().id == "base"
    assert stack.next_expiry() is None


def test_cooldown_blocks_repeat_until_elapsed():
    stack = LayerStack()
    layer = Layer("greet-elijah", 80, {"type": "greeting"}, ttl=5)
    assert stack.upsert(layer, cooldown=1800)
    stack.mark_shown("greet-elijah")
    stack.remove("greet-elijah")
    assert not stack.upsert(Layer("greet-elijah", 80, {"type": "greeting"}), cooldown=1800)
    stack._last_shown["greet-elijah"] = time.time() - 1801
    assert stack.upsert(Layer("greet-elijah", 80, {"type": "greeting"}), cooldown=1800)


def test_empty_stack():
    stack = LayerStack()
    assert stack.top() is None
    assert stack.all() == []
    assert not stack.remove("nothing")
