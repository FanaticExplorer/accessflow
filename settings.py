from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CONFIG_DIR = Path(__file__).resolve().parent / "config"

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class EmbedSettings(BaseModel):
    title: str
    description: str = ""
    color: str = Field(pattern=r"^#?[0-9A-Fa-f]{6}$")
    image: str = ""

    @field_validator("image")
    @classmethod
    def _check_image_url(cls, value: str) -> str:
        if value and not value.startswith(("http://", "https://", "attachment://")):
            raise ValueError(
                f"'image' must be a URL (http://, https:// or attachment://), got {value!r}"
            )
        return value


class WelcomeEmbedSettings(EmbedSettings):
    footer: str = ""


class TicketMessageSettings(EmbedSettings):
    @model_validator(mode="after")
    def _check_placeholders(self) -> TicketMessageSettings:
        for field_name in ("title", "description"):
            text = getattr(self, field_name)
            unknown = set(_PLACEHOLDER_RE.findall(text)) - {"user"}
            if unknown:
                raise ValueError(
                    f"'review.ticket.{field_name}' may only use the '{{user}}' "
                    f"placeholder, got: {', '.join(sorted(unknown))}"
                )
        return self


class CopyEmbedSettings(BaseModel):
    title: str
    color: str = Field(pattern=r"^#?[0-9A-Fa-f]{6}$")


class DecisionDmSettings(BaseModel):
    accepted: str = "Congratulations, {user}! Your application was accepted."
    denied: str = "Your application was declined."
    denied_with_reason: str = "Your application was declined. Reason: {reason}"

    @model_validator(mode="after")
    def _check_placeholders(self) -> DecisionDmSettings:
        for field_name in ("accepted", "denied", "denied_with_reason"):
            text = getattr(self, field_name)
            unknown = set(_PLACEHOLDER_RE.findall(text)) - {"user", "reason"}
            if unknown:
                raise ValueError(
                    f"'application.dm.{field_name}' may only use the '{{user}}' and "
                    f"'{{reason}}' placeholders, got: {', '.join(sorted(unknown))}"
                )
        return self


class DenyModalSettings(BaseModel):
    title: str
    label: str
    placeholder: str = ""


class ApplicationContentSettings(BaseModel):
    user_label: str = "User"
    created_label: str = "Account created"
    joined_label: str = "Member joined"
    accepted_footer: str = "Application accepted by {user}"
    denied_footer: str = "Application denied by {user}"
    deleted_footer: str = "Application deleted by {user}"
    embed: EmbedSettings
    dm: DecisionDmSettings
    deny_modal: DenyModalSettings
    copy_embed: CopyEmbedSettings


class ReviewContentSettings(BaseModel):
    ticket: TicketMessageSettings


class TranscriptSettings(BaseModel):
    header: str = "AccessFlow ticket transcript"
    filename: str = "ticket-{user}.txt"
    message: str = "Transcript for {user}"

    @model_validator(mode="after")
    def _check_placeholders(self) -> TranscriptSettings:
        for field_name in ("filename", "message"):
            text = getattr(self, field_name)
            unknown = set(_PLACEHOLDER_RE.findall(text)) - {"user"}
            if unknown:
                raise ValueError(
                    f"'transcript.{field_name}' may only use the '{{user}}' "
                    f"placeholder, got: {', '.join(sorted(unknown))}"
                )
        return self


class ButtonsReplySettings(BaseModel):
    accept: str
    deny: str
    delete: str


class ButtonsSettings(BaseModel):
    accept: str
    deny: str
    open_ticket: str
    delete: str
    reply: ButtonsReplySettings


class StartScreenSettings(BaseModel):
    modal_title: str
    button_label: str
    ack_message: str
    confirmation_message: str
    existing_application_message: str = "You already have an active application!"
    welcome: WelcomeEmbedSettings
    application: ApplicationContentSettings
    review: ReviewContentSettings
    transcript: TranscriptSettings
    buttons: ButtonsSettings


class QuestionSettings(BaseModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1, max_length=45)
    placeholder: str = Field("", max_length=100)
    style: Literal["short", "long"] = "short"
    required: bool = False
    min_length: int | None = Field(None, ge=0, le=4000)
    max_length: int | None = Field(None, ge=1, le=4000)
    value: str | None = Field(None, max_length=4000)
    custom_id: str | None = Field(None, max_length=100)
    row: int | None = Field(None, ge=0, le=4)

    @model_validator(mode="after")
    def _check_length_range(self) -> QuestionSettings:
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError(
                f"'min_length' ({self.min_length}) cannot exceed 'max_length' "
                f"({self.max_length})"
            )
        return self


class ContentFile(BaseModel):
    start_screen: StartScreenSettings


class QuestionsFile(BaseModel):
    question: list[QuestionSettings] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_unique_keys(self) -> QuestionsFile:
        keys = [q.key for q in self.question]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ValueError(f"duplicate question keys: {', '.join(duplicates)}")
        return self


class TicketSettings(BaseModel):
    category: int | None = Field(None, gt=0)
    name_prefix: str = Field(min_length=1)
    transcript_channel: int | None = Field(None, gt=0)

    @field_validator("category", "transcript_channel", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class ReviewBehaviorSettings(BaseModel):
    channel: int | None = Field(None, gt=0)
    ticket_buttons: bool = True


class ApplicationBehaviorSettings(BaseModel):
    role_id: int | None = Field(None, gt=0)
    require_deny_reason: bool = False
    send_copy: bool = True
    allow_delete: bool = True

    @field_validator("role_id", mode="before")
    @classmethod
    def _empty_role_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class StartScreenConfig(BaseModel):
    mode: Literal["review", "direct"] = "review"
    timezone: str = "UTC"
    review: ReviewBehaviorSettings
    ticket: TicketSettings
    application: ApplicationBehaviorSettings = Field(
        default_factory=ApplicationBehaviorSettings
    )

    @field_validator("timezone")
    @classmethod
    def _normalize_timezone(cls, value: str) -> str:
        normalized = value.upper()
        if not re.fullmatch(r"(?:UTC|Z|[+-]\d{2}:\d{2})", normalized):
            raise ValueError(
                "'timezone' must be 'UTC', 'Z', or a UTC offset like '+03:00'"
            )
        return "UTC" if normalized == "Z" else normalized

    @model_validator(mode="after")
    def _check_review_channel(self) -> StartScreenConfig:
        if self.mode == "review" and self.review.channel is None:
            raise ValueError("'channel' is required when mode is 'review'")
        return self


class BotConfig(BaseModel):
    start_screen: StartScreenConfig


class Settings(BaseModel):
    start_screen: StartScreenSettings
    questions: list[QuestionSettings]
    config: BotConfig

    @model_validator(mode="after")
    def _check_confirmation_placeholders(self) -> Settings:
        known_keys = {q.key for q in self.questions}
        placeholders = set(_PLACEHOLDER_RE.findall(self.start_screen.confirmation_message))
        unknown = placeholders - known_keys
        if unknown:
            raise ValueError(
                "'start_screen.confirmation_message' references unknown question keys: "
                f"{', '.join(sorted(unknown))}"
            )
        return self


def _read_toml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"config: missing file {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"config: invalid TOML in {path}: {exc}") from None


def load_settings() -> Settings:
    content = ContentFile.model_validate(_read_toml("content.toml"))
    questions_file = QuestionsFile.model_validate(_read_toml("questions.toml"))
    bot_config = BotConfig.model_validate(_read_toml("config.toml"))
    return Settings(
        start_screen=content.start_screen,
        questions=questions_file.question,
        config=bot_config,
    )
