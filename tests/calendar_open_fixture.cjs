// Synthetic public scripting harness. Never connects to Calendar or the desktop.
const fs = require('fs');
const vm = require('vm');
const [source, scenario, input] = process.argv.slice(2);
const p = JSON.parse(input);
if (scenario === 'recurring') p.event.recurring = true;
const counters = {shows:0};
const wanted = p.event;
const event = {
    uid:()=>scenario==='wrong-uid'?'wrong-id':p.calendar_item_id,
    summary:()=>wanted.title,
    startDate:()=>new Date(wanted.start),
    endDate:()=>new Date(scenario==='changed-date'?'2026-10-24T12:00:00Z':wanted.end),
    alldayEvent:()=>wanted.all_day,
    description:()=>wanted.notes+(scenario==='changed-notes'?' changed':''),
    location:()=>wanted.location,url:()=>wanted.url,recurrence:()=>'',
};
const captured = {};
const app = {
    calendars:{byId:id=>{
        captured.calendar_id=id;
        return {events:{byId:id=>{captured.item_id=id;return event;}}};
    }},
    show:selected=>{if(selected!==event) throw Error('Wrong object');counters.shows++;},
};
const context = {
    ObjC:{import:()=>{},unwrap:x=>x},
    $:{NSFileHandle:{fileHandleWithStandardInput:{readDataToEndOfFile:JSON.stringify(p)}},
       NSString:{alloc:{initWithDataEncoding:x=>x}},NSUTF8StringEncoding:4},
    Application:()=>app,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(source,'utf8'),context);
try {console.log(JSON.stringify({result:JSON.parse(context.run()),counters,captured}));}
catch(error) {console.log(JSON.stringify({error:String(error),counters,captured}));}
