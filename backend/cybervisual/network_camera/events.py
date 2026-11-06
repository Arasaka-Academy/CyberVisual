import math
import threading
import time
import uuid
from collections import deque


TOPICS = ("Analytics/PersonPresence", "Analytics/VehiclePresence", "Device/AnalyticsOnline")
VEHICLES = frozenset(("car", "truck", "bus", "motorcycle", "bicycle"))


class SubscriptionError(ValueError):
    pass


class EventBroker(object):
    """Property-change events with independent, bounded PullPoint queues."""

    def __init__(self, disappearance_seconds=2.0, max_subscribers=16, queue_size=256):
        self._condition = threading.Condition()
        self._subscriptions = {}
        self._presence = {"person": False, "vehicle": False}
        self._last_seen = {}
        self._online = False
        self._last_error = None
        self.disappearance_seconds = disappearance_seconds
        self.max_subscribers = max_subscribers
        self.queue_size = queue_size

    def observe(self, detections, frame_ts=None, confidence=0.35, allowlist=(), now=None):
        now = time.monotonic() if now is None else now
        stamp = time.time() if frame_ts is None else frame_ts
        found = set()
        for detection in detections:
            label = detection.get("label", "").lower()
            if detection.get("confidence", 0) < confidence or (allowlist and label not in allowlist):
                continue
            if label == "person":
                found.add("person")
            elif label in VEHICLES:
                found.add("vehicle")
        with self._condition:
            if not self._online:
                # Time spent offline cannot be counted as evidence of absence.
                self._last_seen = {key: now for key, active in self._presence.items() if active}
                self._online = True
                self._publish("Device/AnalyticsOnline", True, stamp)
            self._last_error = None
            for category, active in list(self._presence.items()):
                if category in found:
                    self._last_seen[category] = now
                    if not active:
                        self._presence[category] = True
                        self._publish(self._topic(category), True, stamp)
                elif active and now - self._last_seen.get(category, now) >= self.disappearance_seconds:
                    self._presence[category] = False
                    self._publish(self._topic(category), False, stamp)

    def offline(self, reason):
        with self._condition:
            self._last_error = reason
            if self._online:
                self._online = False
                self._publish("Device/AnalyticsOnline", False, time.time())

    def status(self):
        with self._condition:
            self._expire()
            return {"online": self._online, "last_error": self._last_error,
                    "presence": dict(self._presence), "subscribers": len(self._subscriptions)}

    def subscribe(self, ttl=60, topics=None):
        ttl = self._ttl(ttl)
        selected = set(TOPICS if topics is None else topics)
        if not selected or not selected.issubset(TOPICS):
            raise SubscriptionError("Unsupported event topic filter.")
        with self._condition:
            self._expire()
            if len(self._subscriptions) >= self.max_subscribers:
                raise SubscriptionError("PullPoint subscription limit reached.")
            token = uuid.uuid4().hex
            item = {"id": token, "deadline": time.monotonic() + ttl,
                    "expires": time.time() + ttl, "topics": selected, "queue": deque()}
            self._subscriptions[token] = item
            self._initialize(item)
            return {"id": token, "expires": item["expires"]}

    def pull(self, token, timeout=0, limit=64):
        if not math.isfinite(timeout) or not 0 <= timeout <= 30 or not 1 <= limit <= 64:
            raise SubscriptionError("Pull timeout must be 0..30 seconds and message limit 1..64.")
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                item = self._get(token)
                if item["queue"] or time.monotonic() >= deadline:
                    return [item["queue"].popleft() for _ in range(min(limit, len(item["queue"])))]
                remaining = min(deadline, item["deadline"]) - time.monotonic()
                self._condition.wait(max(0, remaining))

    def renew(self, token, ttl=60):
        ttl = self._ttl(ttl)
        with self._condition:
            item = self._get(token)
            item.update(deadline=time.monotonic() + ttl, expires=time.time() + ttl)
            self._condition.notify_all()
            return item["expires"]

    def expiry(self, token):
        with self._condition:
            return self._get(token)["expires"]

    def synchronize(self, token):
        with self._condition:
            item = self._get(token)
            item["queue"].clear()
            self._initialize(item)
            self._condition.notify_all()

    def unsubscribe(self, token):
        with self._condition:
            self._get(token)
            del self._subscriptions[token]
            self._condition.notify_all()

    def close(self):
        with self._condition:
            self._subscriptions.clear()
            self._condition.notify_all()

    def _get(self, token):
        self._expire()
        if token not in self._subscriptions:
            raise SubscriptionError("Unknown or expired PullPoint subscription.")
        return self._subscriptions[token]

    def _expire(self):
        now = time.monotonic()
        for token, item in list(self._subscriptions.items()):
            if item["deadline"] <= now:
                del self._subscriptions[token]

    def _initialize(self, item):
        states = {self._topic(key): value for key, value in self._presence.items()}
        states["Device/AnalyticsOnline"] = self._online
        for topic in TOPICS:
            if topic in item["topics"]:
                item["queue"].append(self._event(topic, states[topic], time.time(), True))

    def _publish(self, topic, state, stamp):
        self._expire()
        event = self._event(topic, state, stamp, False)
        for item in self._subscriptions.values():
            if topic not in item["topics"]:
                continue
            if len(item["queue"]) >= self.queue_size:
                item["queue"].clear()
                self._initialize(item)
            item["queue"].append(event)
        self._condition.notify_all()

    @staticmethod
    def _topic(category):
        return "Analytics/%sPresence" % category.title()

    @staticmethod
    def _event(topic, state, stamp, initialized):
        category = {"Analytics/PersonPresence": "person", "Analytics/VehiclePresence": "vehicle"}.get(topic, "analytics")
        return {"topic": topic, "state": bool(state), "frame_ts": stamp,
                "initialized": initialized, "source": "camera0", "category": category}

    @staticmethod
    def _ttl(value):
        if not math.isfinite(value) or not 1 <= value <= 3600:
            raise SubscriptionError("Subscription lifetime must be 1..3600 seconds.")
        return value
