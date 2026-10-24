from datetime import UTC, date, datetime

import EventKit as EK
import pytest

from macos_personal_mcp.models import Contact, ContactsScope
from macos_personal_mcp.native_worker import local_dates, require_calendar_read, selected_page
from macos_personal_mcp.process import NativeError


def test_write_only_calendar_authorization_cannot_claim_read_coverage() -> None:
    with pytest.raises(NativeError, match="Full Calendar read access"):
        require_calendar_read(EK.EKAuthorizationStatusWriteOnly)
    require_calendar_read(EK.EKAuthorizationStatusFullAccess)


def test_all_day_civil_range_handles_london_25_hour_day() -> None:
    start = datetime(2026, 10, 24, 23, tzinfo=UTC)
    end = datetime(2026, 10, 26, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 25 * 3600
    assert local_dates(start, end, "Europe/London") == (date(2026, 10, 25), date(2026, 10, 26))


def test_contact_pagination_preserves_same_name_identities() -> None:
    contacts = [
        Contact(
            id=identifier,
            name="Same Name",
            first_name="Same",
            last_name="Name",
            organization="",
            job_title="",
            emails=[],
            phones=[],
        )
        for identifier in ["first", "second", "third"]
    ]
    first, continuation = selected_page(contacts, ContactsScope(limit=2))
    assert [c.id for c in first] == ["first", "second"] and continuation == 2
    last, continuation = selected_page(contacts, ContactsScope(offset=2, limit=2))
    assert [c.id for c in last] == ["third"] and continuation is None
