import asyncio
import re

from datetime import datetime
from enum import Enum
from operator import attrgetter
from typing import Any, ClassVar, Dict, List

from mentos.py.freshdesk.client import (
    FreshDeskClient, MissingResourceException, ServerError
)

from mentos.py.freshdesk.models import TicketStatus, TicketType
import mentos.py.freshdesk.models as fdmodels


class FullBlockCreator:
    ticket_map = {
        TicketType.Case: "CASE",
        TicketType.Incident: "INC",
        TicketType.Request: "REQ",
        TicketType["Service Request"]: "SR",
    }
    def __init__(
        self,
        freshdesk: FreshDeskClient,
        access_url: str,
        ticket_statuses: Enum = TicketStatus
    ):
        self.client = freshdesk
        self.access_url = access_url
        self.statuses = ticket_statuses

    def format_body(self, text: str) -> str:
        """Reply bodies get some rather ugly formatting so this tries to do some
        pretty formatting without trying to touch the html-ified "body" that is
        also sent via API calls like conversations or tickets."""
        # basic rules - if something has more than 3 spaces in a row, assume
        # it's just a linebreak.
        lines = re.split(r"\s{2,}", text)
        return "\n\n".join(lines)

    def format_sr_info(self, req_info: List[fdmodels.RequestedItems]):
        text = []
        print(type(req_info))
        for ri in req_info:
            for k, v in ri.custom_fields.items():
                key = k.replace("_", " ").title()
                text.append(f"*{key}*: {v}")
        return "\n".join(text)

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
        except ServerError:
            return {"text": "FreshDesk server encountered issues. Try again later."}

        # tickets provide a bunch of identifiers that need to be reified
        # into additional objects
        agent, req, group, convos, req_items = await asyncio.gather(
            self.client.get_agent(ticket.responder_id),
            self.client.get_requester(ticket.requester_id),
            self.client.get_agent_group(ticket.group_id),
            self.client.get_conversations(ticket_id),
            self.client.get_requested_items(ticket_id),
            return_exceptions=True
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
        try:
            status = self.statuses(ticket.status).name
        except ValueError:
            status = f"Custom Status - {ticket.status}"
        ticket_url = f"{self.access_url}/{ticket_id}"

        key_type = FullBlockCreator.ticket_map[ticket.type]
        ident = f"{key_type}-{ticket_id}"
        if ticket.type in [TicketType.Incident]:
            description = {
                "mrkdwn_in": ["pretext", "text"],
                "pretext": "*Description*",
                "color": "#ff9933",
                "text": self.format_body(ticket.description_text)
            }
        elif ticket.type in [TicketType.Case]:
            description = {
                "mrkdwn_in": ["pretext", "text"],
                "pretext": "*Case Description*",
                "color": "#ff9933",
                "text": self.format_body(ticket.description_text)
            }
        else:
            pretext_name = "Request" if ticket.type == TicketType.Request else "Service Request"
            description = {
                "mrkdwn_in": ["pretext", "text"],
                "pretext": f"*{pretext_name} - Requested Items*",
                "color": "#ff9933",
                "text": self.format_sr_info(req_items)
            }

        info_sections = {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Ticket:*\n<{ticket_url}|{ident}>"
                }
            ]
        }

        # sometimes stuff doesn't have groups or agents, either
        # because they're unassigned or because groups aren't
        # used
        agentless = False
        if isinstance(agent, MissingResourceException):
            agentless = True
            agent_text = "No Agent Assigned"
        else:
            agent_text = f"{agent.first_name} {agent.last_name}"

        if isinstance(group, MissingResourceException):
            group_text = "No Assigned Group"
        else:
            group_text = group.name

        if req:
            requester = f"*Client:*\n{req.first_name} {req.last_name}"
        else:
            requester = f"*Client*: Unknown"

        if verbose:
            info_sections["fields"].extend([
                {
                    "type": "mrkdwn",
                    "text": submitted
                },
                {
                    "type": "mrkdwn",
                    "text": requester
                },
                {
                    "type": "mrkdwn",
                    "text": updated
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Assigned Tech Group:*\n{group_text}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Current Status:*\n{status}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Assigned Tech:*\n{agent_text}"
                }
            ])

        # for last update, sort the conversations by created (probably?)
        replies = sorted(convos, key=attrgetter("created_at"), reverse=True)
        last_public = next((r for r in replies if not r.private), None)

        if last_public:
            if last_public.user_id == ticket.requester_id:
                reply_from = requester
                color = "#439fe0"
            elif not agentless and last_public.user_id == agent.id:
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
                "text": "*No replies to show*"
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
