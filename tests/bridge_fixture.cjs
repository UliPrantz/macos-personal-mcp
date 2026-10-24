// Synthetic native app; evaluating the production bridge must never reach macOS.
const fs = require('node:fs');
const vm = require('node:vm');
const [sourcePath, scenario, operation, payload] = process.argv.slice(2);
const counters = {body: 0, headers: 0};
const identity = 'synthetic-id@example.test';
const message = {
    id: () => 12, messageId: () => identity, subject: () => 'Synthetic subject',
    sender: () => 'sender@example.test', dateReceived: () => new Date('2026-10-16T17:10:10Z'),
    readStatus: () => scenario === 'flags-changed' && counters.body > 0,
    content: () => {counters.body++; return 'Unicode café 🐈 body only needle ' + 'z'.repeat(10000);},
    allHeaders: () => {counters.headers++; return 'Message-ID: <' + identity + '>\r\nTo: Test <recipient@example.test>\r\n';},
    source: () => {counters.body++;return 'Message-ID: <'+identity+'>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nComplete raw source body';},
    mailAttachments: () => [],
};
let capturedFilter;
const messages = {
    byId: () => message,
    whose: filter => {capturedFilter = filter; return {
        id: () => scenario === 'negative' ? [] : [12], messageId:()=>[identity],subject:()=>['Synthetic subject'],
        sender:()=>['sender@example.test'],dateReceived:()=>[new Date('2026-10-16T17:10:10Z')],readStatus:()=>[false],
    };},
};
const box = {name: () => 'Inbox', messages, mailboxes: () => [], unreadCount: () => 1};
const account = {id: () => 'synthetic', name: () => 'Fixture', emailAddresses: () => ['sender@example.test'],
                 enabled: () => true, mailboxes: () => [box]};
account.mailboxes.whose=filter=>()=>filter.name===box.name()?[box]:[];
const accounts=()=>[account];
accounts.whose=filter=>()=>filter.id===account.id()?[account]:[];
const sandbox = {Application: () => ({accounts}), Date, JSON};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), sandbox);
try {
    const result = JSON.parse(sandbox.run([operation, payload]));
    process.stdout.write(JSON.stringify({result, counters, capturedFilter}));
} catch (error) {
    process.stdout.write(JSON.stringify({error: error.message, counters, capturedFilter}));
}
