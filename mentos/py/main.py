from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Type, TypeVar

import argparse
import hashlib
import hmac
import logging
import os
import time
import urllib.parse

import aiohttp

from async_lru import alru_cache
from fastapi import Depends, FastAPI, Request, Response, status
from pydantic import BaseModel, BaseSettings, HttpUrl

T = TypeVar("T")


class VerificationStatus(Enum):
    VERIFIED = 1
    BAD_SIGNATURE = 2
    OUTDATED_REQUEST = 3


def verify_signature(
    secret: str,
    body: str,
    req_sig: str,
    req_ts: int
) -> VerificationStatus:
    """Perform request signature verification.

    Requires the signing secret from your Slack application.
    The other parameters are the raw request body (from Slack), request
    signature, and  the request timestamp.

    See https://api.slack.com/authentication/verifying-requests-from-slack"""
    if abs(int(time.time()) - req_ts) > 300:
        # request timestamp is old, so ignore this request as it could be
        # a replay
        VerificationStatus.OUTDATED_REQUEST

    bs = f"v0:{req_ts}:{body}"
    hsh = hmac.new(
            bytes(secret, "utf-8"),
            msg=bytes(bs, "utf-8"),
            digestmod=hashlib.sha256).hexdigest()

    signature = f"v0={hsh}"
    if hmac.compare_digest(signature, req_sig):
        return VerificationStatus.VERIFIED
    return VerificationStatus.BAD_SIGNATURE


class Settings(BaseSettings):
    freshdesk_url: HttpUrl
    freshdesk_api_key: str
    slack_signing_secret: str
    limit_users: bool = True
    approved_users: List[str]

    class Config:
        env_file = ".env"


class Requester(BaseModel):
    """This is the 'requester' block that is returned when tickets are
    requested with the '?include=requester' param"""
    id: int
    name: str
    email: str


class TicketInfo(BaseModel):
    """
    Model for the FreshDesk API's ticket info. Doesn't fully capture everything
    in the response because there are some additional fields that don't really
    matter for the purpose, like conversations.

    See API: https://api.freshservice.com/#view_a_ticket"""
    cc_emails: List[str]
    fwd_emails: List[str]
    reply_cc_emails: List[str]
    fr_escalated: bool
    spam: bool
    email_config_id: Optional[int]
    group_id: Optional[int]
    priority: int
    requester_id: int
    responder_id: Optional[int]
    source: int
    status: int
    subject: str
    to_emails: Optional[List[str]]
    sla_policy_id: int
    department_id: Optional[int]
    id: int
    type: str
    due_by: datetime
    fr_due_by: datetime
    is_escalated: bool
    description: str
    description_text: str
    created_at: datetime
    updated_at: datetime
    urgency: int
    impact: int
    category: Optional[str]
    sub_category: Optional[str]
    item_category: Optional[str]
    deleted: bool
    requester: Optional[Requester]


class AgentGroup(BaseModel):
    id: int
    name: str
    description: str


class Agent(BaseModel):
    id: int
    active: bool
    email: str
    first_name: str
    last_name: str


class Department(BaseModel):
    id: int
    name: str
    description: str
    header_user_id: int
    prime_user_id: int


class MissingResourceException(Exception):
    """Exception for some missing API resource"""


class FreshDeskClient:
    base_url: str = None
    api_key: str = None
    session: aiohttp.ClientSession = None

    def configure(self, url: str, api_key: str):
        self.session = aiohttp.ClientSession()
        self.base_url = url
        self.api_key = api_key

    async def cleanup(self):
        logger.info(self.get_agent.cache_info())
        logger.info(self.get_ticket.cache_info())
        await self.session.close()

    async def _api_fetch(self, resource: str, gen_type: Type[T]) -> T:
        api_url = f"{self.base_url}/api/v2/{resource}"
        headers = {"content-type": "application/json"}
        async with self.session.get(
            api_url,
            headers=headers,
            auth=aiohttp.BasicAuth(self.api_key, "X")
        ) as rsp:
            if 400 <= rsp.status < 500:
                raise MissingResourceException

            js = await rsp.json()
            return gen_type(**next(iter(js.values())))

    @alru_cache
    async def get_agent(self, agent_id: int):
        resource = f"agents/{agent_id}"
        return await self._api_fetch(resource, Agent)

    @alru_cache
    async def get_agent_group(self, agent_group: int):
        resource = f"groups/{agent_group}"
        return await self._api_fetch(resource, AgentGroup)

    @alru_cache
    async def get_department(self, department_id: int):
        resource = f"departments/{department_id}"
        return await self._api_fetch(resource, Department)

    @alru_cache
    async def get_ticket(self, ticket_id: str) -> TicketInfo:
        resource = f"tickets/{ticket_id}"
        return await self._api_fetch(resource, TicketInfo)


@lru_cache
def get_settings() -> Settings:
    return Settings()


class SlackPayload(BaseModel):
    """This payload is documented in Slack's command API.

    It ignores some fields that don't particularly matter like whether or not
    this is running an Enterprise Slack.

    See:
    https://api.slack.com/interactivity/slash-commands#app_command_handling"""
    token: str
    team_id: str
    team_domain: str
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    command: str
    text: str
    response_url: str
    trigger_id: str
    api_app_id: str


def gen_message(
    ticket: TicketInfo,
    verbose: bool = False,
    public: bool = False
) -> Dict[str, Any]:
    divider = {"type": "divider"}
    header = {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": ticket.subject.strip()
        },
    }

    def create_date(date: datetime, title: str) -> str:
        ts = int(date.timestamp())
        fallback = date.strftime("%c")
        return f"*{title}:*\n<!date^{ts}^{{date}} {{time}}|{fallback}>"

    created = create_date(ticket.created_at, "Created")
    updated = create_date(ticket.updated_at, "Updated")
    due = create_date(ticket.due_by, "Due By")

    date_sections = {
        "type": "section",
        "fields": [
            {
                "type": "mrkdwn",
                "text": created
            },
            {
                "type": "mrkdwn",
                "text": due
            },
            {
                "type": "mrkdwn",
                "text": updated
            }
        ]
    }

    if verbose:
        description = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Description*:\n{ticket.description_text.strip()}"
            }
        }
        blocks = [header, description, divider, date_sections]
    else:
        blocks = [header, divider, date_sections]

    return {
        "response_type": "in_channel" if public else "ephemeral",
        "blocks": blocks
    }


def get_ticket_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse ticket request")
    parser.add_argument("-v", dest="verbose", action="store_true")
    parser.add_argument("-p", dest="public", action="store_true")
    parser.add_argument("ticket")
    return parser


app = FastAPI()
freshdesk = FreshDeskClient()

logger = logging.getLogger("uvicorn")
logger.setLevel("DEBUG")


@app.on_event("startup")
def startup():
    settings = get_settings()
    freshdesk.configure(settings.freshdesk_url, settings.freshdesk_api_key)


@app.on_event("shutdown")
async def shutdown_app():
    await freshdesk.cleanup()


@app.get("/")
async def index(settings: Settings = Depends(get_settings)):
    """Returns info about this bot."""
    return {"name": "mentos-bot", "version": "1.0"}


@app.post("/ticket")
async def ticket_info(
    request: Request,
    settings: Settings = Depends(get_settings)
) -> Response:
    """This responds to the following Slack command:
    /COMMAND [-v] [-p] TICKET

    * -v - verbose mode, return more info about the ticket
    * -p - show the information publicly in requesting channel
    * TICKET - a number/identifier for the FreshDesk ticket"""

    body = (await request.body()).decode("utf-8")
    logger.info(request.headers)
    logger.info(body)
    req_ts = int(request.headers["x-slack-request-timestamp"])
    logger.info(f"x-slack-request-timestamp={req_ts}")
    req_sig = request.headers["x-slack-signature"]
    logger.info(f"x-slack-signature={req_sig}")
    secret = settings.slack_signing_secret

    sig_ver = verify_signature(secret, body, req_sig, req_ts)
    if sig_ver in (VerificationStatus.VERIFIED,):
        qsd = dict(urllib.parse.parse_qsl(body))
        payload = SlackPayload.parse_obj(qsd)

        if payload.user_name not in settings.approved_users:
            return {
                "text": f"Sorry, user {payload.user_name} isn't authorized."
            }

        parser = get_ticket_parser()
        command_args = parser.parse_args(payload.text.split())

        try:
            ticket = await freshdesk.get_ticket(command_args.ticket)
            logger.info(ticket)
        except MissingResourceException:
            return {"text": f"Ticket {command_args.ticket} not found"}
        return gen_message(ticket, command_args.verbose, command_args.public)
    else:
        if sig_ver == VerificationStatus.BAD_SIGNATURE:
            return {"text": "Slack API call could not be verified."}
        else:
            return {
                "text": "Old Slack call received. Possible replay attack seen!"
            }
