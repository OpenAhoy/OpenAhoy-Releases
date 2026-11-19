"""Run a verified release's updater for an existing Codex marketplace slot."""
import argparse
import json
from pathlib import Path
from secrets import token_hex
import subprocess
import sys
import time

PACKAGE = Path(__file__).resolve().parents[1] / 'plugins' / 'wechat-ecosystem'
sys.path.insert(0, str(PACKAGE))

from wce.contracts import WCEError
from wce.own_update_install import (ACTIVE, SELECTOR, UpdateInstaller, cli, installed,
                                    require, verify_installation, verify_package)
from wce.own_updates import VERSION, check


def upgrade(plugin_id, version, *, run=cli, checker=check, installer=UpdateInstaller):
    require(SELECTOR.fullmatch(plugin_id) and VERSION.fullmatch(version), 'UPDATE_TARGET_INVALID')
    active = installed(run('list'))
    require(len(active) == 1 and active[0]['pluginId'] == plugin_id, 'UPDATE_INSTALLED_VERSION_CHANGED')
    previous = active[0]['version']
    advertised = checker(previous)
    require(advertised.get('state') != 'CHECK_UNAVAILABLE', 'UPDATE_CHECK_UNAVAILABLE')
    require(advertised.get('latest_version') == version, 'UPDATE_ADVERTISEMENT_CHANGED')
    manifest = advertised['package_manifest_sha256']
    verify_package(PACKAGE, version, manifest)
    service = installer(previous, checker=checker, run=run)
    if previous == version:
        verify_installation(version, plugin_id, manifest, {'installed': active})
        result = service.status()
        if result['state'] in ACTIVE | {'INSTALL_UNKNOWN'}:
            return result
        return {'state': 'INSTALLED', 'version': version}
    request_id = token_hex(16)
    result = service.start(version, advertised['advertised_revision'], request_id)
    if result.get('request_id') != request_id:
        return result
    while result['state'] in ACTIVE:
        time.sleep(.25)
        result = service.status(request_id)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-id', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    try:
        result = upgrade(args.plugin_id, args.version)
    except (WCEError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        result = {'state': 'FAILED', 'code': getattr(error, 'code', 'UPDATE_OPERATION_FAILED')}
    print(json.dumps({key: result[key] for key in ('state', 'version', 'code', 'request_id') if key in result}))
    return 0 if result['state'] in ('INSTALLED', 'INSTALLED_RELOAD_REQUIRED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
