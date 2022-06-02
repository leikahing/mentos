import asyncio
import re

from datetime import datetime
from operator import attrgetter
from typing import Any, Dict

from mentos.py.freshdesk.client import (
    FreshDeskClient, MissingResourceException
)

import mentos.py.freshdesk.models as fdmodels


class FullBlockCreator:
    def __init__(self, freshdesk: FreshDeskClient, access_url: str):
        self.client = freshdesk
        self.access_url = access_url

    def format_body(self, text: str) -> str:
        """Reply bodies get some rather ugly formatting so this tries to do some
        pretty formatting without trying to touch the html-ified "body" that is
        also sent via API calls like conversations or tickets."""
        # basic rules - if something has more than 3 spaces in a row, assume
        # it's just a linebreak.
        lines = re.split(r"\s{2,}", text)
        return "\n\n".join(lines)

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
        agent, req, group, dept, convos = await asyncio.gather(
            self.client.get_agent(ticket.responder_id),
            self.client.get_agent(ticket.requester_id),
            self.client.get_agent_group(ticket.group_id),
            self.client.get_department(ticket.department_id),
            self.client.get_conversations(ticket_id)
        )

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
        ticket_url = f"{self.access_url}/{ticket_id}"
        if ticket.type.lower() == "incident":
            ident = f"IN-{ticket_id}"
        else:
            ident = f"SR-{ticket_id}"

        info_sections = {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Ticket:*\n<{ticket_url}|{ident}>"
                }
            ]
        }

        if verbose:
            info_sections["fields"].extend([
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
            ])

        description = {
            "mrkdwn_in": ["pretext", "text"],
            "pretext": "*Description*",
            "color": "#ff9933",
            "text": self.format_body(ticket.description_text)
        }

        # for last update, sort the conversations by created (probably?)
        replies = sorted(convos, key=attrgetter("created_at"), reverse=True)
        last_public = next((r for r in replies if not r.private), None)

        if last_public:
            if last_public.user_id == ticket.requester_id:
                reply_from = f"Client: {req.first_name} {req.last_name}"
                color = "#439fe0"
            elif last_public.user_id == agent.id:
                reply_from = f"Tech: {agent.first_name} {agent.last_name}"
                color = "#3cba54"
            else:
                reply_from = "CC"
                color = "#f4c20d"

            reply_attachment = {
                "mrkdwn_in": ["pretext", "text"],
                "pretext": "*Latest Reply*",
                "color": color,
                "author_name": reply_from,
                "text": self.format_body(last_public.body_text)
            }
        else:
            reply_attachment = {
                "mrkdwn_in": ["text"],
                "color": "#db3236",
                "text": "**No replies to show**"
            }

        blocks = [header, divider, info_sections, divider]
        if verbose:
            attachments = [description, reply_attachment]
        else:
            attachments = [reply_attachment]

        return {
            "response_type": "in_channel" if not ephemeral else "ephemeral",
            "blocks": blocks,
            "attachments": attachments
        }
