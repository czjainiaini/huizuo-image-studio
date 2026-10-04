"""Narrow compatibility fix for user-activated navigation to the public HTML root."""
import argparse
import hashlib
import json
import os
from pathlib import Path

OLD = """            if sec_fetch_site == 'cross-site':
                return web.Response(status=403)
"""
NEW = """            if sec_fetch_site == 'cross-site':
                # Huizuo: only a user-activated, top-level GET of the public shell.
                public_root_navigation = (
                    request.method == 'GET' and request.path == '/'
                    and request.headers.get('Sec-Fetch-Mode') == 'navigate'
                    and request.headers.get('Sec-Fetch-Dest') == 'document'
                    and request.headers.get('Sec-Fetch-User') == '?1'
                )
                if not public_root_navigation:
                    return web.Response(status=403)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfy-root', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.comfy_root.resolve()
    target = root / 'server.py'
    if not target.is_file() or not (root / 'main.py').is_file():
        parser.error('Expected existing native ComfyUI')
    source = target.read_text(encoding='utf-8')
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest == '769395c0dc3a0e18b3ff2eac94aca87e06f609311f53374a94519fbb53f5ec63':
        print(json.dumps({'already_applied': True})); return
    if digest != '12545dbc44f56ce4c8ae696832925baedf0eecd2879c4e23bae3469411d7593c' or source.count(OLD) != 1:
        parser.error('Core guard differs from the verified implementation; preserved unchanged.')
    patched = source.replace(OLD, NEW, 1)
    compile(patched, str(target), 'exec')
    record = {'fix': 'user-activated GET / document navigation only',
              'before_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'after_sha256': hashlib.sha256(patched.encode()).hexdigest(),
              'api_cross_site_guard': 'retained', 'other_middleware': 'unchanged', 'applied': args.apply}
    if args.apply:
        backup = root / '.huizuo-runtime/server.py.before-navigation-fix'
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists():
            parser.error('Backup already exists; existing files preserved.')
        backup.write_text(source, encoding='utf-8')
        temporary = root / '.huizuo-runtime/server.py.navigation-new'
        temporary.write_text(patched, encoding='utf-8')
        temporary.chmod(target.stat().st_mode & 0o777)
        os.replace(temporary, target)
        (backup.parent / 'navigation-fix.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
