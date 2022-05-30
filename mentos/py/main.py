from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional

import argparse
import hashlib
import hmac
import logging
import time
import urllib.parse

import aiohttp

from fastapi import Depends, FastAPI, Request, Response, status
from pydantic import BaseModel, BaseSettings, HttpUrl

app = FastAPI()

logger = logging.getLogger("uvicorn")
logger.setLevel("DEBUG")


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


@lru_cache
def get_settings() -> Settings:
    return Settings()


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
    req_ts = int(request.headers["X-Slack-Request-Timestamp"])
    req_sig = request.headers["X-Slack-Signature"]
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

        ticket_api_url = f"{settings.freshdesk_url}/api/v2/tickets"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{ticket_api_url}/{command_args.ticket}?include=requester",
                headers={"content-type": "application/json"},
                auth=aiohttp.BasicAuth(settings.freshdesk_api_key, "X")
            ) as ticket_rsp:
                if 400 <= ticket_rsp.status < 500:
                    return {"text": f"Ticket {command_args.ticket} not found."}

                js = await ticket_rsp.json()
                info = TicketInfo(**js["ticket"])
                await session.post(
                    payload.response_url,
                    json=gen_message(
                        info, command_args.verbose, command_args.public
                    )
                )

        return Response(status_code=status.HTTP_200_OK)
    else:
        if sig_ver == VerificationStatus.BAD_SIGNATURE:
            return {"text": "Slack API call could not be verified."}
        else:
            return {
                "text": "Old Slack call received. Possible replay attack seen!"
            }
