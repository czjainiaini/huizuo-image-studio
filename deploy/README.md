# 部署

本仓库是0.4.4研究源码。源码与已保存AutoDL镜像分别维护；修改仓库不会自动更新旧镜像。

## 已有AutoDL Linux实例

装配需要Python >=3.10、Git、Bash及可用的软件包安装环境。持续6006入口依赖系统软件源的Nginx；若尚未安装，脚本要求既有 `policy-rc.d` 策略禁止软件包安装时自动启动默认服务，否则会停止并提示。先按自己镜像的服务策略准备Nginx，再执行装配；不要覆盖已有策略文件。已提供的Docker配方会在构建阶段安装Nginx。

先进入自己的实例，获取源码：

```bash
git clone https://github.com/czjainiaini/huizuo-image-studio.git
cd huizuo-image-studio
```

装配脚本默认只显示计划，不安装。目标需为新目录；不要覆盖自己已有的ComfyUI环境。

```bash
python3 scripts/prepare_autodl.py --root /root/HuizuoStudio --model-source auto --purpose research --with-lora-manager
```

核对计划后，安装到新环境：

```bash
python3 scripts/prepare_autodl.py --root /root/HuizuoStudio --model-source auto --purpose research --with-lora-manager --apply
```

这会安装固定ComfyUI、依赖、原创节点及可选管理器，不会租机、生成图片、付费扩容或提交平台发布。实例自己的开机／存储费用仍由平台计收。

镜像维护者在AutoDL设置开机启动命令：

```bash
HUIZUO_HUB_ENDPOINT=https://hf-mirror.com bash /root/HuizuoStudio/autostart.sh
```

默认准备缺失核心模型，不下载PE、不下载LoRA样本。固定平台开机链会自动启用持续6006入口和自启钩子；在普通终端中打开shell不会重复启动。

## Docker

完整管理版构建方式：

```bash
docker build -f deploy/Dockerfile --build-arg TORCH_CHANNEL=cu128 --build-arg WITH_LORA_MANAGER=1 -t huizuo/comfyui:0.4.4-cu128-lora .
```

根目录Dockerfile与 `deploy/Dockerfile` 内容相同。默认 `WITH_LORA_MANAGER=0`，只使用普通工作流时可不安装管理器。

需要主机具备适配的NVIDIA驱动和容器GPU支持：

```bash
docker run --gpus all --rm -p 6006:6006 -v huizuo-models:/opt/ComfyUI/models huizuo/comfyui:0.4.4-cu128-lora
```

模型卷用于保留核心及可选权重；内存图片不通过该卷持久化。首次模型准备需要时间与足够磁盘空间。个人实例服务入口不要转发给他人，使用范围按平台协议处理。

本配方已完整构建，Torch 2.11.0+cu128；独立CPU界面、节点注册、HTTP/WebSocket、内存图片重启失效与原生PNG导入检查通过。Docker容器的Qwen GPU推理没有在本机4GB显卡上验收，不能与AutoDL真实GPU结果混称。

## 检查与使用

```bash
python3 scripts/validate_workflows.py
node --test tests/*.test.mjs
```

这两项检查工作流结构和前端行为，不替代真实GPU出图。首次操作见[启动指南](../使用指南.md)，实际已验证范围见[验收报告](../evidence/v044-complete-validation.md)。
