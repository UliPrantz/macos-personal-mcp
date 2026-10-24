// Fixed public Apple Events bridge. Request values are JSON argv, never source code.
// No send/make/set/delete/synchronize operations exist in this bridge.
function run(argv) {
    const op = argv[0], p = JSON.parse(argv[1]);
    const maxCandidates = 5000;
    function text(value) { return value === null || value === undefined ? '' : String(value); }
    // Envelope Index retains the RFC angle brackets; Mail's public messageId
    // omits one well-formed outer pair. Preserve every character inside it.
    function rfcIdentity(value) {
        if (typeof value !== 'string') throw Error('RFC Message-ID unavailable');
        if (/^<[^<>]+>$/.test(value)) return value.slice(1, -1);
        return value;
    }
    function identityFailure() {
        return JSON.stringify({code:'message_identity',
            message:'Message identity differs; search again before reading this message'});
    }
    function bounded(items) {
        if (items.length > maxCandidates) throw Error('Candidate limit; narrow the explicit scope');
        return items;
    }
    function exact(items, predicate) {
        const matches = items.filter(predicate);
        if (matches.length !== 1) throw Error('Selector absent or ambiguous');
        return matches[0];
    }
    function paged(items) {
        return {rows: items.slice(p.offset, p.offset + p.limit),
                next: p.offset + p.limit < items.length ? p.offset + p.limit : null};
    }
    if (op === 'permissions') {
        ObjC.import('EventKit'); ObjC.import('Contacts');
        return JSON.stringify({calendar: String($.EKEventStore.authorizationStatusForEntityType(0)),
                               contacts: String($.CNContactStore.authorizationStatusForEntityType(0))});
    }
    if (op.indexOf('mail_') === 0) {
        const app = Application('/System/Applications/Mail.app');
        if (op === 'mail_list_accounts') {
            return JSON.stringify({accounts: bounded(app.accounts()).map(a => ({
                id: a.id(), name: a.name(), emails: a.emailAddresses(), enabled: a.enabled()
            }))});
        }
        const account = p.account_id === '__local__' ? app :
            exact(app.accounts.whose({id:p.account_id})(), a => a.id() === p.account_id);
        if (op === 'mail_list_mailboxes') {
            const rows = [];
            function visit(parent, path) {
                if (path.length > 20) throw Error('Mailbox hierarchy too deep');
                bounded(parent.mailboxes()).forEach(box => {
                    const next = path.concat([box.name()]);
                    rows.push({path: next, unread_count: box.unreadCount()});
                    bounded(rows); visit(box, next);
                });
            }
            visit(account, []);
            return JSON.stringify({account_id: p.account_id, mailboxes: rows});
        }
        let box = account;
        p.mailbox_path.forEach(name => { box = exact(box.mailboxes.whose({name:name})(), b => b.name() === name); });
        function metadata(m) {
            return {local_id: m.id(), message_id: m.messageId(), subject: m.subject(),
                    sender: m.sender(), received_at: m.dateReceived().toISOString(), read: m.readStatus()};
        }
        if (op === 'mail_get_source') {
            const msg=box.messages.byId(p.local_id);
            if(rfcIdentity(msg.messageId()) !== rfcIdentity(p.expected_message_id)) return identityFailure();
            const before=msg.readStatus(), source=msg.source(), after=msg.readStatus();
            if(before !== after) throw Error('Observed read state change; no restoration attempted');
            if(rfcIdentity(msg.messageId()) !== rfcIdentity(p.expected_message_id)) return identityFailure();
            if(typeof source !== 'string' || source.length > (p.max_source_chars || 4000000)) return JSON.stringify({schema_version:1,ok:false,
                code:typeof source !== 'string' ? 'source_unavailable' : 'source_limit',
                message:'Complete RFC source unavailable or exceeds the explicit character bound; scope is incomplete',
                complete:false,external_effects_dispatched:false});
            return JSON.stringify({message_id:p.expected_message_id,source:source,read_before:before,read_after:after});
        }
        if (op === 'mail_get_message') {
            const msg = box.messages.byId(p.local_id);
            const identity = msg.messageId();
            if (rfcIdentity(identity) !== rfcIdentity(p.expected_message_id)) return identityFailure();
            const before = msg.readStatus(), body = msg.content(), headers = msg.allHeaders();
            if (typeof body !== 'string' || typeof headers !== 'string') throw Error('Body unavailable');
            const attachments = bounded(msg.mailAttachments()).map(a => ({
                id: a.id(), name: a.name(), approximate_bytes: a.fileSize()
            }));
            const after = msg.readStatus();
            if (before !== after) throw Error('Observed read state change; no restoration attempted');
            if (msg.messageId() !== identity) throw Error('RFC Message-ID changed during read');
            const characters = Array.from(body);
            return JSON.stringify({metadata: metadata(msg), body: characters.slice(0, p.body_chars).join(''),
                body_characters: characters.length, body_truncated: characters.length > p.body_chars,
                raw_headers: headers, attachments: attachments, read_before: before, read_after: after});
        }
        if (op !== 'mail_list_messages' && op !== 'mail_search_headers' && op !== 'mail_inventory') throw Error('Unsupported Mail operation');
        const terms = [{dateReceived: {_greaterThanEquals: new Date(p.since)}},
                       {dateReceived: {_lessThan: new Date(p.before)}}];
        if (p.unread_only) terms.push({readStatus: false});
        if (p.query.length) terms.push({_or: [{sender: {_contains: p.query}}, {subject: {_contains: p.query}}]});
        const selection=box.messages.whose({_and: terms});
        const ids = bounded(selection.id());
        let rows;
        if(op === 'mail_inventory') {
            const rfcs=selection.messageId(), subjects=selection.subject(), senders=selection.sender(),
                  dates=selection.dateReceived(), flags=selection.readStatus();
            if([rfcs,subjects,senders,dates,flags].some(a=>a.length !== ids.length) ||
               JSON.stringify(selection.id()) !== JSON.stringify(ids)) throw Error('Inventory changed during enumeration');
            rows=ids.map((id,i)=>({local_id:id,message_id:rfcs[i],subject:subjects[i],sender:senders[i],
                received_at:dates[i].toISOString(),read:flags[i]}));
        } else rows = ids.map(id => metadata(box.messages.byId(id)));
        rows.sort((a, b) => b.received_at.localeCompare(a.received_at) || b.local_id - a.local_id);
        const page = op === 'mail_inventory' ? {rows:rows,next:null} : paged(rows);
        return JSON.stringify({messages: page.rows, total_matches: rows.length, next_offset: page.next,
            observed_at: new Date().toISOString(), complete: true,
            scope: p.account_id + '/' + p.mailbox_path.join('/') + ' [' + p.since + ', ' + p.before + ')'});
    }
    if (op.indexOf('calendar_') === 0) {
        const app = Application('/System/Applications/Calendar.app'), calendars = bounded(app.calendars());
        if (op === 'calendar_list_calendars') {
            return JSON.stringify({calendars: calendars.map(c => ({id: c.uid(), name: c.name(), writable: c.writable()}))});
        }
        function event(c, e) {
            return {calendar_id: c.uid(), uid: e.uid(), title: text(e.summary()),
                start: e.startDate().toISOString(), end: e.endDate().toISOString(), all_day: e.alldayEvent(),
                location: text(e.location()), notes: text(e.description()), url: text(e.url()),
                recurrence: text(e.recurrence()), attendees: bounded(e.attendees()).map(a => ({
                    name: text(a.displayName()), email: text(a.email()), status: text(a.participationStatus())
                }))};
        }
        if (op === 'calendar_get_event') {
            const cal = exact(calendars, c => c.uid() === p.calendar_id);
            const e = exact(cal.events.whose({uid: p.event_uid})(), e => e.uid() === p.event_uid);
            return JSON.stringify(event(cal, e));
        }
        if (op !== 'calendar_list_events' && op !== 'calendar_search_events') throw Error('Unsupported Calendar operation');
        let rows = [];
        p.calendar_ids.forEach(id => {
            const cal = exact(calendars, c => c.uid() === id);
            const events = bounded(cal.events.whose({_and: [
                {startDate: {_lessThan: new Date(p.before)}}, {endDate: {_greaterThan: new Date(p.since)}}
            ]})());
            rows = rows.concat(events.map(e => event(cal, e))); bounded(rows);
        });
        const needle = p.query.toLowerCase();
        rows = rows.filter(e => [e.title, e.location, e.notes].some(v => v.toLowerCase().indexOf(needle) !== -1));
        rows.sort((a,b) => a.start.localeCompare(b.start) || a.calendar_id.localeCompare(b.calendar_id) || a.uid.localeCompare(b.uid));
        const page = paged(rows);
        return JSON.stringify({events: page.rows, total_matches: rows.length, next_offset: page.next});
    }
    if (op.indexOf('contacts_') === 0) {
        const app = Application('/System/Applications/Contacts.app');
        function contact(c) {
            function labeled(items) { return bounded(items).map(v => ({label: text(v.label()), value: text(v.value())})); }
            return {id: c.id(), name: text(c.name()), first_name: text(c.firstName()), last_name: text(c.lastName()),
                organization: text(c.organization()), job_title: text(c.jobTitle()),
                emails: labeled(c.emails()), phones: labeled(c.phones())};
        }
        if (op === 'contacts_get') {
            const matches = app.people.whose({id: p.contact_id})();
            return JSON.stringify(contact(exact(matches, c => c.id() === p.contact_id)));
        }
        if (op !== 'contacts_list' && op !== 'contacts_search') throw Error('Unsupported Contacts operation');
        let rows = bounded(app.people()).map(contact);
        const needle = p.query.toLowerCase();
        rows = rows.filter(c => [c.name, c.organization].concat(c.emails.map(e => e.value), c.phones.map(v => v.value))
            .some(v => v.toLowerCase().indexOf(needle) !== -1));
        rows.sort((a,b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
        const page = paged(rows);
        return JSON.stringify({contacts: page.rows, total_matches: rows.length, next_offset: page.next});
    }
    throw Error('Unsupported bridge operation');
}
