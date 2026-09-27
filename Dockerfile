FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SET_CONTAINER_TIMEZONE=true
ENV CONTAINER_TIMEZONE=Asia/Shanghai
ENV TZ=Asia/Shanghai


ARG TARGETARCH
ARG VERSION=dev
ARG APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG APT_SCHEME=https
ARG APT_FALLBACK_MIRROR=deb.debian.org
ARG APT_FALLBACK_SCHEME=https
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
ENV VERSION=${VERSION}
ENV PYTHON_IN_DOCKER='PYTHON_IN_DOCKER'

WORKDIR /app

RUN set -eux; \
    rewrite_sources() { \
        src="$1"; \
        dst="$2"; \
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
            sed -i "s|$src|$dst|g" /etc/apt/sources.list.d/debian.sources; \
        fi; \
        if [ -f /etc/apt/sources.list ]; then \
            sed -i "s|$src|$dst|g" /etc/apt/sources.list; \
        fi; \
    }; \
    primary_src="http://deb.debian.org"; \
    primary_security_src="http://security.debian.org"; \
    primary_dst="${APT_SCHEME}://${APT_MIRROR}"; \
    fallback_dst="${APT_FALLBACK_SCHEME}://${APT_FALLBACK_MIRROR}"; \
    rewrite_sources "$primary_src" "$primary_dst"; \
    rewrite_sources "$primary_security_src" "$primary_dst"; \
    if ! (apt-get --allow-releaseinfo-change update && apt-get install -y --no-install-recommends chromium chromium-driver fonts-noto-cjk tzdata xauth xvfb); then \
        echo "Primary apt mirror failed, falling back to ${fallback_dst}" >&2; \
        rewrite_sources "$primary_dst" "$fallback_dst"; \
        apt-get --allow-releaseinfo-change update; \
        apt-get install -y --no-install-recommends chromium chromium-driver fonts-noto-cjk tzdata xauth xvfb; \
    fi; \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime; \
    echo $TZ > /etc/timezone; \
    dpkg-reconfigure --frontend noninteractive tzdata; \
    rm -rf /var/lib/apt/lists/*; \
    apt-get clean

COPY requirements.txt /tmp/requirements.txt

RUN cd /tmp \
    && python3 -m pip install --upgrade pip \
    && PIP_ROOT_USER_ACTION=ignore pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    --retries 10 \
    --timeout 120 \
    --index-url "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}" \
    -r requirements.txt \
    && rm -rf /tmp/* \
    && find /usr/local/lib/python3.12/site-packages -type d \( -name __pycache__ -o -name test -o -name tests \) -prune -exec rm -rf '{}' + \
    && find /usr/local/lib/python3.12/site-packages -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete \
    && pip cache purge \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/log/*

ENV LANG=C.UTF-8

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app \
    && mkdir -p /app/data \
    && chown -R app:app /app

COPY --chown=app:app scripts /app/scripts
COPY --chown=app:app captcha_solver /app/captcha_solver
COPY --chown=app:app config /app/config

ENV BROWSER_DISABLE_SANDBOX=true
USER app

HEALTHCHECK --interval=60s --timeout=5s --start-period=120s --retries=2 \
    CMD python3 -m scripts.tools.healthcheck

CMD ["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", "python3", "-m", "scripts.main"]
