# Dockerfile（修改版）
FROM raibee/abution-graph:3.5.0

WORKDIR /thutmose
USER root

# 安装 Nginx 和工具
RUN apk update && apk add --no-cache \
    nginx \
    apache2-utils \
    netcat-openbsd \
    busybox-extras \
    procps \
    jq \
    && rm -rf /var/cache/apk/* \
    && mkdir -p /run/nginx /etc/nginx/http.d /var/lib/nginx/tmp /var/log/nginx

# 创建密码文件
RUN htpasswd -bc /etc/nginx/.htpasswd abution YourPassword123!

# 创建主配置（包含 log_format）
RUN echo 'events { \
    worker_connections 1024; \
} \
http { \
    include /etc/nginx/mime.types; \
    default_type application/octet-stream; \
    log_format debug_log '"'"'\n'"'"' \
        '"'"'========================================\n'"'"' \
        '"'"'Request Time: $time_local\n'"'"' \
        '"'"'Remote Address: $remote_addr\n'"'"' \
        '"'"'Request Method: $request_method\n'"'"' \
        '"'"'Request URI: $request_uri\n'"'"' \
        '"'"'Full Request: $request\n'"'"' \
        '"'"'HTTP Host: $http_host\n'"'"' \
        '"'"'HTTP Referer: $http_referer\n'"'"' \
        '"'"'HTTP User-Agent: $http_user_agent\n'"'"' \
        '"'"'Authorization Header: $http_authorization\n'"'"' \
        '"'"'Query String: $query_string\n'"'"' \
        '"'"'Request Body: $request_body\n'"'"' \
        '"'"'Cookies: $http_cookie\n'"'"' \
        '"'"'----------------------------------------\n'"'"' \
        '"'"'Proxied to: http://127.0.0.1:9995$request_uri\n'"'"' \
        '"'"'========================================\n'"'"'; \
    access_log /thutmose/logs/nginx/access.log; \
    error_log /thutmose/logs/nginx/error.log; \
    include /etc/nginx/http.d/*.conf; \
}' > /etc/nginx/nginx.conf

# 复制子配置文件（不含 log_format）
COPY nginx.conf /etc/nginx/http.d/abution.conf

# 安装 openssl 并生成自签名证书
RUN apk add --no-cache openssl && \
    mkdir -p /etc/nginx/ssl && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/abution.key \
        -out /etc/nginx/ssl/abution.crt \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=Abution/OU=Dev/CN=localhost"

# 暴露端口
EXPOSE 25565 9996 9997

# 复制启动脚本
COPY start.sh ./
COPY network.conf /thutmose/network.conf

RUN chmod +x start.sh

# 创建必要目录
RUN mkdir -p ./data ./logs ./backup
RUN mkdir -p /thutmose/logs/nginx

CMD ["./start.sh"]