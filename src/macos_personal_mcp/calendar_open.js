// Public native show only. No event mutation, invitation or app-launch fallback.
ObjC.import('Foundation');
function run() {
    const input = $.NSFileHandle.fileHandleWithStandardInput.readDataToEndOfFile;
    const p = JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding(input, $.NSUTF8StringEncoding)));
    const app = Application('/System/Applications/Calendar.app');
    const wanted = p.event;
    if (wanted.recurring) throw Error('Exact recurring occurrence opening unavailable');
    // Calendar may resolve event IDs globally regardless of the container selector.
    // Public EventKit has already checked the exact selected calendar. Compare the
    // globally unique calendarItemIdentifier itself, never title alone or RFC UID.
    const event = app.calendars.byId(wanted.calendar_id).events.byId(p.calendar_item_id);
    function value(v) { return v === null || v === undefined ? '' : String(v); }
    if (event.uid() !== p.calendar_item_id || event.summary() !== wanted.title ||
        event.startDate().toISOString() !== new Date(wanted.start).toISOString() ||
        event.endDate().toISOString() !== new Date(wanted.end).toISOString() ||
        event.alldayEvent() !== wanted.all_day || value(event.description()) !== wanted.notes ||
        value(event.location()) !== wanted.location || value(event.url()) !== wanted.url ||
        value(event.recurrence()) !== '') throw Error('Native selected item changed or differs');
    app.show(event);
    return JSON.stringify({calendar_item_id:p.calendar_item_id,show_acknowledged:true});
}
