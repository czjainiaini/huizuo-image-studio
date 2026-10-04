"""Process-owned image files with a scoped loader and /view integration.

PNG/JPEG bytes live in sealed Linux memfd objects. The managed folders contain
only links; when the serving process stops, no image payload remains on disk.
Existing ordinary files and platform records are never removed by this module.
"""
import atexit
from collections import OrderedDict
import io
import json
import os
from pathlib import Path
import re
import threading
import uuid
import sys

SUBFOLDER = 'huizuo-memory'
NAME = re.compile(r'^hz_mem_(input|temp)_[0-9a-f]{32}\.(png|jpg|jpeg|webp|gif)$')
TARGET = re.compile(r'^/proc/\d+/fd/\d+$')


def create_memory_fd(name):
    if sys.platform!='linux':raise ValueError('关机清图模式需要Linux镜像，不会退回磁盘保存图片。')
    flags=getattr(os,'MFD_CLOEXEC',1)|getattr(os,'MFD_ALLOW_SEALING',2)
    native=getattr(os,'memfd_create',None)
    if callable(native):return native(name,flags)
    # Conda builds targeting old glibc may omit Python's binding, even on a
    # host whose libc and kernel support the same standard Linux operation.
    import ctypes
    libc=ctypes.CDLL(None,use_errno=True)
    native=getattr(libc,'memfd_create',None)
    if native is None:raise ValueError('系统缺少内存文件接口，图片不会退回磁盘保存。')
    native.argtypes=[ctypes.c_char_p,ctypes.c_uint];native.restype=ctypes.c_int
    descriptor=native(name.encode('utf-8'),flags)
    if descriptor<0:
        error=ctypes.get_errno();raise OSError(error,os.strerror(error))
    return descriptor


class MemoryMediaStore:
    def __init__(self, input_directory, temp_directory, max_bytes=128*1024*1024):
        self.roots = {'input': Path(input_directory), 'temp': Path(temp_directory)}
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.lock = threading.RLock()
        for root in self.roots.values():
            directory = root / SUBFOLDER
            if directory.is_symlink():
                raise ValueError('内存图片目录不能是外部链接。')
            directory.mkdir(parents=True, exist_ok=True)
            # Old process IDs/FDs may be reused. Remove only our managed links
            # before serving requests, even if an old target now happens to exist.
            for path in directory.iterdir():
                if NAME.fullmatch(path.name) and path.is_symlink() and TARGET.fullmatch(os.readlink(path)):
                    path.unlink()

    def put(self, kind, data, suffix='.png'):
        if kind not in self.roots or suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.gif'}:
            raise ValueError('不支持的临时图片类型。')
        if len(data) > self.max_bytes:
            raise ValueError('图片超过内存临时区上限，请减小尺寸。')
        with self.lock:
            while sum(item['size'] for item in self.entries.values()) + len(data) > self.max_bytes:
                oldest = next((name for name,item in self.entries.items() if item['kind']=='temp'), None)
                if oldest is None:
                    raise ValueError('参考素材占满内存临时区，请减小素材或重新启动实例。')
                self._release(oldest)
            name = f'hz_mem_{kind}_{uuid.uuid4().hex}{suffix.lower()}'
            directory=self.roots[kind] / SUBFOLDER
            if directory.is_symlink():raise ValueError('内存图片目录不能是外部链接。')
            # Core clears temp after loading extensions, so create it on use.
            directory.mkdir(parents=True,exist_ok=True)
            path = directory / name
            fd = create_memory_fd(name)
            target = f'/proc/{os.getpid()}/fd/{fd}'
            try:
                remaining = memoryview(data)
                while remaining:
                    written = os.write(fd, remaining)
                    remaining = remaining[written:]
                import fcntl
                seals = getattr(fcntl,'F_SEAL_WRITE',8)|getattr(fcntl,'F_SEAL_GROW',4)|getattr(fcntl,'F_SEAL_SHRINK',2)|getattr(fcntl,'F_SEAL_SEAL',1)
                fcntl.fcntl(fd,getattr(fcntl,'F_ADD_SEALS',1033),seals)
                path.symlink_to(target)
            except BaseException:
                os.close(fd)
                if path.is_symlink() and os.readlink(path)==target:
                    path.unlink()
                raise
            self.entries[name] = {'fd':fd,'target':target,'path':path,'kind':kind,'size':len(data)}
            return {'name':name,'filename':name,'subfolder':SUBFOLDER,'type':kind}

    def owns(self, name, kind, subfolder):
        with self.lock:
            item = self.entries.get(name)
            return subfolder==SUBFOLDER and item is not None and item['kind']==kind

    def read(self, name, kind, subfolder):
        with self.lock:
            if not self.owns(name,kind,subfolder):
                raise ValueError('参考图已随上次关机释放，请重新上传。')
            item=self.entries[name]
            return os.pread(item['fd'],item['size'],0)

    def input_names(self):
        with self.lock:
            return [SUBFOLDER+'/'+name for name,item in self.entries.items() if item['kind']=='input']

    def _release(self, name):
        item = self.entries.pop(name)
        if item['path'].is_symlink() and os.readlink(item['path'])==item['target']:
            item['path'].unlink()
        os.close(item['fd'])

    def close(self):
        with self.lock:
            for name in list(self.entries):
                self._release(name)


_store = None

def get_store():
    global _store
    if _store is None:
        import folder_paths
        _store = MemoryMediaStore(folder_paths.get_input_directory(), folder_paths.get_temp_directory())
        atexit.register(_store.close)
    return _store


class HuizuoEphemeralLoadImage:
    @classmethod
    def INPUT_TYPES(cls):
        import nodes
        definition=nodes.LoadImage.INPUT_TYPES()
        files,options=definition['required']['image']
        return {'required':{'image':(sorted(set(files+get_store().input_names())),options)}}
    RETURN_TYPES=('IMAGE','MASK')
    FUNCTION='load_image'
    CATEGORY='绘作台/图片'
    DESCRIPTION='参考图保存在当前服务内存；关机后需重新上传。已有普通磁盘素材仍遵循原生加载器的安全检查。'

    @staticmethod
    def managed_name(image):
        name=str(image).removesuffix(' [input]')
        parts=name.split('/')
        if len(parts)==2 and parts[0]==SUBFOLDER and NAME.fullmatch(parts[1]):return parts[1]
        return None

    @classmethod
    def VALIDATE_INPUTS(cls,image):
        name=cls.managed_name(image)
        if name is not None:
            return True if get_store().owns(name,'input',SUBFOLDER) else '参考图已释放，请重新上传。'
        import nodes
        return nodes.LoadImage.VALIDATE_INPUTS(image)

    @classmethod
    def IS_CHANGED(cls,image):
        name=cls.managed_name(image)
        if name is not None:
            import hashlib
            return hashlib.sha256(get_store().read(name,'input',SUBFOLDER)).hexdigest()
        import nodes
        return nodes.LoadImage.IS_CHANGED(image)

    def load_image(self,image):
        name=self.managed_name(image)
        if name is None:
            import nodes
            return nodes.LoadImage().load_image(image)
        from PIL import Image,ImageOps,ImageSequence
        import numpy as np
        import torch
        import comfy.model_management as management
        data=get_store().read(name,'input',SUBFOLDER)
        images=[];masks=[];size=None
        with Image.open(io.BytesIO(data)) as source:
            for frame in ImageSequence.Iterator(source):
                picture=ImageOps.exif_transpose(frame)
                if size is None:size=picture.size
                if picture.size!=size:continue
                images.append(torch.from_numpy(np.array(picture.convert('RGB')).astype(np.float32)/255.)[None])
                mask=1.-torch.from_numpy(np.array(picture.getchannel('A')).astype(np.float32)/255.) if 'A' in picture.getbands() else torch.zeros((64,64))
                masks.append(mask.unsqueeze(0))
        device=management.intermediate_device();dtype=management.intermediate_dtype()
        return torch.cat(images).to(device=device,dtype=dtype),torch.cat(masks).to(device=device,dtype=dtype)


class HuizuoEphemeralPreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'images':('IMAGE',)},
                'hidden':{'prompt':'PROMPT','extra_pnginfo':'EXTRA_PNGINFO'}}
    RETURN_TYPES = ()
    FUNCTION = 'preview'
    OUTPUT_NODE = True
    CATEGORY = '绘作台/图片'
    DESCRIPTION = '图片在当前服务内存中预览；实例完整关机后释放。需要保留请下载到本机。内存上限128MB，满时释放最旧预览，不删除模型或设置。'

    def preview(self, images, prompt=None, extra_pnginfo=None):
        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        results = []
        for image in images:
            picture = Image.fromarray(np.clip(255.*image.cpu().numpy(),0,255).astype(np.uint8))
            metadata = PngInfo()
            if prompt is not None:
                metadata.add_text('prompt',json.dumps(prompt,ensure_ascii=False))
            for key,value in (extra_pnginfo or {}).items():
                metadata.add_text(key,json.dumps(value,ensure_ascii=False))
            buffer = io.BytesIO()
            picture.save(buffer,format='PNG',pnginfo=metadata,compress_level=1)
            results.append(get_store().put('temp',buffer.getvalue()))
        return {'ui':{'images':results}}


def install_memory_media():
    """Keep core path/security checks; intercept only image-upload storage."""
    from aiohttp import web
    from server import PromptServer
    instance = PromptServer.instance
    if getattr(instance,'_huizuo_memory_media',False):
        return
    instance._huizuo_memory_media = True
    get_store()

    @web.middleware
    async def middleware(request, handler):
        path = request.path.removeprefix('/api')
        if path=='/upload/image' and request.method=='POST' and os.environ.get('HUIZUO_EPHEMERAL_INPUTS','1')=='1':
            reader = await request.multipart()
            fields = {}; payload = bytearray(); filename = None
            while True:
                field = await reader.next()
                if field is None:
                    break
                if field.name=='image':
                    if filename is not None:
                        return web.json_response({'error':'一次只上传一张参考图。'},status=400)
                    filename = field.filename or ''
                    while chunk := await field.read_chunk():
                        payload.extend(chunk)
                        if len(payload)>32*1024*1024:
                            return web.json_response({'error':'参考图超过32MB，请先减小文件。'},status=413)
                else:
                    fields[field.name] = await field.text()
            if filename is None or fields.get('type','input') not in {'input','temp'}:
                return web.json_response({'error':'临时素材上传仅接受input或temp图片。'},status=400)
            suffix = Path(filename).suffix.lower()
            if suffix not in {'.png','.jpg','.jpeg','.webp','.gif'}:
                return web.json_response({'error':'只接受PNG/JPEG/WebP/GIF图片。'},status=400)
            try:
                from PIL import Image
                with Image.open(io.BytesIO(payload)) as image:
                    image.verify()
                info = get_store().put(fields.get('type','input'),bytes(payload),suffix)
                return web.json_response({key:info[key] for key in ['name','subfolder','type']})
            except (ValueError,OSError) as error:
                return web.json_response({'error':str(error)},status=400)
        if path=='/view' and NAME.fullmatch(request.query.get('filename','')):
            if not get_store().owns(request.query['filename'],request.query.get('type','output'),request.query.get('subfolder','')):
                return web.Response(status=404,headers={'Cache-Control':'no-store'})
            name=request.query['filename'];kind=request.query.get('type','output')
            data=get_store().read(name,kind,SUBFOLDER)
            mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.gif':'image/gif'}[Path(name).suffix]
            return web.Response(body=data,content_type=mime,headers={'Cache-Control':'no-store'})
        return await handler(request)
    instance.app.middlewares.append(middleware)
