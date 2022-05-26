from datetime import datetime
from functools import cache
from typing import List, Union

import argparse
import asyncio
import base64
import logging

import aiohttp

from fastapi import Depends, FastAPI, Form
from pydantic import BaseModel, BaseSettings, HttpUrl

app = FastAPI()

def slack_body(cls):
    cls.__signature__ = cls.__signature__.replace(
        parameters=[
            arg.replace(default=Form(...))
            for arg in cls.__signature__.parameters.values()
        ]
    )
    return cls

class Settings(BaseSettings):
    freshdesk_url: HttpUrl
    freshdesk_api_key: str
    slack_signing_secret: str
    approved_users: List[str]

    class Config:
        env_file = ".env"

@cache
def get_settings():
    return Settings()
    

class TicketInfo(BaseModel):
    """
    Model for the FreshDesk API's ticket info.
    
    See API: https://api.freshservice.com/#view_a_ticket"""
    cc_emails: List[str]
    fwd_emails: List[str]
    reply_cc_emails: List[str]
    fr_escalated: bool
    spam: bool
    email_config_id: Union[int, None]
    group_id: Union[int, None]
    priority: int
    requester_id: int
    responder_id: Union[int, None]
    source: int
    status: int
    subject: str
    to_emails: Union[List[str], None]
    sla_policy_id: int
    department_id: Union[int, None]
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
    category: Union[str, None]
    sub_category: Union[str, None]
    item_category: Union[str, None]
    deleted: bool

@slack_body
class SlackPayload(BaseModel):
    """This payload is documented in Slack's command API.

    See:
    https://api.slack.com/interactivity/slash-commands#app_command_handling"""
    token: str
    team_id: str
    team_domain: str
    enterprise_id: str
    enterprise_name: str
    channel_id: str
    channel_name: str
    user_id: str
    user_name: str
    command: str
    text: str
    response_url: str
    trigger_id: str
    api_app_id: str

def get_ticket_parser():
    parser = argparse.ArgumentParser(description="Parse ticket request command")
    parser.add_argument("-v", dest="verbose", action="store_true")
    parser.add_argument("ticket")
    return parser

@app.get("/")
async def index(settings: Settings = Depends(get_settings)):
    """Returns info about this bot."""
    return {"name": "mentos-bot", "version": "1.0"}

@app.post("/request")
async def ticket_info(
        payload: SlackPayload = Depends(SlackPayload),
        settings: Settings = Depends(get_settings)):
    """This responds to the following Slack command:

    /request [-v] TICKET 

    * -v - verbose mode, return more info about the ticket
    * TICKET - a number/identifier for the FreshDesk ticket"""
    parser = get_ticket_parser()
    command_args = parser.parse_args(payload.command.split())
    
    headers = {
        "content-type": "application/json",
    }
    async with aiohttp.ClientSession(
            f"{settings.freshdesk_url}",
            headers=headers,
            auth=aiohttp.BasicAuth(settings.freshdesk_api_key, "X")
    ) as session:
        async with session.get(f"/api/v2/tickets/{command_args.ticket}") as rsp:
            js = await rsp.json()
            return TicketInfo(**js["ticket"])
