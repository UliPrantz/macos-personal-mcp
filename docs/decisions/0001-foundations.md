# 0001: Python, desktop-launched STDIO, explicit local state

Status: accepted project direction, 22 October 2026. Runtime not implemented.

Invitation/provider investigation options in this original decision are superseded
by [decision 0008](0008-native-only-scope-without-invitations.md): attendee creation
and direct provider integrations are now explicitly outside scope.

## Decision

Build a new Python project with one local STDIO MCP entry point. The native
desktop client launches and owns the process. Keep every feature request-driven;
no HTTP server, tunnels, scheduled email or autonomous indexing service.

The application runtime and native adapters are Python. Start with Python 3.15.1,
uv and the official stable MCP Python SDK. Check current SDK/client protocol
compatibility instead of pinning an untested SDK major version by assumption.
Quality tools do not imply a Node application runtime.

Use public native APIs where they work. Prefer PyObjC for Contacts/EventKit and
investigate ScriptingBridge/Apple Events for Mail. Existing JXA probes provide
measured behavior to reproduce, not production architecture to inherit.

Allow a persistent, owner-only local search index. Rebuilding/updating it is an
explicit bounded operation with progress and resumability, not a background
service. Also allow a small operation-outcome journal for risky writes. These
files must survive process restarts, remain outside the checkout, and be removable
through documented local commands. No message content belongs in Git.

Separate immutable-source read tools, cache maintenance, local calendar writes,
and external communications. MCP annotations describe effects; the client owns
its approval policy. Do not represent hints as guaranteed authorization.

## Why

This matches the installed WhatsApp MCP lifecycle, avoids service startup
dependencies, and preserves fast repeat queries without rescanning every body.
The actual WhatsApp implementation uses a readable SQLite cache. Mail directory
access was denied in earlier tests, so its indexing route still needs proof.

Sending and invitations can disclose data. Approval must cover the concrete
payload/recipients, and uncertain sends must not be retried blindly.

## Capability gates

Fast complete body search is a product requirement; fast scoped header search
does not satisfy it. A usable source/index with demonstrated coverage is needed.

Reading/creating an EventKit event does not imply invitation support. EventKit
cannot add participants; the installed Calendar attendee properties are read-only.
Investigate supported scripting/provider routes separately. Do not use private
setters or claim an emailed ICS file equals a fully managed organizer invitation.

## Consequences

"No daemon" does not mean "zero files on disk" or "a new process per call".
Initial indexing can be expensive, but a connected idle server must do no scans.
Unsupported capabilities must fail clearly; they cannot be represented by fake
successes, empty placeholder lists, or an unannounced reduced feature set.
