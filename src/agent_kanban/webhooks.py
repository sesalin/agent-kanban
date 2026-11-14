"""Best-effort delivery after the task transaction commits."""

import asyncio
import logging

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.models import OutboundWebhook

logger = logging.getLogger(__name__)
_pending: set[asyncio.Task] = set()


async def _send(url: str, token: str | None, body: dict) -> None:
    headers = {"X-Webhook-Secret": token} if token else {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        logger.warning(
            "Webhook delivery failed for project %s (%s)", body["project_id"], body["event"]
        )


async def notify_task_event(
    session: AsyncSession, project_id: int | None, event_type: str, payload: dict
) -> None:
    if project_id is None:
        return
    try:
        result = await session.execute(
            select(OutboundWebhook.target_url, OutboundWebhook.secret_token).where(
                OutboundWebhook.project_id == project_id, OutboundWebhook.is_active.is_(True)
            )
        )
    except SQLAlchemyError:
        logger.warning("Webhook lookup failed for project %s (%s)", project_id, event_type)
        return

    body = {"event": event_type, "project_id": project_id, "data": payload}
    for url, token in result:
        delivery = asyncio.create_task(_send(url, token, body))
        _pending.add(delivery)
        delivery.add_done_callback(_pending.discard)
