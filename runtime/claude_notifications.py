"""Claude turn identities, with no transcript or tool content retained."""
ATTENTION={'permission_prompt','idle_prompt','elicitation_dialog','elicitation_url_dialog'}

def transition(previous,event):
    state=dict(previous)
    if state.get('session_id')!=event.session_id:
        if state and event.name not in {'SessionStart','UserPromptSubmit'}:
            return state,None
        state={'session_id':event.session_id,'counter':0}
    name=event.name
    if name=='SessionStart':
        return {'session_id':event.session_id,'counter':0},None
    if name=='UserPromptSubmit':
        counter=state.get('counter',0)+1
        return {'session_id':event.session_id,'counter':counter,'turn':event.turn_key or str(counter),'working':True},None
    if event.turn_key and state.get('turn') and event.turn_key!=state['turn']:
        return state,None
    if name=='SessionEnd':
        return {'session_id':event.session_id,'counter':state.get('counter',0),'ended':True},None
    if name in {'Interrupt','StopFailure'}:
        state.update(working=False,ended=True)
        return state,None
    if state.get('ended'):
        return state,None
    # PostToolUse/Failure confirm that the previous permission interaction is
    # over. They never reset completion identity for the current prompt.
    if name in {'PostToolUse','PostToolUseFailure'}:
        state.pop('attention_claims',None)
        return state,None
    if name=='Notification' and event.notification_type in ATTENTION:
        key=event.notification_key or event.notification_type
        claims=list(state.get('attention_claims',[]))
        if key in claims:
            return state,None
        state['attention_claims']=[*claims,key]
        return state,'attention'
    if name=='Stop' and state.get('working') and not event.background_running and not event.stop_hook_active:
        state['working']=False
        return state,'complete'
    return state,None
