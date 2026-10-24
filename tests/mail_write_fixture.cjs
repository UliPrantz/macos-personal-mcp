// Synthetic public-scripting harness only; never connects to Mail or the desktop.
const fs = require('fs');
const vm = require('vm');
const [source, scenario, input] = process.argv.slice(2);
const p = JSON.parse(input);
const counters = {drafts:0,sends:0};
let captured;
function recipients() {
    const values=[];
    return {push:x=>values.push(x),address:()=>values.map(x=>x.address)};
}
const app={
    accounts:()=>Array.from({length:scenario==='ambiguous'?2:1},()=>({enabled:()=>true,emailAddresses:()=>[p.sender]})),
    OutgoingMessage:data=>{
        const content=()=>data.content+(scenario==='changed-content'?' unreviewed signature':'');
        content.attachments={push:x=>{captured.attachments.push(x.fileName);}};
        captured={...data,to:[],cc:[],bcc:[],attachments:[]};
        const to=recipients(),cc=recipients(),bcc=recipients();
        return {sender:()=>data.sender,subject:()=>data.subject,content,toRecipients:to,ccRecipients:cc,bccRecipients:bcc};
    },
    outgoingMessages:{push:()=>counters.drafts++},
    ToRecipient:x=>x,CcRecipient:x=>x,BccRecipient:x=>x,Attachment:x=>x,
    send:message=>{
        counters.sends++;
        captured.to=message.toRecipients.address();
        captured.cc=message.ccRecipients.address();
        captured.bcc=message.bccRecipients.address();
        return true;
    }
};
const context={
    ObjC:{import:()=>{},unwrap:x=>x},
    $:{NSFileHandle:{fileHandleWithStandardInput:{readDataToEndOfFile:input}},
       NSString:{alloc:{initWithDataEncoding:x=>x}},NSUTF8StringEncoding:4},
    Application:()=>app,Path:x=>x
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(source,'utf8'),context);
try {console.log(JSON.stringify({result:JSON.parse(context.run()),counters,captured}));}
catch(error) {console.log(JSON.stringify({error:String(error),counters}));}
