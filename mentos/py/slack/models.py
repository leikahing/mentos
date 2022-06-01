from pydantic import BaseModel


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
