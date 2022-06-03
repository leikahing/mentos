from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

TicketStatus = Enum("TicketStatus", [("Open", 2), ("Pending", 3), ("Resolved", 4), ("Closed", 5)])
Priority = Enum("Priority", [("Low", 1), ("Medium", 2), ("High", 3), ("Urgent", 4)])


class Requester(BaseModel):
    """This is the 'requester' block that is returned when tickets are
    requested with the '?include=requester' param"""
    id: int
    first_name: str
    last_name: str
    primary_email: str

class Meta(BaseModel):
    count: int

class Conversation(BaseModel):
    created_at: datetime
    updated_at: datetime
    body: str
    body_text: str
    private: bool = False
    user_id: int
    support_email: Optional[str]
    ticket_id: int

class Conversations(BaseModel):
    conversations: List[Conversation]
    meta: Meta


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
