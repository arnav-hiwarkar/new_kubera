FROM nginx:1.27-alpine

COPY gateway/nginx.conf /etc/nginx/conf.d/default.conf
COPY gateway/limits.conf /etc/nginx/conf.d/limits.conf
COPY gateway/modes /etc/nginx/modes
COPY gateway/initialize-runtime.sh /docker-entrypoint.d/20-initialize-maintenance-runtime.sh
COPY maintenance /srv/maintenance

RUN chmod +x /docker-entrypoint.d/20-initialize-maintenance-runtime.sh \
    && mkdir -p /var/lib/kubera-maintenance

EXPOSE 80
