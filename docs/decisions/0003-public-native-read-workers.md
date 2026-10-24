# 0003: Public Python native reads behind a bounded worker

Status: accepted, 22 October 2026.

## Evidence and decision

Dependency/network access is restored and PyObjC 12.2.2 installs successfully
on the pinned Python 3.15.1 interpreter. Replace the Calendar/Contacts scripting
branches with public EventKit/Contacts calls in a disposable Python child process.
Keep Mail's proven fixed Apple Events script and the typed Bridge protocol.

Calendar.app's scripting count/name/writability work, but its identifier getters
fail with native -10000/-1700. Contacts scripting repeatedly exceeds 15 seconds.
The Python Contacts API enumerates 613 visible contacts in 0.194 seconds for an
identifier-only probe, without restricted notes or contact mutations.

The worker keeps native objects behind narrow, public-selector stubs in
`typings/`. Results are validated domain models serialized to a strict reply.
The parent enforces the same deadline/output bound/cancellation/child-reaping
policy. No native frameworks are imported or permissions requested at MCP startup.

Calendar occurrence queries use public EventKit predicates in explicit selected
calendars/date bounds. Exact recurring occurrence reads require the listed start
instant. Return native/system-floating timezone provenance and all-day civil
dates with an exclusive end; do not assume all days are 24 hours. Return available
calendar source/subscription/writability fields and attendee identities/status.

Contacts use public unified-record enumeration with explicit requested keys,
bounded memory, deterministic identity-preserving pages, phone/email/name lookup
and postal addresses. Do not request notes. Full/limited authorization changes
the reported coverage; provider synchronization is outside that claim.

## Scope limitation

The first EventKit probe exposed one calendar under status 4, which was
incorrectly treated as full access. Apple defines 4 as write-only; 3 is full
access. After an explicit full-access grant, **18 calendars and 186 October
events** are readable, including recurring/all-day events. Write-only reads
now fail before enumeration and a regression test fixes this boundary.
Calendar.app reports 20 calendars, so all-account reconciliation remains open.
Selected visible-calendar completeness is separate from all-account coverage.

The desktop conversation has now directly called the registered Mail account,
mailbox, header-query and targeted-body tools. That establishes actual desktop
Mail access, independently of subprocess tests. Full Mail storage access is still
denied. The detached Codex server predates the ChatGPT restart and permission
change; it may need its own restart before its children inherit that change.

References: [PyObjC EventKit](https://pyobjc.readthedocs.io/en/latest/apinotes/EventKit.html),
[PyObjC Contacts](https://pyobjc.readthedocs.io/en/latest/apinotes/Contacts.html),
[Apple EventKit queries](https://developer.apple.com/documentation/eventkit/ekeventstore/events(matching:)).

Authorization reference: [Apple EKAuthorizationStatus](https://developer.apple.com/documentation/eventkit/ekauthorizationstatus).
