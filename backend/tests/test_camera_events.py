import pytest

from cybervisual.network_camera.events import EventBroker, SubscriptionError


PERSON = {"label": "person", "confidence": 0.9}


def subscription(broker, topic="Analytics/PersonPresence"):
    item = broker.subscribe(topics=[topic])
    broker.pull(item["id"], timeout=0)
    return item["id"]


def test_presence_emits_edges_and_waits_two_seconds_before_disappearance():
    broker = EventBroker()
    token = subscription(broker)
    broker.observe([PERSON], frame_ts=100, now=10)
    broker.observe([PERSON], frame_ts=101, now=11)
    assert [e["state"] for e in broker.pull(token, timeout=0)] == [True]
    broker.observe([], frame_ts=102, now=12)
    assert broker.pull(token, timeout=0) == []
    broker.observe([], frame_ts=103, now=13.01)
    events = broker.pull(token, timeout=0)
    assert [e["state"] for e in events] == [False]
    assert events[0]["frame_ts"] == 103


def test_offline_does_not_invent_disappearance_and_recovery_resets_grace_period():
    broker = EventBroker()
    token = subscription(broker)
    broker.observe([PERSON], now=10)
    broker.pull(token, timeout=0)
    broker.offline("camera disconnected")
    assert broker.pull(token, timeout=0) == []
    broker.observe([], now=100)
    assert broker.pull(token, timeout=0) == []
    broker.observe([], now=102.01)
    assert [e["state"] for e in broker.pull(token, timeout=0)] == [False]


def test_subscribers_are_independent_and_vehicle_classes_share_one_state():
    broker = EventBroker()
    first = subscription(broker, "Analytics/VehiclePresence")
    second = subscription(broker, "Analytics/VehiclePresence")
    broker.observe([{"label": "car", "confidence": 0.9}], now=1)
    broker.observe([{"label": "bus", "confidence": 0.8}], now=2)
    assert [e["state"] for e in broker.pull(first, timeout=0)] == [True]
    assert [e["state"] for e in broker.pull(second, timeout=0)] == [True]
    broker.synchronize(first)
    assert broker.pull(first, timeout=0)[0]["initialized"] is True
    broker.unsubscribe(first)
    with pytest.raises(SubscriptionError):
        broker.pull(first, timeout=0)


def test_filtering_and_expired_subscriptions(monkeypatch):
    broker = EventBroker()
    token = subscription(broker)
    broker.observe([PERSON], confidence=0.95, now=1)
    broker.observe([PERSON], allowlist=["car"], now=2)
    assert broker.pull(token, timeout=0) == []
    broker.renew(token, ttl=1)
    monkeypatch.setattr("cybervisual.network_camera.events.time.monotonic", lambda: float("inf"))
    with pytest.raises(SubscriptionError):
        broker.pull(token, timeout=0)


def test_slow_subscriber_overflow_resynchronizes_without_blocking_others():
    broker = EventBroker(queue_size=4)
    slow = subscription(broker)
    fast = subscription(broker)
    for index in range(10):
        broker.observe([PERSON], now=index * 10)
        broker.observe([], now=index * 10 + 3)
        assert [event["state"] for event in broker.pull(fast)] == [True, False]
    backlog = broker.pull(slow)
    assert len(backlog) <= 4
    assert any(event["initialized"] for event in backlog)
    assert backlog[-1]["state"] is False


def test_unsubscribe_and_shutdown_wake_blocked_pullers():
    import concurrent.futures

    broker = EventBroker()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
        first, second = subscription(broker), subscription(broker)
        pending = [workers.submit(broker.pull, token, timeout=30) for token in (first, second)]
        broker.unsubscribe(first)
        broker.close()
        for future in pending:
            with pytest.raises(SubscriptionError):
                future.result(timeout=1)
