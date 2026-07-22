"""事件总线单元测试"""
import pytest
from shared.eventbus import Event
from shared.eventbus.events import EventType


def test_event_creation():
    event = Event(
        event_type=EventType.CUSTOMER_HIGH_INTENT,
        source="customer_service",
        payload={"customer_id": "C123"},
    )
    assert event.event_type == "customer.high_intent"
    assert event.source == "customer_service"
    assert event.payload["customer_id"] == "C123"
    assert event.event_id  # auto-generated


def test_event_serialization():
    event = Event(
        event_type="test.event",
        source="test",
        payload={"key": "value"},
    )
    msg = event.to_message()
    assert "event_id" in msg
    assert msg["event_type"] == "test.event"

    restored = Event.from_message(msg)
    assert restored.event_type == event.event_type
    assert restored.payload == event.payload


def test_event_type_enum():
    assert EventType.CUSTOMER_HIGH_INTENT == "customer.high_intent"
    assert EventType.PROMOTION_STARTED == "promotion.started"
    assert EventType.CONTENT_REVIEW_NEEDED == "content.review_needed"
