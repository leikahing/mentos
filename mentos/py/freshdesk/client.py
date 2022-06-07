from typing import Any, Dict, List, Type, TypeVar

import aiohttp

from async_lru import alru_cache

import mentos.py.freshdesk.models as fdmodels

T = TypeVar("T")


class MissingResourceException(Exception):
    """Exception for some missing API resource"""


class ServerError(Exception):
    """Exception for server-level issues (e.g. HTTP 5xx)"""


class FreshDeskClient:
    base_url: str = None
    api_key: str = None
    session: aiohttp.ClientSession = None

    def configure(self, url: str, api_key: str):
        self.session = aiohttp.ClientSession()
        self.base_url = url
        self.api_key = api_key

    async def cleanup(self):
        await self.session.close()

    async def _api_fetch(self, resource: str) -> Dict[str, Any]:
        api_url = f"{self.base_url}/api/v2/{resource}"
        headers = {"content-type": "application/json"}
        async with self.session.get(
            api_url,
            headers=headers,
            auth=aiohttp.BasicAuth(self.api_key, "X")
        ) as rsp:
            if 400 <= rsp.status < 500:
                raise MissingResourceException
            elif rsp.status >= 500:
                raise ServerError

            js = await rsp.json()
            return js

    async def _api_fetch_list(
        self,
        resource: str,
        gen_type: Type[T]
    ) -> List[T]:
        js = await self._api_fetch(resource)
        inner_list = next(iter(js.values()))
        return [gen_type(**x) for x in inner_list]

    async def _api_fetch_single(
        self,
        resource: str,
        gen_type: Type[T]
    ) -> T:
        js = await self._api_fetch(resource)
        return gen_type(**next(iter(js.values())))

    @alru_cache
    async def get_agent(self, agent_id: int) -> fdmodels.Agent:
        resource = f"agents/{agent_id}"
        return await self._api_fetch_single(resource, fdmodels.Agent)

    @alru_cache
    async def get_requester(self, requester_id: int) -> fdmodels.Requester:
        resource = f"requesters/{requester_id}"
        return await self._api_fetch_single(resource, fdmodels.Requester)

    @alru_cache
    async def get_agent_group(self, agent_group: int) -> fdmodels.AgentGroup:
        resource = f"groups/{agent_group}"
        return await self._api_fetch_single(resource, fdmodels.AgentGroup)

    @alru_cache
    async def get_department(self, department_id: int) -> fdmodels.Department:
        resource = f"departments/{department_id}"
        return await self._api_fetch_single(resource, fdmodels.Department)

    async def get_requested_items(
        self,
        ticket_id: str
    ) -> List[fdmodels.RequestedItems]:
        resource = f"tickets/{ticket_id}/requested_items"
        return await self._api_fetch_list(resource, fdmodels.RequestedItems)

    async def get_conversations(
        self,
        ticket_id: str
    ) -> List[fdmodels.Conversation]:
        resource = f"tickets/{ticket_id}/conversations"
        return await self._api_fetch_list(resource, fdmodels.Conversation)

    async def get_ticket(self, ticket_id: str) -> fdmodels.TicketInfo:
        resource = f"tickets/{ticket_id}"
        return await self._api_fetch_single(resource, fdmodels.TicketInfo)
