import asyncio

import pytest

from app.events.bus import EventBus


async def test_subscriber_receives_published_message():
    bus = EventBus()
    queue = bus.subscribe()

    await bus.publish({"event_type": "agent.started"})

    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message == {"event_type": "agent.started"}
    bus.unsubscribe(queue)


async def test_multiple_subscribers_all_receive_message():
    bus = EventBus()
    q1, q2 = bus.subscribe(), bus.subscribe()

    await bus.publish({"event_type": "tool.completed"})

    m1 = await asyncio.wait_for(q1.get(), timeout=1)
    m2 = await asyncio.wait_for(q2.get(), timeout=1)
    assert m1 == m2 == {"event_type": "tool.completed"}
    bus.unsubscribe(q1)
    bus.unsubscribe(q2)


async def test_publish_with_no_subscribers_does_not_raise():
    bus = EventBus()
    await bus.publish({"event_type": "orphan"})  # should not raise


async def test_unsubscribed_queue_receives_nothing_further():
    bus = EventBus()
    queue = bus.subscribe()
    bus.unsubscribe(queue)

    await bus.publish({"event_type": "after-unsub"})

    assert queue.empty()
