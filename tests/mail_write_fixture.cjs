// Synthetic public-scripting harness only; never connects to Mail or the desktop.
const fs = require('fs');
const vm = require('vm');
const [source, scenario, input] = process.argv.slice(2);
const p = JSON.parse(input);
const counters = {drafts:0,sends:0,replies:0};
let captured;
function recipients(initial=[]) {
    const values=initial.map(address=>({address}));
    const list=()=>values.slice();
    list.push=x=>values.push(x);
    list.address=()=>values.map(x=>x.address);
    list.remove=x=>values.splice(values.indexOf(x),1);
    return list;
}
function draft(data) {
    const suffix={'changed-content':' unreviewed signature','trailing-space':' ',
        'two-spaces':'  ','trailing-newline':'\n'}[scenario]||'';
    const content=()=>(scenario==='leading-newline'?'\n':'')+data.content+suffix;
    const attachments=()=>scenario==='inherited-attachment'?[{fileName:'/unreviewed/file'}]:
        scenario==='null-attachments'?null:[];
    attachments.push=x=>captured.attachments.push(x.fileName);
    content.attachments=attachments;
    captured={...data,to:[],cc:[],bcc:[],attachments:[]};
    const message={content,toRecipients:recipients(data.to),ccRecipients:recipients(data.cc),bccRecipients:recipients(data.bcc)};
    ['sender','subject','content'].forEach(key=>{
        Object.defineProperty(message,key,{get:()=>key==='content'?content:()=>data[key],set:value=>data[key]=value});
    });
    return message;
}
const original={messageId:()=>scenario==='stale-reply'?'other@example.test':
    scenario==='changed-reply'&&counters.replies?'changed@example.test':'original@example.test'};
const box={name:()=> 'Inbox',messages:{byId:id=>{if(id!==123)throw Error('Wrong local ID');return original;}}};
const boxes={whose:q=>()=>q.name==='Inbox'&&scenario!=='missing-mailbox'?[box]:[]};
const account={id:()=> 'account-1',enabled:()=>true,emailAddresses:()=>[p.sender],mailboxes:boxes};
const accounts=()=>Array.from({length:scenario==='ambiguous'?2:1},()=>account);
accounts.whose=q=>()=>q.id==='account-1'&&scenario!=='missing-account'?[account]:[];
const app={accounts,mailboxes:boxes,
    OutgoingMessage:draft,
    outgoingMessages:{push:()=>counters.drafts++},
    reply:(target,options)=>{
        if(target!==original||options.openingWindow||options.replyToAll)throw Error('Wrong reply');
        counters.replies++;counters.drafts++;
        return draft({sender:'inherited@example.test',subject:'Re: Original',content:'Quoted original',
            to:['inherited@example.test'],cc:['secret@example.test'],bcc:['hidden@example.test']});
    },
    delete:recipient=>{[latest.toRecipients,latest.ccRecipients,latest.bccRecipients].forEach(list=>{
        if(list().includes(recipient))list.remove(recipient);
    });},
    ToRecipient:x=>x,CcRecipient:x=>x,BccRecipient:x=>x,Attachment:x=>x,
    send:message=>{
        counters.sends++;
        captured.to=message.toRecipients.address();captured.cc=message.ccRecipients.address();captured.bcc=message.bccRecipients.address();
        captured.content=message.content();
        return true;
    }
};
let latest;
const construct=app.OutgoingMessage;app.OutgoingMessage=data=>(latest=construct(data));
const reply=app.reply;app.reply=(...args)=>(latest=reply(...args));
const context={ObjC:{import:()=>{},unwrap:x=>x},
    $:{NSFileHandle:{fileHandleWithStandardInput:{readDataToEndOfFile:input}},
       NSString:{alloc:{initWithDataEncoding:x=>x}},NSUTF8StringEncoding:4},
    Application:()=>app,Path:x=>x};
vm.createContext(context);vm.runInContext(fs.readFileSync(source,'utf8'),context);
try {console.log(JSON.stringify({result:JSON.parse(context.run()),counters,captured}));}
catch(error) {console.log(JSON.stringify({error:String(error),counters}));}
