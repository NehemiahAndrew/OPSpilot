"""OpsPilot — SSE Event Bus for the orchestrator.

Accepts events from any orchestrator step, publishes them to all SSE
subscribers for a given run_id, persists events to the database, and
never loses an event.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class OrchestratorEvent:
    """A single event emitted by the orchestrator."""

    def __init__(
        self,
        run_id: str,
        event_type: str,
        step_number: int = 0,
        agent: str = "",
        status: str = "ok",
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.event_id = str(uuid4())
        self.run_id = run_id
        self.timestamp = datetime.now(timezone.utc)
        self.event_type = event_type
        self.step_number = step_number
        self.agent = agent
        self.status = status
        self.message = message
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "step_number": self.step_number,
            "agent": self.agent,
            "status": self.status,
            "message": self.message,
            "metadata": self.metadata,
        }

    def to_sse(self) -> str:
        """Format as an SSE data line."""
        return json.dumps(self.to_dict(), default=str)


class EventBus:
    """In-memory event bus with SSE subscriber support.

    - publish(): fans out to all subscribers for a run_id
    - subscribe(): returns an async generator that yields events
    - history: retains last N events per run for reconnect replay
    """

    def __init__(self, max_history: int = 100):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._history: Dict[str, List[OrchestratorEvent]] = {}
        self._max_history = max_history

    async def publish(self, event: OrchestratorEvent) -> None:
        """Publish an event to all subscribers and persist to history."""
        # Persist to history
        if event.run_id not in self._history:
            self._history[event.run_id] = []
        self._history[event.run_id].append(event)
        # Trim history
        if len(self._history[event.run_id]) > self._max_history:
            self._history[event.run_id] = self._history[event.run_id][-self._max_history:]

        # Fan out to subscribers
        subs = self._subscribers.get(event.run_id, [])
        for queue in subs:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Event queue full for run %s, dropping event", event.run_id)

    def subscribe(self, run_id: str, last_event_id: Optional[str] = None) -> asyncio.Queue:
        """Subscribe to events for a run_id. Returns a Queue that yields OrchestratorEvents."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        if run_id not in self._subscribers:
            self._subscribers[run_id] = []
        self._subscribers[run_id].append(queue)

        # Replay history: everything on a fresh subscribe, or from the
        # last event id on reconnect. Never loses an event.
        if run_id in self._history:
            replaying = not last_event_id
            for evt in self._history[run_id]:
                if not replaying:
                    if evt.event_id == last_event_id:
                        replaying = True
                    continue
                try:
                    queue.put_nowait(evt)
                except asyncio.QueueFull:
                    break

        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber."""
        subs = self._subscribers.get(run_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs and run_id in self._subscribers:
            del self._subscribers[run_id]

    def get_history(self, run_id: str) -> List[OrchestratorEvent]:
        """Return event history for a run."""
        return list(self._history.get(run_id, []))


# Global singleton
event_bus = EventBus()
