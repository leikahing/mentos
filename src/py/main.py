import argparse
import logging

import requests

from fastapi import Depends, FastAPI, Form
from pydantic import BaseModel

app = FastAPI()

def slack_body(cls):
    cls.__signature__ = cls.__signature__.replace(
        parameters=[
            arg.replace(default=Form(...))
            for arg in cls.__signature__.parameters.values()
        ]
    )
    return cls

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

def create_parser():
    parser = argparse.ArgumentParser(description="Parse ticket request command")
    parser.add_argument("-v", dest="verbose", action="store_true")
    parser.add_argument("ticket")
    return parser

@app.get("/")
async def root():
    """Returns info about this bot."""
    return {"name": "mentos-bot", "version": "1.0"}

@app.post("/request")
async def ticket_info(payload: SlackPayload = Depends(SlackPayload)):
    """This responds to the following Slack command:

    /request [-v] TICKET 

    * -v - verbose mode, return more info about the ticket
    * TICKET - a number/identifier for the FreshDesk ticket"""
    parser = create_parser()
    command_args = parser.parse_args(payload.text.split())
    return {"verbose": command_args.verbose, "ticket": command_args.ticket} 
