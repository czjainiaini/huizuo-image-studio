"""Actual Nginx integration: unavailable/start/ready/stop, APIs and WebSockets."""
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from aiohttp import ClientSession, web

spec=importlib.util.spec_from_file_location('gateway_config','/tmp/gateway_config.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


class Gateway(unittest.IsolatedAsyncioTestCase):
    async def test_front_stays_200_and_proxy_preserves_protocols_and_failures(self):
        with tempfile.TemporaryDirectory(prefix='huizuo-gateway-') as folder:
            app_root=Path(folder);app_root.chmod(0o755)
            public_port,backend_port=port(),port()
            settings=module.configure(app_root,public_port,backend_port,app_root/'public')
            subprocess.run(['nginx','-t','-c',settings['nginx_config']],check=True,capture_output=True)
            front=subprocess.Popen(['nginx','-c',settings['nginx_config'],'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            url=f'http://127.0.0.1:{public_port}'
            runner=None
            try:
                async with ClientSession() as client:
                    for _ in range(60):
                        try:
                            async with client.get(url+'/') as response:
                                text=await response.text();self.assertEqual(response.status,200)
                                self.assertIn('正在启动',text);break
                        except OSError:await asyncio.sleep(.03)
                    else:self.fail('Front door never bound.')
                    for _ in range(15):
                        async with client.get(url+'/') as response:self.assertEqual(response.status,200)
                        await asyncio.sleep(.02)
                    async with client.get(url+'/system_stats') as response:self.assertEqual(response.status,502)
                    async def handle(request):
                        if request.path=='/system_stats':return web.json_response({'system':{'comfyui_version':'fixture'}})
                        if request.path=='/protected':return web.Response(status=403)
                        if request.path=='/missing':return web.Response(status=404)
                        if request.path=='/upload':return web.json_response({'data':(await request.read()).decode(),'host':request.host})
                        if request.path=='/ws':
                            ws=web.WebSocketResponse();await ws.prepare(request)
                            async for message in ws:
                                if message.type==web.WSMsgType.TEXT:await ws.send_str(message.data)
                                elif message.type==web.WSMsgType.BINARY:await ws.send_bytes(message.data)
                            return ws
                        return web.Response(text='NATIVE_CORE_READY',headers={'Content-Security-Policy':"default-src 'self'"})
                    backend=web.Application();backend.router.add_route('*','/{tail:.*}',handle)
                    runner=web.AppRunner(backend);await runner.setup();await web.TCPSite(runner,'127.0.0.1',backend_port).start()
                    async with client.get(url+'/') as response:
                        self.assertEqual(response.status,200);self.assertEqual(await response.text(),'NATIVE_CORE_READY')
                        self.assertEqual(response.headers['Content-Security-Policy'],"default-src 'self'")
                    for path,status in [('/protected',403),('/missing',404),('/system_stats',200)]:
                        async with client.get(url+path) as response:self.assertEqual(response.status,status)
                    async with client.post(url+'/upload',data=b'fixture-upload',headers={'Host':'studio.example:8443'}) as response:
                        data=await response.json();self.assertEqual(data,{'data':'fixture-upload','host':'studio.example:8443'})
                    async with client.ws_connect(url+'/ws') as ws:
                        await ws.send_str('text-fixture');self.assertEqual((await ws.receive()).data,'text-fixture')
                        await ws.send_bytes(b'\x00\x01');self.assertEqual((await ws.receive()).data,b'\x00\x01')
                    await runner.cleanup();runner=None
                    async with client.get(url+'/') as response:
                        self.assertEqual(response.status,200);self.assertIn('正在启动',await response.text())
                    async with client.get(url+'/system_stats') as response:self.assertEqual(response.status,502)
            finally:
                if runner is not None:await runner.cleanup()
                front.terminate();front.wait(timeout=5)


if __name__=='__main__':unittest.main()
