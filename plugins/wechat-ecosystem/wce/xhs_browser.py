"""One private standard-browser pipe, owned by the current plugin process.

The renderer cannot be reused: it is offline and disables scripts. This small
fixed-action helper uses existing local dependencies, never installs a browser,
exports cookies, opens a public control port or controls a user's other profile.
"""
import atexit
import json
import os
from pathlib import Path
import select
import secrets
import shutil
import subprocess
import threading
import time

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import locked
from .own_connection_registry import container


def runtime():
    # Host dependency locators, not immutable/version-lock claims. No username
    # or rendered runtime pins are copied into a portable package.
    base=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    node=base/'bin/node'
    if not node.is_file():node=Path(shutil.which('node') or '/nonexistent')
    entry=base/'node_modules/playwright/index.js'
    chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if not all(p.is_file() for p in (node,entry,chrome)):
        raise WCEError('XHS_RUNTIME_UNAVAILABLE')
    return {'node':str(node),'entry':str(entry),'browser':str(chrome)}


class Browser:
    def __init__(self,root,*,dependencies=None):
        self.root=Path(root);self.dependencies=dependencies
        self.process=None;self.lease=None;self.mutex=threading.RLock();self.retain=False;self.abandoned=set();self.incoming=bytearray()
        atexit.register(self.close)

    def available(self):
        try:self.dependencies or runtime();return True
        except WCEError:return False

    def _start(self):
        if self.process and self.process.poll() is None:return
        self.close()
        deps=self.dependencies or runtime()
        path_check(self.root,True)
        self.lease=locked(self.root/'browser.lock',nonblocking=True)
        try:
            self.lease.__enter__()
            profile=container(self.root,'browser-profile')
            env=os.environ.copy();env.pop('NODE_OPTIONS',None);env.pop('NODE_PATH',None)
            # Chromium credentials stay in its own 0700 profile. stderr is not
            # a diagnostic source: browser errors may include private URLs.
            self.process=subprocess.Popen([deps['node'],str(Path(__file__).with_name('xhs_browser_driver.cjs')),
                deps['entry'],deps['browser'],str(profile)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,env=env,start_new_session=True)
        except BaseException:
            self.close();raise

    def call(self,op,*,on_event=None,timeout=120,**args):
        if op not in {'BEGIN','POLL','PROFILE','NOTES','NOTE','PUBLISH','RESOLVE','FORM','RESUME_DRAFT','RESULT'}:
            raise WCEError('XHS_INVALID_REQUEST')
        with self.mutex:
            self._start();p=self.process;end=time.monotonic()+timeout;request_id=secrets.token_hex(16)
            try:
                p.stdin.write((json.dumps({'op':op,'request_id':request_id}|args)+'\n').encode());p.stdin.flush()
                while True:
                    # Do not combine select(fd) with BufferedReader.readline:
                    # a coalesced late reply can already be buffered while the
                    # OS fd is empty, falsely timing out the next request.
                    if b'\n' not in self.incoming:
                        remaining=end-time.monotonic()
                        if remaining<=0 or not select.select([p.stdout],[],[],remaining)[0]:
                            raise WCEError('XHS_BROWSER_TIMEOUT')
                        chunk=os.read(p.stdout.fileno(),65536)
                        if not chunk:raise WCEError('XHS_BROWSER_UNAVAILABLE')
                        self.incoming.extend(chunk);continue
                    line,_,remaining_bytes=self.incoming.partition(b'\n')
                    self.incoming=bytearray(remaining_bytes)
                    value=json.loads(line)
                    response_id=value.pop('request_id',None)
                    if response_id!=request_id:
                        if response_id in self.abandoned and 'event' not in value:
                            self.abandoned.discard(response_id);continue
                        raise WCEError('XHS_BROWSER_PROTOCOL_INVALID')
                    if set(value) in ({'event'},{'event','data'}):
                        if value['event'] not in {'UPLOAD_STARTED','SUBMIT_STARTED'} or on_event is None:
                            raise WCEError('XHS_BROWSER_PROTOCOL_INVALID')
                        on_event(value['event'],value.get('data'))
                        p.stdin.write((json.dumps({'ack':True,'request_id':request_id})+'\n').encode());p.stdin.flush();continue
                    if set(value)=={'error'}:
                        # Only fixed driver codes, never exception strings.
                        import re
                        if type(value['error']) is str and re.fullmatch('XHS_[A-Z_]+',value['error']):
                            raise WCEError(value['error'])
                        raise WCEError('XHS_BROWSER_PROTOCOL_INVALID')
                    if set(value)!={'result'} or type(value['result']) is not dict:
                        raise WCEError('XHS_BROWSER_PROTOCOL_INVALID')
                    return value['result']
            except WCEError as error:
                if error.code=='XHS_BROWSER_TIMEOUT' and self.retain:self.abandoned.add(request_id)
                elif error.code in {'XHS_BROWSER_TIMEOUT','XHS_BROWSER_PROTOCOL_INVALID','XHS_BROWSER_UNAVAILABLE'}:self.close()
                raise
            except Exception:
                self.close()
                raise WCEError('XHS_BROWSER_UNAVAILABLE') from None

    def close(self):
        with self.mutex:
            p,self.process=self.process,None;self.retain=False;self.abandoned.clear();self.incoming.clear()
            if p:
                try:p.stdin.close();p.wait(timeout=5)
                except (OSError,subprocess.TimeoutExpired):
                    p.terminate()
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:p.kill();p.wait()
                finally:
                    if p.stdout:p.stdout.close()
            lease,self.lease=self.lease,None
            if lease:
                try:lease.__exit__(None,None,None)
                except Exception:pass
