# AutoDL源码关联说明

本仓库地址：**https://github.com/czjainiaini/huizuo-image-studio**。

GitHub保存工作流、节点／侧栏源码、安装脚本、Dockerfile与使用指南。AutoDL保存的Docker镜像继续由平台镜像列表管理，不把完整镜像或大模型文件作为Git仓库内容提交。

## 发布表单中如何使用

- 如果表单要求“GitHub仓库”“源码地址”或类似字段，填写上述仓库地址。
- 如要求分支，使用 `main`；如要求Dockerfile路径，根目录 `Dockerfile` 与 `deploy/Dockerfile` 均为同一构建配方。该配方与已经保存的AutoDL镜像是两种部署方式，请按表单实际含义选择。
- 镜像关联选择维护者已经保存并完成恢复验收的0.4.4研究镜像；不要把Git仓库地址误填成镜像ID。
- 默认应用入口为6006；启动命令见[部署说明](deploy/README.md)。

具体字段、封面、协议与审核要求以具有发布权限账号的实际页面为准。本仓库准备完成不代表已经关联镜像、提交审核或取得商业授权。

## 权利与激励

Qwen Image 2.1及可选PE的现行研究许可限制商业用途，另需商业授权。平台现金激励用途应先核对授权范围；源码地址可用并不能补足模型商用许可。第三方代码和模型分别遵守各自条款，详情见[NOTICE](NOTICE.md)。

官方参考：[AutoDL镜像说明](https://www.autodl.art/docs/image/)、[平台激励规则](https://www.autodl.art/docs/reward_rule/)、[Qwen模型许可](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)。
