import asyncio
import json

from datetime import datetime
from typing import Any, Dict

from mentos.py.freshdesk.client import (
    FreshDeskClient, MissingResourceException
)

import mentos.py.freshdesk.models as fdmodels

import logging
logger = logging.getLogger("uvicorn")


class FullBlockCreator:
    def __init__(self, freshdesk: FreshDeskClient):
        self.client = freshdesk

    def create_date(self, date: datetime, title: str) -> str:
        ts = int(date.timestamp())
        fallback = date.strftime("%c")
        return f"*{title}:*\n<!date^{ts}^{{date}} {{time}}|{fallback}>"

    async def gen_ticket_block(
        self,
        ticket_id: str,
        verbose: bool = False,
        ephemeral: bool = False
    ) -> Dict[str, Any]:
        divider = {"type": "divider"}

        try:
            ticket = await self.client.get_ticket(ticket_id)
        except MissingResourceException:
            return {"text": f"Ticket {ticket_id} not found"}

        # tickets provide a bunch of identifiers that need to be reified
        # into additional objects
        agent, req, group, dept = await asyncio.gather(
            self.client.get_agent(ticket.responder_id),
            self.client.get_agent(ticket.requester_id),
            self.client.get_agent_group(ticket.group_id),
            self.client.get_department(ticket.department_id)
        )
        logger.debug(agent)

        header = {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ticket.subject.strip(),
                "emoji": True
            }
        }

        submitted = self.create_date(ticket.created_at, "Date Submitted")
        updated = self.create_date(ticket.updated_at, "Last Update")
        status = fdmodels.TicketStatus(ticket.status).name

        info_sections = {
            "type": "section",
            "fields": [
                # ticket URL goes here...
                {
                    "type": "mrkdwn",
                    "text": submitted
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Client:*\n{req.first_name} {req.last_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": updated
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Assigned Tech Group:*\n{dept.name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Current Status:*\n{status}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Assigned Tech:*\n{agent.first_name} {agent.last_name}"
                }
            ]
        }

        description = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Description*:\n{ticket.description_text.strip()}"
            }
        }
        blocks = [header, divider, info_sections, divider, description]

        final = {
            "response_type": "in_channel" if not ephemeral else "ephemeral",
            "blocks": blocks
        }
        return json.dumps(final, indent=3)
