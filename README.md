# AccessFlow

Discord onboarding bot with a fully configurable application flow. An admin
posts a welcome embed with a persistent **Get Started** button; users press it,
fill out a modal with questions from `config/questions.toml`, and the
application is routed to the admins.

There are two routing modes, set in `config/config.toml`:

- `review` — the application is posted as an embed to a configured channel:
  applicant info (username, id, avatar, account-created and member-join
  timestamps) plus all answers, with Accept / Deny / Open-ticket buttons.
- `direct` — a private ticket channel is created for the applicant immediately,
  containing the same embed, and the decision is made there.

Accepting grants the role from config and DMs the applicant. Denying DMs them
too, optionally with a reason entered in an admin modal. Applicants receive a DM
copy of their answers (toggleable) and may delete it with a button (also
toggleable); they can only have one pending application at a time.

All user-facing text and behavior is configurable via TOML — no code changes
needed (but pull requests and suggestions are appreciated).

## Why?

My friends asked me to make this... so why not.

## Setup

- Python 3.13+, [uv](https://docs.astral.sh/uv/) recommended
- Create a bot at the [Discord Developer Portal](https://discord.com/developers/applications)
- Set the `BOT_TOKEN` env var
- `uv sync && uv run python main.py`

The bot needs Send Messages, Embed Links, Manage Channels, Manage Roles and
Read Message History. Default intents are enough. The SQLite database is created
automatically at `data/accessflow.db`.

## Usage

`/start_screen` (Administrator) posts the welcome embed in the current channel.
The button is persistent and survives bot restarts.

## Configuration

Three files in `config/`:

| File | Contents |
|---|---|
| `config.toml` | behavior: mode, timezone, role id, channel/category ids, toggles |
| `content.toml` | all text: embeds, labels, DMs, buttons, footers |
| `questions.toml` | the application form questions |

Text fields support `{name}`, `{user}` and `{reason}` placeholders; unknown ones
are rejected at startup.

## License

MIT — see [LICENSE](LICENSE).
