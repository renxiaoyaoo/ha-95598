ARG BUILD_FROM=ghcr.io/renxiaoyaoo/ha-95598:latest
FROM ${BUILD_FROM}

USER root

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
