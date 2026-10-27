// Fixed public Mail scripting executor. Only called after independent native
// human approval, attachment snapshotting and durable dispatch intent.
ObjC.import('Foundation');
function run() {
    const input = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
    const p = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding(input, $.NSUTF8StringEncoding)));
    const app = Application('/System/Applications/Mail.app');
    const accounts = app.accounts().filter(a => a.enabled() &&
        a.emailAddresses().some(v => v.toLowerCase() === p.sender.toLowerCase()));
    if (accounts.length !== 1) throw Error('Sender absent or ambiguous');
    let message;
    if (p.reply_to_message) {
        const t = p.reply_to_message;
        function exact(items, predicate) {
            const matches = items.filter(predicate);
            if (matches.length !== 1) throw Error('Reply selector absent or ambiguous');
            return matches[0];
        }
        function identity(value) {
            if (typeof value !== 'string') throw Error('RFC Message-ID unavailable');
            return /^<[^<>]+>$/.test(value) ? value.slice(1,-1) : value;
        }
        let box = t.account_id === '__local__' ? app :
            exact(app.accounts.whose({id:t.account_id})(), a => a.id() === t.account_id);
        t.mailbox_path.forEach(name => {
            box = exact(box.mailboxes.whose({name:name})(), b => b.name() === name);
        });
        const original = box.messages.byId(t.local_id);
        if (identity(original.messageId()) !== identity(t.expected_message_id)) {
            return JSON.stringify({accepted:false,failure_code:'native_reply_identity'});
        }
        message = app.reply(original,{openingWindow:false,replyToAll:false});
        if (identity(original.messageId()) !== identity(t.expected_message_id)) {
            return JSON.stringify({accepted:false,failure_code:'native_reply_identity'});
        }
        // Native reply supplies threading metadata. Never inherit recipients
        // or quoted text as approved content.
        [message.toRecipients,message.ccRecipients,message.bccRecipients].forEach(list => {
            list().forEach(recipient => app.delete(recipient));
        });
        message.sender = p.sender;
        message.subject = p.subject;
        message.content = p.body;
        message.visible = false;
        // Mail returns null for an empty attachment collection on this path.
        const inherited = message.content.attachments();
        if (inherited !== null && (!Array.isArray(inherited) || inherited.length !== 0)) {
            return JSON.stringify({accepted:false,failure_code:'native_message_changed'});
        }
    } else {
        message = app.OutgoingMessage({sender:p.sender, subject:p.subject, content:p.body, visible:false});
        app.outgoingMessages.push(message);
    }
    p.to.forEach(v => message.toRecipients.push(app.ToRecipient({address:v})));
    p.cc.forEach(v => message.ccRecipients.push(app.CcRecipient({address:v})));
    p.bcc.forEach(v => message.bccRecipients.push(app.BccRecipient({address:v})));
    function same(values, expected) {
        return JSON.stringify(values.map(v => v.toLowerCase()).sort()) ===
               JSON.stringify(expected.map(v => v.toLowerCase()).sort());
    }
    // Mail may append one ASCII space when materializing an outgoing rich-text
    // body. Permit only that observed artifact, not trimming or other changes.
    const body = message.content();
    const sameBody = body === p.body || body === p.body + ' ';
    if (message.sender() !== p.sender || message.subject() !== p.subject || !sameBody ||
        !same(message.toRecipients.address(),p.to) || !same(message.ccRecipients.address(),p.cc) ||
        !same(message.bccRecipients.address(),p.bcc)) {
        return JSON.stringify({accepted:false,failure_code:'native_message_changed'});
    }
    p.attachments.forEach(v => message.content.attachments.push(app.Attachment({fileName:Path(v)})));
    return JSON.stringify({accepted:app.send(message) === true});
}
