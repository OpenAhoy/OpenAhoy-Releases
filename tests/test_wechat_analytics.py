from datetime import datetime, date
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest import TestCase
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'))
from wce.contracts import Secret, WCEError
from wce.http_transport import HTTPRequest, HTTPResponse, HTTPSender
from wce import wechat_analytics as analytics
from wce.own_connection_tools import ConnectionRouter, validate
from wce.own_settings_protocol import SettingsRouter

OAUTH = Secret('test-not-a-production-secret')


class Tokens:
    reads = 0
    def get(self, guard):
        guard()
        self.reads += 1
        return SimpleNamespace(token=OAUTH, wall_deadline=time.time()+300)

    def valid(self, value):
        return value.token is OAUTH


def reply(data, code=200):
    return HTTPResponse(code,json.dumps(data).encode())


class Sender:
    def __init__(self, readers=110, denied=None):
        self.requests=[]
        self.readers=readers
        self.denied=denied

    def send(self, request, timeout):
        path=urlsplit(request.path).path.split('/')[-1]
        values=json.loads(request.body)
        first=date.fromisoformat(values['begin_date'])
        last=date.fromisoformat(values['end_date'])
        length=(last-first).days+1
        self.requests.append((path,first,last))
        assert 0<length<=analytics.WINDOWS[path]
        assert request.method=='POST' and 0<timeout<=8
        if path==self.denied:
            return reply({'errcode':48001,'errmsg':'not authorized'})
        rows=[]
        for i in range(length):
            day=(first+i*analytics.DAY).isoformat()
            if path==analytics.FANS:
                rows.extend([{'ref_date':day,'user_source':0,'new_user':0,'cancel_user':0},
                             {'ref_date':day,'user_source':1,'new_user':3,'cancel_user':2}])
            if path==analytics.TOTAL:
                rows.append({'ref_date':day,'cumulate_user':self.readers})
            if path==analytics.CONTENT:
                rows.append({'ref_date':day,'detail':{'read_user':self.readers,'share_user':0,
                            'collection_user':4,'send_page_count':1}})
            if path==analytics.ARTICLE:
                rows.append({'ref_date':day,'title':'Verified example','content_url':'https://mp.weixin.qq.com/s/known',
                            'detail_list':[{'stat_date':day,'read_user':7,'read_finish_rate':0.3,
                                            'read_avg_activetime':1.125,'share_user':0,
                                            'read_user_source':[{'scene_desc':'全部','user_count':7}]}]})
        return reply({'list':rows,'is_delay':'false'})


class AnalyticsTest(TestCase):
    def make(self, sender=None, hour=10):
        transport=sender or Sender()
        clock=lambda:datetime(2026,11,19,hour,15,tzinfo=analytics.BEIJING)
        return analytics.Analytics(Tokens(),transport,clock)

    def query(self, reader, cid='account-one', days=7, refresh=False):
        return reader.read(cid,days,refresh,lambda:None,time.monotonic()+8)

    def test_summary_7_to_30_refresh_and_account_isolation(self):
        first=self.make()
        second=self.make(Sender(405))
        small=self.query(first)
        self.assertEqual((small['start'],small['end']),('2026-11-12','2026-11-18'))
        self.assertTrue(all(r['new_user']==3 and r['cancel_user']==2 and r['share_user']==0 for r in small['timeline']))
        count=len(first.sender.requests)
        self.assertEqual(self.query(first),small)
        self.assertEqual(len(first.sender.requests),count)
        self.assertEqual(first.tokens.reads,1)
        large=self.query(first,days=30)
        self.assertEqual(len(large['timeline']),30)
        self.assertTrue(all(last<date(2026,11,12) for path,start,last in first.sender.requests[count:]))
        self.assertEqual(self.query(second,'account-two')['timeline'][-1]['read_user'],405)
        self.assertEqual(self.query(first)['timeline'][-1]['read_user'],110)
        first.sender.readers=66
        self.assertEqual(self.query(first,refresh=True)['timeline'][-1]['read_user'],66)
        self.assertEqual(len(small['articles']),4)
        self.assertEqual(small['articles'][0]['sources'][0]['value'],7)

    def test_before_eight_uses_prior_eligible_day_and_denial_not_zero(self):
        result=self.query(self.make(Sender(0,analytics.CONTENT),hour=7))
        self.assertEqual(result['end'],'2026-11-17')
        self.assertEqual(result['timeline'][-1]['cumulate_user'],0)
        self.assertNotIn('read_user',result['timeline'][-1])
        self.assertEqual(result['status'][analytics.CONTENT],{'states':['PERMISSION'],'codes':[48001]})

    def test_delayed_empty_and_invalid_payload(self):
        begin=date(2026,11,18)
        for payload,expected in (({'errcode':61503},'DELAYED'),({'list':[],'is_delay':True},'DELAYED'),
                                 ({'list':[]},'READY'),({'list':[{'ref_date':'2026-11-17'}]},'UNAVAILABLE'),
                                 ({'list':[],'is_delay':0},'UNAVAILABLE')):
            self.assertEqual(analytics.decode(analytics.CONTENT,reply(payload),OAUTH,begin,begin,begin)[0],expected)
        val=self.make()
        original=val.sender.send
        def delay(request, timeout):
            if 'getbizsummary' in request.path:
                return reply({'errcode':61503})
            return original(request, timeout)
        self.query(val)
        val.sender.send=delay
        result=self.query(val,refresh=True)
        self.assertEqual(result['status'][analytics.CONTENT]['states'],['DELAYED'])
        self.assertEqual(result['timeline'][-1]['read_user'],110)

    def test_latest_cumulative_snapshot_does_not_add_daily_figures(self):
        first=date(2026,11,16)
        today=date(2026,11,18)
        body={'list':[{'ref_date':first.isoformat(),'title':'article','content_url':'https://mp.weixin.qq.com.attacker.test/s/bad',
                       'detail_list':[{'stat_date':'2026-11-18','read_user':8,'share_user':0},
                                      {'stat_date':'2026-11-16','read_user':5},
                                      {'stat_date':'2026-11-19','read_user':99}]}]}
        state,rows,_=analytics.decode(analytics.ARTICLE,reply(body),OAUTH,first,first,today)
        self.assertEqual(state,'READY')
        item=rows[first.isoformat()][0]
        self.assertEqual((item['read_user'],item['share_user'],item['url']),(8,0,None))
        self.assertEqual(item['stat_date'],today.isoformat())

    def test_routes_are_fixed_read_only_and_app_only(self):
        assert not any(row['name']==analytics.TOOL for row in ConnectionRouter().list_tools())
        tool=next(r for r in SettingsRouter(ConnectionRouter()).list_tools() if r['name']==analytics.TOOL)
        self.assertEqual(tool['_meta']['ui']['visibility'],['app'])
        validate(analytics.TOOL,{'connection_id':'account-one','days':7})
        with self.assertRaises(WCEError):
            validate(analytics.TOOL,{'connection_id':'account-one','days':14})
        http='http://mp.weixin.qq.com/s?__biz=Example%3D&mid=123&idx=1&sn='+'a'*32+'#rd'
        self.assertEqual(analytics.readable_link(http),'https'+http[4:])
        self.assertIsNone(analytics.readable_link('https://mp.weixin.qq.com/s/fixture?access_token=invalid'))
        sender=HTTPSender(enabled=True)
        sender._prepare_request(HTTPRequest('POST','/datacube/getusersummary',{},b'{}'),1)
        for method,path in [('GET','/datacube/getusersummary'),('POST','/datacube/reset'),
                            ('POST','https://example.org/datacube/getusersummary')]:
            with self.assertRaises(WCEError):
                sender._prepare_request(HTTPRequest(method,path,{},b''),1)
