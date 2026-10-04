FROM python:3.12-slim-bookworm
ARG COMFY_COMMIT=651ca296a73cd21c12a57eb8741d52e40dc6528f
ARG TORCH_CHANNEL=cu128
ARG WITH_LORA_MANAGER=0
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=5 \
    COMFY_ROOT=/opt/ComfyUI HUIZUO_DEVICE=cuda HUIZUO_PORT=6006
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libgl1 libglib2.0-0 nginx \
    && rm -rf /var/lib/apt/lists/*
RUN git init /opt/ComfyUI \
    && git -C /opt/ComfyUI remote add origin https://github.com/Comfy-Org/ComfyUI.git \
    && git -C /opt/ComfyUI fetch --depth 1 origin ${COMFY_COMMIT} \
    && git -C /opt/ComfyUI checkout --detach FETCH_HEAD
COPY deploy/torch-constraints.txt /opt/huizuo/deploy/torch-constraints.txt
RUN python -m pip install torch==2.11.0+${TORCH_CHANNEL} torchvision==0.26.0+${TORCH_CHANNEL} --index-url https://download.pytorch.org/whl/${TORCH_CHANNEL} --extra-index-url https://pypi.org/simple \
    && python -m pip install -r /opt/ComfyUI/requirements.txt -c /opt/huizuo/deploy/torch-constraints.txt \
    && python -m pip check
COPY scripts /opt/huizuo/scripts
COPY custom_nodes /opt/huizuo/custom_nodes
COPY workflows /opt/huizuo/workflows
COPY third_party /opt/huizuo/third_party
COPY models-manifest.json /opt/huizuo/models-manifest.json
COPY prompt-enhancer-models-manifest.json /opt/huizuo/prompt-enhancer-models-manifest.json
COPY deploy/lora-manager-plugin.json /opt/huizuo/deploy/lora-manager-plugin.json
RUN python /opt/huizuo/scripts/fix_root_navigation.py --comfy-root /opt/ComfyUI --apply \
    && python /opt/huizuo/scripts/install.py --comfy-root /opt/ComfyUI
RUN if [ "${WITH_LORA_MANAGER}" = "1" ]; then python /opt/huizuo/scripts/install_lora_manager.py --comfy-root /opt/ComfyUI --apply; fi
COPY deploy/entrypoint.sh /opt/huizuo/deploy/entrypoint.sh
COPY deploy/autodl-public-models.json /opt/huizuo/deploy/autodl-public-models.json
RUN chmod +x /opt/huizuo/deploy/entrypoint.sh \
    && python -m pip freeze > /opt/huizuo/deploy/runtime.freeze.txt
WORKDIR /opt/ComfyUI
EXPOSE 6006
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('HUIZUO_PORT','6006')+'/system_stats',timeout=4)"
ENTRYPOINT ["/opt/huizuo/deploy/entrypoint.sh"]
