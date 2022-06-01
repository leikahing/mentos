from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List

import argparse
import logging
import urllib.parse

from fastapi import Depends, FastAPI, Request, Response
from pydantic import BaseSettings, HttpUrl

import mentos.py.slack.util as SlackUtils

from mentos.py.freshdesk.client import (
    FreshDeskClient, MissingResourceException
)
from mentos.py.freshdesk.models import TicketInfo
from mentos.py.slack.models import SlackPayload
from mentos.py.slack.util import VerificationStatus


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


def gen_message(
    ticket: TicketInfo,
    verbose: bool = False,
    private: bool = False
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
        "response_type": "in_channel" if not private else "ephemeral",
        "blocks": blocks
    }


def get_ticket_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse ticket request")
    parser.add_argument("-v", dest="verbose", action="store_true")
    parser.add_argument("-p", dest="private", action="store_true")
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
    * -p - show the information privately to requester, rather than publicly
    * TICKET - a number/identifier for the FreshDesk ticket"""

    body = (await request.body()).decode("utf-8")
    logger.info(request.headers)
    logger.info(body)
    req_ts = int(request.headers["x-slack-request-timestamp"])
    logger.info(f"x-slack-request-timestamp={req_ts}")
    req_sig = request.headers["x-slack-signature"]
    logger.info(f"x-slack-signature={req_sig}")
    secret = settings.slack_signing_secret

    sig_ver = SlackUtils.verify_signature(secret, body, req_sig, req_ts)
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
        return gen_message(ticket, command_args.verbose, command_args.private)
    else:
        if sig_ver == VerificationStatus.BAD_SIGNATURE:
            return {"text": "Slack API call could not be verified."}
        else:
            return {
                "text": "Old Slack call received. Possible replay attack seen!"
            }
