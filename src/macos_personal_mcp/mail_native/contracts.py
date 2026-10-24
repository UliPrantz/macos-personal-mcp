"""Unified native Mail search, distinct from opt-in legacy FTS5 semantics."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from macos_personal_mcp.models import Model, Page, Text

SearchField = Literal["subject", "sender", "body"]


class NativeSearch(Page):
    query: str = Field(min_length=1, max_length=500)
    since: AwareDatetime | None = None
    before: AwareDatetime | None = None
    account_id: Text | None = None
    mailbox_path: list[Text] | None = Field(default=None, min_length=1, max_length=20)
    unread_only: bool = False
    fuzzy_distance: int = Field(default=0, ge=0, le=2)
    search_fields: list[SearchField] = Field(
        default_factory=lambda: ["subject", "sender", "body"], min_length=1, max_length=3
    )
    snapshot: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def valid_scope(self) -> Self:
        if len(set(self.search_fields)) != len(self.search_fields):
            raise ValueError("Search fields must be unique")
        if self.since is not None and self.before is not None and self.before <= self.since:
            raise ValueError("Require since < before")
        if self.mailbox_path is not None and self.account_id is None:
            raise ValueError("A mailbox path requires an account ID")
        if self.fuzzy_distance and (
            not self.query.isascii() or not self.query.isalnum() or not 4 <= len(self.query) <= 40
        ):
            raise ValueError("Fuzzy search requires one ASCII alphanumeric word of length 4-40")
        if self.offset and self.snapshot is None:
            raise ValueError("Continuation requires the previous snapshot")
        return self


class NativeMatch(Model):
    local_id: int
    message_id: str | None
    account_id: str
    mailbox_path: list[str]
    subject: str
    sender: str
    received_at: AwareDatetime
    read: bool
    matched_fields: list[SearchField] = Field(default_factory=lambda: list[SearchField]())
    excerpt: str | None = Field(default=None, max_length=320)
    excerpt_field: SearchField | None = None


class NativeSearchResult(Model):
    version: Literal["native-mail-v2"] = "native-mail-v2"
    backend: Literal["catalogue-only", "direct-mime", "native-spotlight"]
    search_fields: list[SearchField]
    fuzzy_distance: int = 0
    matched_spellings: list[str] = Field(default_factory=list)
    matches: list[NativeMatch]
    total_matches: int
    next_offset: int | None
    snapshot: str
    catalogue_messages: int
    searched_headers: int
    header_matches: int
    native_covered: int
    exception_messages: int
    candidate_messages: int
    searched_bodies: int
    unavailable_bodies: int
    partial_bodies: int
    unsearched_candidates: int
    error_counts: dict[str, int]
    execution_complete: bool
    exhaustive: bool = False
    flags_unchanged: bool
    observed_at: AwareDatetime
    elapsed_ms: float
    semantics: str = "Unicode NFC casefolded tokens AND across selected fields; each quoted phrase stays within one field and preserves normalized word order, punctuation and whitespace. Accents preserved. Excerpts are normalized text; matched_fields are observed supporting fields, not every possible matching field. Newest received first; dates lower inclusive, upper exclusive. Optional single-word ASCII fuzzy spelling distance 1-2; no Boolean operators, stemming or semantic search."
    coverage_note: str = "Header-proven matches need no body read. Native indexing and local MIME availability can omit other matches. Partial zero means no match in the searched data. candidate_messages counts selected body candidates; searched_headers and header_matches report metadata work separately. Checkpoint observations are guarded, not a proven atomic snapshot or Mail rendering parity."
