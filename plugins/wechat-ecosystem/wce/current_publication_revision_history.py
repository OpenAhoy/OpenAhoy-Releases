"""Targeted continuation evidence, without entering RevisionStore or Store.read."""
from copy import deepcopy
import json
from .contracts import WCEError
from .service import digest


def _hold():
    raise WCEError('DRAFT_REVISION_PENDING_ADOPTION_HOLD')


def extend(store, old_events, proposal_sha, anchor, guard):
    """Read bounded per-handle events; returned facts do not grant authority."""
    from .current_publication_continuation import ContinuationIndex
    if type(old_events) is not list or not old_events or not callable(guard):
        _hold()
    index=ContinuationIndex(store)
    with index._db(readonly=True) as (db,identity):
        db.execute('BEGIN')
        head=index._head(db,identity,recover=False)
        index._check_old_index(db,index._meta(db,identity))
        cutoff=head['seq'] if anchor is None else anchor.get('sequence')
        if type(cutoff) is not int or not 1<=cutoff<=head['seq']:
            _hold()
        terminal=db.execute('SELECT event_sha FROM events WHERE seq=?',(cutoff,)).fetchone()
        if terminal is None or (anchor is not None and terminal['event_sha']!=anchor.get('sha256')):
            _hold()
        proposal=db.execute('SELECT handle,event_seq FROM legacy_revision_proposals WHERE proposal_sha=?',(proposal_sha,)).fetchone()
        if proposal is None or proposal['event_seq']>cutoff:
            _hold()
        handle=proposal['handle'];base=old_events[-1]['value']
        row=base.get('targets',{}).get(handle)
        if row is None:
            version=db.execute('SELECT * FROM intent_versions WHERE handle=? ORDER BY event_seq LIMIT 1',(handle,)).fetchone()
            if version is None:
                _hold()
            row=json.loads(version['row_json'])
            saved=db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(version['event_seq'],)).fetchone()
            if saved is None:
                _hold()
            event=json.loads(saved['event_json'])
            if digest(row)!=version['row_sha'] or digest(event)!=saved['event_sha'] or event.get('targets',{}).get(handle)!=version['row_sha']:
                _hold()
        view={'account_key':index.account,'targets':{handle:deepcopy(row)}}
        fields=('revision_pending_images','revision_pending_baselines','revision_pending_uploads')
        for field in fields:
            initial=base.get(field,{})
            if type(initial) is not dict:
                _hold()
            view[field]={handle:deepcopy(initial[handle])} if handle in initial else {}
        output=list(old_events)
        links=db.execute('SELECT event_seq,event_sha FROM legacy_revision_events WHERE handle=? AND event_seq<=? ORDER BY event_seq',(handle,cutoff))
        for link in links:
            guard()
            saved=db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(link['event_seq'],)).fetchone()
            if saved is None:
                _hold()
            event=json.loads(saved['event_json'])
            if digest(event)!=saved['event_sha'] or saved['event_sha']!=link['event_sha'] or event.get('kind')!='LEGACY_BATCH':
                _hold()
            for change in event.get('deltas',[]):
                field,key=change.get('field'),change.get('key')
                if field not in fields:
                    continue
                if key is None:
                    old=change.get('old') or {};new=change.get('new')
                    if type(old) is not dict or type(new) is not dict:
                        _hold()
                    was=old.get(handle);now=new.get(handle);old_present=handle in old;new_present=handle in new
                elif key==handle:
                    was=change.get('old');now=change.get('new');old_present=change.get('old_present');new_present=True
                else:
                    continue
                if (handle in view[field])!=old_present or view[field].get(handle)!=was or not new_present:
                    _hold()
                view[field][handle]=deepcopy(now)
            # Bind the synthetic projection to the exact persisted delta event.
            output.append({'value':deepcopy(view),'previous_sha256':saved['event_sha']})
        if view['revision_pending_images'].get(handle,{}).get('proposal_sha256')!=proposal_sha:
            _hold()
        guard();index._head(db,identity,recover=False);db.execute('COMMIT')
        return output,cutoff,terminal['event_sha'],handle,view
