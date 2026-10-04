"""Original sidebar plus an optional, default-off adapter over core CLIP APIs."""
from .prompt_enhancer import HuizuoQwenPromptEnhance, HuizuoCanvasPromptOptimize
from .ephemeral_media import HuizuoEphemeralPreview, HuizuoEphemeralLoadImage, install_memory_media
NODE_CLASS_MAPPINGS = {'HuizuoQwenPromptEnhance':HuizuoQwenPromptEnhance,
                      'HuizuoCanvasPromptOptimize':HuizuoCanvasPromptOptimize,
                      'HuizuoEphemeralPreview':HuizuoEphemeralPreview,
                      'HuizuoEphemeralLoadImage':HuizuoEphemeralLoadImage}
NODE_DISPLAY_NAME_MAPPINGS = {'HuizuoQwenPromptEnhance':'绘作台 · 官方PE提示词优化（可选）',
                             'HuizuoCanvasPromptOptimize':'绘作台 · 画布AI提示词优化（开关）',
                             'HuizuoEphemeralPreview':'绘作台 · 图片内存预览（关机清除）',
                             'HuizuoEphemeralLoadImage':'绘作台 · 参考图内存加载（关机清除）'}
install_memory_media()
WEB_DIRECTORY = "./web"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
