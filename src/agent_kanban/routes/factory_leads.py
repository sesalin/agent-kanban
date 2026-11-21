"""Public lead capture; project-filtered reads require the factory identity."""

from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from starlette.middleware.cors import CORSMiddleware

from agent_kanban.factory_coordinator import Coordinator, supabase_client
from agent_kanban.ratelimit import limiter
from agent_kanban.routes.factory import DB, FactoryAgent

router = APIRouter(prefix="/api/factory/leads", tags=["factory leads"])
Identifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
]


class Lead(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    event_id: Identifier
    project_slug: Identifier
    full_name: str = Field(min_length=1, max_length=200)
    contact: str = Field(min_length=3, max_length=320)
    company: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    source_url: HttpUrl | None = None
    honeypot: str = Field(default="", max_length=500)


class LeadCORS:
    """Open CORS for lead endpoints without opening credentialed board routes."""

    def __init__(self, app):
        self.app = app
        self.cors = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["POST", "GET"],
            allow_headers=["Content-Type", "Authorization"],
        )

    async def __call__(self, scope, receive, send):
        target = self.cors if scope.get("path") == "/api/factory/leads" else self.app
        await target(scope, receive, send)


@router.post("", status_code=201)
@limiter.limit("10/minute")
async def create_lead(request: Request, data: Lead, session: DB):
    if data.honeypot:
        return {"ok": True, "lead_id": str(uuid4())}
    async with supabase_client() as client:
        c = Coordinator(session, client)
        try:
            projects = await c.api(
                "GET",
                "opportunity_pipelines",
                params={"event_id": "eq." + data.event_id, "select": "event_id,run_landing"},
            )
            if not projects or not projects[0]["run_landing"] or data.project_slug != data.event_id:
                raise HTTPException(404, "Landing project not found")
            rows = await c.api(
                "POST",
                "factory_leads",
                headers={"Prefer": "return=representation"},
                json=data.model_dump(mode="json", exclude={"honeypot"}),
            )
        except (RuntimeError, httpx.HTTPError) as error:
            raise HTTPException(503, "Lead storage unavailable") from error
    return {"ok": True, "lead_id": rows[0]["id"]}


@router.get("")
async def get_leads(
    session: DB,
    agent: FactoryAgent,
    event_id: Annotated[
        str, Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    ],
    project_slug: Annotated[
        str, Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    ],
):
    async with supabase_client() as client:
        try:
            return await Coordinator(session, client).api(
                "GET",
                "factory_leads",
                params={
                    "event_id": "eq." + event_id,
                    "project_slug": "eq." + project_slug,
                    "order": "created_at.desc",
                    "limit": "100",
                },
            )
        except (RuntimeError, httpx.HTTPError) as error:
            raise HTTPException(503, "Lead storage unavailable") from error
