"""App-only device authorization and a quote for one exact saved revision."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from threading import RLock
from decimal import Decimal

from . import video_director_delivery as delivery
from . import video_vidmuse as vidmuse
from .contracts import WCEError
from .own_connection_policy import atomic_write, locked, read_optional
from .prepared_contracts import strict_validate

TARGET = {key: {'type':'string','pattern':'^[a-f0-9]{32}$'}
          for key in ('project_id','work_id','scene_id','shot_id','revision_id')}
HANDLE = {'type':'string','pattern':'^[a-f0-9]{32}$'}
QUOTE_SECONDS = 180
BLOCKING = delivery.ACTIVE | {'SUBMIT_UNKNOWN'}


def action(name, **fields):
    return {'type':'object','additionalProperties':False,'required':['action',*fields],
            'properties':{'action':{'type':'string','const':name},**fields}}


def seal(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass(frozen=True)
class Plan:
    account: str
    route: vidmuse.Route
    cost: Decimal
    balance: Decimal
    body_sha256: str
    body: bytes
    summary: dict


class InsufficientCredits(WCEError):
    def __init__(self,cost,balance):
        self.data={'state':'INSUFFICIENT_CREDITS','estimate':str(cost),'balance':str(balance)}
        super().__init__('VIDMUSE_INSUFFICIENT_CREDITS')


class VidMusePanel:
    TOOL = 'wce.ui.video.vidmuse'
    SPEC = {'oneOf': [action(name) for name in ('status','install','device_start')] +
            [action(name,session=HANDLE) for name in ('device_finish','device_cancel')] +
            [action('quote',**TARGET),action('confirm',quote_id=HANDLE)]}

    def __init__(self, router):
        self.router = router
        self.jobs = router.jobs
        self.director = router.director
        self.cli = self.jobs.vidmuse
        self.guard = RLock()
        self.quotes = {}

    def tool(self):
        return {'name':self.TOOL,'title':'VidMuse MAGI-2 in Jiusera',
                'description':'Connect the official VidMuse CLI and read the live MAGI-2 catalog and balance. Only the Jiusera app may present and confirm a single exact-revision credit estimate.',
                'inputSchema':self.SPEC,'_meta':{'ui':{'visibility':['app']}},
                'annotations':{'readOnlyHint':False,'destructiveHint':False,'openWorldHint':True,'idempotentHint':False}}

    def run(self,args):
        strict_validate(args,self.SPEC)
        action = args['action']
        with self.guard:
            if action=='status':
                return self.status()
            if action=='install':
                self.cli.install()
                return self.status()
            if action.startswith('device_'):
                return self.device(action,args.get('session'))
            try:
                if action=='quote':
                    return self.quote({key:args[key] for key in TARGET})
                return self.confirm(args['quote_id'])
            except InsufficientCredits as error:
                return error.data

    def status(self):
        try:
            account=self.cli.account()
        except WCEError as error:
            return {'state':error.code.removeprefix('VIDMUSE_'),'models':[]}
        data={'account':account[-8:], 'models':[]}
        try:
            data['balance']=str(self.cli.credits())
        except WCEError:
            data['balance']=None
        try:
            data['models']=vidmuse.profile_projection(self.cli.catalog())
            self.cli.check_account(account)
        except WCEError as error:
            return data|{'state':error.code.removeprefix('VIDMUSE_'),'models':[]}
        return data|{'state':'CONNECTED'}

    def device(self,action,session):
        self.cli.binary()
        stamp=self.cli.root/'jiusera-device-state.json'
        with locked(self.cli.root/'jiusera-device.lock'):
            previous=read_optional(stamp)
            if action=='device_start':
                login=self.cli.device_start()
                session=token_hex(16)
                atomic_write(stamp,{'session':session,'expires':self.cli.clock()+300})
                return {'state':'AWAITING_APPROVAL','session':session,**login}
            if not previous or previous['session']!=session or self.cli.clock()>=previous['expires']:
                return {'state':'DEVICE_EXPIRED'}
            if action=='device_cancel':
                # Stops Jiusera from completing a cancelled flow. The provider owns the challenge lifetime.
                stamp.unlink()
                return {'state':'DEVICE_CANCELLED'}
            try:
                self.cli.device_finish()
            except WCEError as error:
                if error.code in ('VIDMUSE_AUTH_REQUIRED','VIDMUSE_AUTH_PENDING'):
                    return {'state':'AWAITING_APPROVAL'}
                raise
            stamp.unlink()
        self.quotes.clear()
        return self.status()

    def latest(self,target):
        root,pin=self.director.project(target['project_id'])
        location=self.director.storage(root,pin)
        state=self.director.load(target['project_id'],location)
        work=state['works'].get(target['work_id'])
        vidmuse.require(work, 'DIRECTOR_WORK_NOT_FOUND')
        records=[]
        for attempt,binding in work.get('generations',{}).items():
            if binding.get('provider') != vidmuse.PROVIDER or not all(
                    binding.get(key)==target[key] for key in ('scene_id','shot_id','revision_id')):
                continue
            row=delivery.read_receipt(self.jobs,attempt,target['project_id'])
            # A persisted canvas bind may precede the first successful receipt write.
            records.append((row['created_at'] if row else 0,attempt,row['state'] if row else 'SUBMIT_UNKNOWN'))
        return max(records,key=lambda row:(row[2] in BLOCKING,row[0],row[1]),default=None)

    def plan(self,target,folder,*,stage=False):
        from .video_director_media import compute_request, source_image

        root,pin=self.director.project(target['project_id'])
        context=self.director.context(target)
        configuration=context['revision'].get('configuration',{})
        vidmuse.require(configuration.get('provider')==vidmuse.PROVIDER and
                        configuration.get('model')==vidmuse.MODEL,'VIDMUSE_MODEL_CHANGED')
        vidmuse.require(context['head_revision']==target['revision_id'],'VIDMUSE_REVISION_CHANGED')
        request=compute_request(self.jobs,context,root,folder)
        account=self.cli.account()
        candidates=[route for route in self.cli.catalog() if route.has(configuration) and
                    len(request['inputs'])<=route.references]
        vidmuse.require(len(candidates)==1, 'VIDMUSE_PARAMETERS_UNAVAILABLE' if not candidates else 'VIDMUSE_MODEL_AMBIGUOUS')
        route=candidates[0]
        images=[item['file'] for item in request['inputs']]
        logical=route.body(configuration,request['prompt'],['sha256:'+item['sha256'] for item in images])
        cost=route.estimate(logical)
        balance=self.cli.credits()
        self.cli.check_account(account)
        if cost>balance:
            raise InsufficientCredits(cost,balance)
        vidmuse.require((root,pin)==self.director.project(target['project_id']),'DIRECTOR_PROJECT_CHANGED')
        paths=[]
        if stage:
            for index,item in enumerate(images):
                mime,data=source_image(root,item,folder)
                suffix={'image/png':'.png','image/jpeg':'.jpg'}.get(mime)
                vidmuse.require(suffix,'VIDEO_FRAME_INVALID')
                path=folder/('reference-'+str(index+1)+suffix)
                with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as handle:
                    handle.write(data)
                paths.append(str(path))
        body=json.dumps(route.body(configuration,request['prompt'],paths),ensure_ascii=False,separators=(',',':')).encode()
        return Plan(account,route,cost,balance,seal(logical),body,
                    {'model':vidmuse.MODEL,'model_name':route.name,'duration':configuration['duration'],
                     'ratio':configuration['ratio'],'resolution':configuration['resolution'],
                     'audio':configuration.get('audio',False),'mode':configuration['mode'],
                     'references':len(images),'account':account[-8:],'shot':context['revision']['title']})

    def quote(self,target):
        latest=self.latest(target)
        if latest and latest[2] in BLOCKING:
            return {'state':'ORIGINAL_ATTEMPT','attempt_id':latest[1],'attempt_state':latest[2]}
        now=self.cli.clock()
        self.quotes={key:value for key,value in self.quotes.items() if value['expires']>now}
        if len(self.quotes)>=32:
            self.quotes.pop(next(iter(self.quotes)))
        self.jobs._directory()
        with TemporaryDirectory(prefix='.vidmuse-quote-',dir=self.jobs.root) as folder:
            plan=self.plan(target,Path(folder))
        quote_id=token_hex(16)
        self.quotes[quote_id]={'target':target,'plan':plan,'latest':latest,'expires':now+QUOTE_SECONDS}
        return {'state':'QUOTED','quote_id':quote_id,'estimate':str(plan.cost),'balance':str(plan.balance),
                **plan.summary}

    def confirm(self,quote_id):
        from .video_director_generation import submit

        quote=self.quotes.get(quote_id)
        vidmuse.require(quote and quote['expires']>self.cli.clock(),'VIDMUSE_QUOTE_EXPIRED')
        target,old=quote['target'],quote['plan']
        attempt='vidmuse-'+quote_id
        if previous:=delivery.read_receipt(self.jobs,attempt,target['project_id']):
            return self.receipt(previous)
        def guard():
            vidmuse.require(self.latest(target)==quote['latest'],'VIDMUSE_ORIGINAL_ATTEMPT_CHANGED')
        guard()
        with TemporaryDirectory(prefix='.vidmuse-submit-',dir=self.jobs.root) as folder:
            plan=self.plan(target,Path(folder),stage=True)
            vidmuse.require((plan.account,plan.route.name,plan.cost,plan.body_sha256)==
                            (old.account,old.route.name,old.cost,old.body_sha256),'VIDMUSE_QUOTE_CHANGED')
            vidmuse.require(quote['expires']>self.cli.clock(),'VIDMUSE_QUOTE_EXPIRED')
            row=submit(self.router,target|{'generation_attempt_id':attempt},
                       vidmuse_plan=plan,vidmuse_previous=guard)
        return self.receipt(row)

    @staticmethod
    def receipt(row):
        return {'state':row['state'],'attempt_id':row['generation_attempt_id'],
                'task_id':row.get('provider_task_id')}
