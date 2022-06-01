# mentos bot


https://user-images.githubusercontent.com/809026/171041460-adba33da-1c68-4353-bb62-a380acbb85b1.mp4


This is an application made by personal request - it handles some FreshDesk functionality for Slack.

## Supported Endpoints

```
SERVER_URL/ticket

Command Arguments: -[vp] TICKET_ID

* -v enables verbose mode, which includes additional ticket information
* -p enables public message mode - the resultant ticket info is publicly displayed in Slack.
* TICKET_ID is the ticket ID you want from freshdesk
```

## Configuration

The bot reads from an environment file called `.env`. A sample configuration titled `.env.sample` is provided that lists all the supported settings.

A full description of the settings is as follows...


| Setting Name | Description |
| ------ | ------ |
| `FRESHDESK_API_URL` | Your URL to access to the FreshDesk API | 
| `FRESHDESK_ACCESS_URL` | Your URL to access FreshDesk itself (e.g. for tickets) | 
| `FRESHDESK_API_KEY` | API key to access the Freshdesk API |
| `SLACK_SIGNING_SECRET` | The signing secret from your Slack app management page for verifying that messages are actually coming from Slack |
| `LIMIT_USERS` | Defaults to `true` if not specified. This allows you to specify `APPROVED_USERS` and provide a list of users who can send commands to this app |
| `APPROVED_USERS` | A JSON list of usernames that are allowed to use this bot. Enforced if `LIMIT_USERS=true` |


## Installing and Running - Production

The easiest way would be to use the provided `Dockerfile`.

Otherwise, to do it from scratch...

```
# get source
git clone --depth 1 https://github.com/leikahing/mentos.git

cd mentos
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt


# configure whatever settings you want in .env and then run server
cp .env.sample .env

gunicorn mentos.py.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Caveats

* Use this with [Slack's apps](https://slack.com/apps) feature, as the this does not work with legacy Slack integrations

## Development

I'd recommend running uvicorn with `--reload` like so:

```
uvicorn mentos.py.main:app --reload
```

This has been tested on Python 3.8+
