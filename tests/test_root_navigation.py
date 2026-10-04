"""Exercise the actual core guard without importing model/GPU modules."""
import ast
import ipaddress
import logging
import os
from pathlib import Path
import socket
import unittest
import urllib.parse
from aiohttp import web
from aiohttp.test_utils import make_mocked_request


def actual_guard():
    source = Path(os.environ.get('COMFY_CORE_SERVER', '/opt/ComfyUI/server.py')).read_text()
    selected = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)
                and node.name in {'is_loopback', 'create_origin_only_middleware'}]
    namespace = {'web': web, 'ipaddress': ipaddress, 'socket': socket, 'urllib': urllib, 'logging': logging}
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<actual-core-guard>', 'exec'), namespace)
    return namespace['create_origin_only_middleware']()


class NavigationGuard(unittest.IsolatedAsyncioTestCase):
    async def response(self, method, path, headers):
        request = make_mocked_request(method, path, headers={'Host': 'studio.example', **headers})

        async def original_handler(request):
            return web.Response(text='native handler', headers={'Content-Security-Policy': "default-src 'self'"})

        return await actual_guard()(request, original_handler)

    async def test_user_activated_public_root_document_opens(self):
        response = await self.response('GET', '/', {'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document', 'Sec-Fetch-User': '?1'})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['Content-Security-Policy'], "default-src 'self'")

    async def test_cross_site_api_and_non_navigation_stay_blocked(self):
        nav = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate',
               'Sec-Fetch-Dest': 'document', 'Sec-Fetch-User': '?1'}
        for method, path, changed in [('POST', '/prompt', {}), ('GET', '/queue', {}),
            ('POST', '/', {}), ('GET', '/', {'Sec-Fetch-Dest': 'iframe'}),
            ('GET', '/', {'Sec-Fetch-Mode': 'cors'}), ('GET', '/', {'Sec-Fetch-User': ''})]:
            with self.subTest(method=method, path=path, changed=changed):
                self.assertEqual((await self.response(method, path, {**nav, **changed})).status, 403)

    async def test_existing_direct_and_same_origin_access_unchanged(self):
        self.assertEqual((await self.response('GET', '/', {})).status, 200)
        self.assertEqual((await self.response('GET', '/queue', {'Sec-Fetch-Site': 'same-origin'})).status, 200)

    async def test_loopback_origin_check_is_retained(self):
        response = await self.response('GET', '/', {'Host': '127.0.0.1:6006',
            'Origin': 'https://untrusted.invalid', 'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document', 'Sec-Fetch-User': '?1'})
        self.assertEqual(response.status, 403)


if __name__ == '__main__':
    unittest.main()
