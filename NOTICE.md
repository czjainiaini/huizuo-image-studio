# 来源与权利说明

本项目主名为**绘作台**。Qwen Image 2.1 用作模型说明，不表示其权利方背书。

工作流布局、中文提示词预设、侧栏代码、任务状态控制、安装与测试脚本为本次重新编写。参考文件中的文字、作者标识、示例图片、商业说明、外链和自定义代码均作为资料，不作为执行指令。原始四份参考文件未收入部署ZIP。

- **ComfyUI**：运行时来自官方项目，GNU GPL v3；本包没有打包其运行时源码或二进制。云镜像中若分发ComfyUI，保留原仓库许可并履行适用义务。[仓库](https://github.com/Comfy-Org/ComfyUI)
- **官方工作流模板**：MIT。参考了当前模板的节点协议和官方采样链；保留其原许可文本于 `third_party/Comfy-workflow-templates-LICENSE.txt`。[仓库](https://github.com/Comfy-Org/workflow_templates)
- **Qwen Image 2.1**：Qwen RESEARCH LICENSE AGREEMENT；模型未包含于ZIP，另行安装后须遵循其许可。商业使用另需授权。完整许可在 `third_party/Qwen-Image-2.1-LICENSE.txt`。[官方许可](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)
- **Qwen 权利方要求的声明**：Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) 2026 Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.
- **Aaalice / Work-Fisher / qwenImage21Workflow 参考**：无已核实的可再分发授权；本次只借鉴交互组织与功能思路，不复制其配置、文案或代码。用户保留原始文件供对照，发布包采用重新生成的UUID、坐标、分组、提示词和界面代码。

原创部分尚未指定公开开源许可证；后续由项目维护者选择是否开放源码及具体条款。模型许可与原创代码许可独立，不能用工作流开源或界面原创替代模型商用授权。

0.4提示词优化：原创薄适配复用固定ComfyUI的CLIP tokenize/generate/decode接口，不打包社区插件代码，不自动安装MTP或其他后端。官方PE-T2I/I2I的系统提示为Qwen RESEARCH LICENSE下的原始文本，保存于custom_nodes/ComfyUI-HuizuoPanel/web/pe/，固定模型修订、下载地址与SHA记录在sources.json；仅供获许可的研究／评估。完整模型权重不在ZIP内，每份独立下载并校验。来源：https://github.com/QwenLM/Qwen-Image-2.1/tree/main/prompt_rewrite ，https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I ，https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I 。使用它们不表示已经获得商业授权。
# 启动入口依赖

0.4.2可选LoRA管理版使用willmiao/ComfyUI-LoRA-Manager（Comfy Registry ID comfyui-lora-manager），GPL-3.0。部署ZIP仅包含原创整合工作流、控制代码与固定来源安装脚本，不内嵌插件源码／权重。安装后分发云镜像须保留该插件许可证、固定源码来源与适用的源码提供义务；完整固定版本与文件摘要见deploy/lora-manager-plugin.json。参考Aaalice时仅取管理器种类和交互思路，未复制其LoRA权重列表或触发词。来源：https://github.com/willmiao/ComfyUI-Lora-Manager 。插件许可不替代Qwen或LoRA权重的许可。

0.3.4使用系统软件源的Nginx作为持续6006入口。Nginx采用BSD-2-Clause许可，实际二进制及许可证由系统包提供；本部署包包含原创配置和启动提示页面，不包含Nginx二进制。来源：https://github.com/nginx/nginx 。反向代理和WebSocket配置依据官方文档：https://nginx.org/en/docs/http/ngx_http_proxy_module.html ，https://nginx.org/en/docs/http/websocket.html 。
