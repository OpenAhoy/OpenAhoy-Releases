"""Human QR entry for an explicit local source/candidate; never installs software.

Uses the same account/session backend as the embedded page. Prints only fixed
states and, after human login, the public account association. No credentials,
QR data, page internals, private capability URLs or browser diagnostics.
"""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wce.xhs_platform import XHSPlatform
from wce.contracts import WCEError


def main():
    platform=XHSPlatform();binding_id=None
    try:
        result=platform.begin_login()
        print(json.dumps({k:v for k,v in result.items() if k!='binding_id'},ensure_ascii=False),flush=True)
        binding_id=result['binding_id']
        while True:
            result=platform.poll_login(binding_id)
            if result['state']=='BOUND_IDLE':
                print(json.dumps(result,ensure_ascii=False),flush=True)
                return 0
            time.sleep(3)
    except KeyboardInterrupt:
        if binding_id:platform.ui('CANCEL',binding_id=binding_id)
        print('XHS_LOGIN_CANCELLED',flush=True)
        return 1
    except WCEError as error:
        print(error.code,flush=True)
        return 1
    finally:
        for browser in platform.browsers.values():browser.close()


if __name__=='__main__':raise SystemExit(main())
