# Current state

Updated: 25 October 2026. Version 0.3.1. The public release starts with one clean
initial commit under AGPL-3.0-only. The previous repository/history remains a
private archive; no old commit objects are pushed to the public repository.

## What works

- Native Mail account/mailbox discovery, scoped metadata/header search, exact
  message and RFC-source reads, combined subject/sender/body search.
- Public EventKit Calendar reads, recurring occurrence identities and selected
  writable-calendar event creation. Exact nonrecurring event opening is available.
- Public Contacts lookup and paged enumeration; restricted notes are excluded.
- Mail preparation/sending with attachments, selected-calendar creation and
  separate UI-open enablement. Native human review is the default for send/create;
  deliberate owner configuration can delegate consent to the host/model.
- One default search surface. Legacy FTS requires explicit startup opt-in and
  manual exact-scope maintenance; it is not silently mixed with native search.
- Human and agent installation guides, a README copy/paste prompt and an isolated
  installer. New installs expose 16 read tools; guarded profiles expose 19.

## Verification evidence

The release is based on the tested implementation, not a fresh unverified rewrite:

- **155 synthetic/protocol tests passed**, three live reads skipped by default.
  Ruff format/check, strict Pyright, wheel build/inspection, installer shell syntax
  and all three native script compilations passed. CI repeats the required checks.
- Separate opt-in Mail/Calendar/Contacts native read checks passed. Normal CI never
  reads anyone's live apps or sends messages/events.
- Actual desktop discovery showed the expected 19-tool guarded catalog, combined
  `native-mail-v2` search, native approval policy and working Mail/Calendar/Contacts
  access. Legacy/native aliases are absent from the default catalog.
- Actual desktop mixed-field search found the known dated message in **0.218 s**,
  searching 47 bodies with zero unavailable and 16 partial. A reversed phrase
  returned no match. A three-day negative searched **185 bodies** in **0.645 s**,
  zero unavailable and 57 partial; flags remained unchanged.
- Direct search-result selectors read the **820-character** message and
  **45,769-character** RFC source through desktop tools with unchanged observed
  flags. A malformed/changed RFC identity is rejected before content reads.
  The bridge accepts exactly one well-formed outer RFC angle-bracket pair; it
  does not strip whitespace, fold case or accept nested brackets.
- Earlier SDK weekly controls searched **401/401 locally readable bodies**, zero
  unavailable, 108 partial. Combined keyword/phrase/date/fuzzy/pagination and
  negative controls passed. These are local-text observations, not complete MIME
  or index recall guarantees.
- The measured archive contained roughly **42,600 physical records**. Native active
  identities covered 42,554; 236 missing/pending/identity exceptions were counted.
  A mixed query read 270/272 candidates, reporting two identity failures, 154
  partial bodies and 394 unsupported metadata records. These remain incomplete.
  Archive sender-only search took **0.632 s** without MIME reads; first indexed
  mixed query **5.394 s**, warm body control **2.459 s**.
- Native approval/cancellation, one specifically authorized controlled self-send,
  recipient/Sent state, delivered attachment bytes and selected-calendar creation
  were verified during pre-release development. No live effects are part of CI,
  normal installation or the public-release checks. No exactly-once delivery claim.

## Installation checks

A clean isolated runtime was installed in a checkout path containing spaces.
Pinned uv 0.13.5, Python 3.15.1 and locked dependencies installed locally. The
source-build toolchain fallback installed Rust 1.99.1 locally under a restricted
PATH; repeat installation reused the environment. No global runtime, shell profile,
MCP registration or privacy setting was changed by the installer.

A fresh official SDK client launched that executable from `/tmp`, discovered 16
read tools, rejected writes/old aliases and invalid input, then shut down cleanly.
The generated TOML parsed and pointed to the exact executable. This verifies a
clean environment on the maintainer's Mac; it is not proof on a pristine Mac
without Apple's Command Line Tools or on every macOS release.

## Known limits

- Account/mailbox scope is currently applied after the catalogue row bound and
  model validation. A small mailbox can therefore hit the 100,000-row global
  bound, and scoped reads do unnecessary work. SQL scope pushdown is recommended
  but not yet implemented; see the comparison below.
- Large native-index searches are validated only for macOS **26.5.2**, header 114
  and the observed LZ4 metadata profile. At most 500 unresolved body rows can be
  scanned directly without Spotlight. Unsupported profiles are not bypassed.
- `exhaustive` remains false. Partial files, absent bodies, unsupported records,
  lagging/changing checkpoints and bounded work can omit matches. A partial zero
  never proves absence. `execution_complete` means selected work finished.
- The universal two-second warm archive-search target is not met. Fuzzy search
  is bounded ASCII spelling similarity, not semantic search; broad distance-two
  expansion may hit a work limit.
- Calendar/Contacts visibility depends on OS grants and configured accounts;
  all-account reconciliation is not established. Event opening is limited to
  exact nonrecurring items. Visual display is separate from native acknowledgment.
- Calendar attendee/invitation creation is intentionally excluded. No provider
  API/OAuth, private attendee setter, screen automation or ICS substitute is added.
- Host approval policy, executor flags and OS privacy grants remain independent.
  No new permission or restart is needed for the maintainer's already verified
  desktop connection. New installations must verify their own actual host process.

## README usability and Mail MCP review

The README now leads with everyday workflows and the agent installation prompt.
Manual setup and optional writes remain fully available in expandable sections;
low-level contracts and configuration moved to TECHNICAL_DETAILS.md. The supported
OS profile and AI-app data boundary remain visible without expanding anything.

[The source comparison](MAIL_MCP_COMPARISON.md) covers all four requested Mail
MCPs plus Imdinu, Sift and MP Consulting at pinned revisions. None of the inspected
paths provided a simpler native full-body index interface. Several use owned
incremental FTS5 indexes and offer credible faster search designs. Their published
timings were reviewed, not reproduced on this Mac.

A separate read-only metadata experiment verified identical rows for a 69-row
mailbox: current catalogue loading took median 379.114 ms versus 9.142 ms for a
SQL-scoped prototype over 42,600 active rows (seven iterations). Known-ID lookup
was 0.017 ms; current archive header engine calls were 580.585 ms (five calls).
These exclude MCP transport and body search. The prototype is not a shipped
optimization. No competitor server was run, and no native writes were made.

Recommended next work is exact SQL scoping, measured inventory-cache improvements,
then an equivalent-workload FTS comparison before any architecture change. The
runtime remains 0.3.1 with the same search/approval behavior and single default
search surface. Documentation links and expandable README rendering are checked
for this update; runtime verification above remains the release evidence.

## Public release boundary

The owner explicitly approved public visibility, a single clean initial commit
and standard AGPLv3. The public tree includes source, synthetic tests, format
research and documentation; local native-data evidence, runtime environments,
credentials and old history are excluded. The pre-release 25-commit history was
scanned across 247 unique blobs: no credential-pattern findings, binary data or
Mail/Calendar/Contacts export files were found. This is an audit result, not a
claim of zero risk. A clean repository is used so old objects and Actions history
never become part of the public repository.

Commercial use is permitted under AGPLv3; it does not require royalties or a
usage report. The README's invitation to get in touch is voluntary. See LICENSE,
NOTICE, THIRD_PARTY.md and decision 0015. Maintain this file as behavior and
verification change; keep raw user data outside Git.
