from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel


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