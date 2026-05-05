#!/bin/sh

echo "========================================="
echo "Starting AbutionGraph with Auth Proxy"
echo "========================================="

# 停止所有 Nginx 进程
pkill nginx 2>/dev/null || true
sleep 2

# 创建日志文件
touch /thutmose/logs/nginx/execute.log /thutmose/logs/nginx/error_details.log /thutmose/logs/nginx/error_requests.log /thutmose/logs/nginx/rest.log /thutmose/logs/nginx/db.log /thutmose/logs/nginx/web.log /thutmose/logs/nginx/graph.log
chown nginx:nginx /thutmose/logs/nginx/execute.log /thutmose/logs/nginx/error_details.log /thutmose/logs/nginx/error_requests.log /thutmose/logs/nginx/rest.log /thutmose/logs/nginx/db.log /thutmose/logs/nginx/web.log /thutmose/logs/nginx/graph.log

# 禁用 default.conf
if [ -f /etc/nginx/http.d/default.conf ]; then
    mv /etc/nginx/http.d/default.conf /etc/nginx/http.d/default.conf.bak
fi

# 创建密码文件（如果不存在）
if [ ! -f /etc/nginx/.htpasswd ]; then
    htpasswd -bc /etc/nginx/.htpasswd abution YourPassword123!
fi

# 测试配置
echo "Testing Nginx configuration..."
nginx -t

# 启动 Nginx
echo "Starting Nginx..."
nginx

sleep 3

# 检查监听
echo "Checking Nginx ports..."
netstat -tlnp | grep nginx
netstat -tlnp | grep 9996

# 测试本地访问
echo "Testing local access..."
curl -u abution:YourPassword123! -I http://127.0.0.1:9996/health 2>/dev/null || echo "❌ Local access failed"
curl -u abution:YourPassword123! -I http://127.0.0.1:9996/ 2>/dev/null || echo "❌ Root access failed"

# 25565 迷惑端口
(
    while true; do
        echo -e "HTTP/1.1 403 Forbidden\r\n\r\nThis port is not for database access. Use port 9996 with HTTP Basic Auth." | \
        nc -l -p 25565 -q 1 2>/dev/null || true
    done
) &
echo "✅ Decoy service started on port 25565"

# 等待 AbutionGraph
echo "Waiting for AbutionGraph on port 9995..."
while ! nc -z 127.0.0.1 9995 2>/dev/null; do
    echo "Waiting..."
    sleep 2
done
echo "✅ AbutionGraph is ready"

echo ""
echo "========================================="
echo "🎯 Access Information"
echo "========================================="
echo "📊 Web Interface:  http://127.0.0.1:9996"
echo "🔑 Username:       abution"
echo "🔑 Password:       YourPassword123!"
echo ""
echo "🔄 Test Commands:"
echo "  curl -u abution:YourPassword123! http://127.0.0.1:9996/health"
echo "  curl -u abution:YourPassword123! http://127.0.0.1:9996/"
echo "========================================="

# 配置文件监控函数
watch_config() {
    CONFIG_FILE="/thutmose/app/abution/graphui/serverConfig.json"
    NETWORK_CONF="/thutmose/network.conf"
    LAST_MODIFIED=0
    
    while true; do
        if [ -f "$NETWORK_CONF" ]; then
            CURRENT_MODIFIED=$(stat -c %Y "$NETWORK_CONF" 2>/dev/null || echo 0)
            if [ "$CURRENT_MODIFIED" != "$LAST_MODIFIED" ] && [ -f "$CONFIG_FILE" ]; then
                echo "📝 Detected network.conf change, updating serverConfig.json..."
                
                # 安全读取配置
                SERVER_URL_HTTP=$(grep -E '^SERVER_URL_HTTP=' "$NETWORK_CONF" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | xargs)
                SERVER_URL_HTTPS=$(grep -E '^SERVER_URL_HTTPS=' "$NETWORK_CONF" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | xargs)
                
                # 设置默认值
                SERVER_URL_HTTP=${SERVER_URL_HTTP:-"http://127.0.0.1:9996"}
                SERVER_URL_HTTPS=${SERVER_URL_HTTPS:-"https://127.0.0.1:9997"}
                
                # 默认使用 HTTPS
                SERVER_URL=$SERVER_URL_HTTPS
                echo "🔒 Defaulting to HTTPS: $SERVER_URL"
                
                # 备份
                cp "$CONFIG_FILE" "$CONFIG_FILE.bak"
                
                # 修改配置
                sed -i "s|\"baseURL\": \".*\"|\"baseURL\": \"${SERVER_URL}\"|g" "$CONFIG_FILE"
                sed -i "s|\"baseURL48\": \".*\"|\"baseURL48\": \"${SERVER_URL}\"|g" "$CONFIG_FILE"
                sed -i "s|\"baseURLFile\": \".*\"|\"baseURLFile\": \"${SERVER_URL}\"|g" "$CONFIG_FILE"
                
                echo "✅ serverConfig.json updated to ${SERVER_URL}"
                LAST_MODIFIED=$CURRENT_MODIFIED
            fi
        fi
        sleep 5
    done
}

# 创建 FIFO 管道用于交互
setup_fifo() {
    FIFO_PATH="/tmp/abution_cmd.fifo"
    
    # 如果已存在，先删除
    [ -p "$FIFO_PATH" ] && rm "$FIFO_PATH"
    
    # 创建新的 FIFO 管道
    mkfifo "$FIFO_PATH"
    echo "✅ Created command FIFO at $FIFO_PATH"
    
    # 在后台启动命令处理
    (
        while true; do
            if read -r cmd < "$FIFO_PATH"; then
                if [ -n "$cmd" ]; then
                    if [ "$cmd" = "exit" ] || [ "$cmd" = "quit" ]; then
                        echo "📝 Command processor exiting..."
                        break
                    fi
                    
                    echo "========================================="
                    echo "📥 Executing command: $cmd"
                    echo "========================================="
                    
                    # 执行命令并捕获输出
                    # 使用临时文件来捕获输出，避免与日志输出混合
                    TMP_OUTPUT=$(mktemp)
                    eval "$cmd" > "$TMP_OUTPUT" 2>&1
                    CMD_EXIT=$?
                    
                    echo "========================================="
                    echo "📤 Command output (exit code: $CMD_EXIT):"
                    echo "========================================="
                    cat "$TMP_OUTPUT"
                    echo "========================================="
                    
                    rm -f "$TMP_OUTPUT"
                fi
            fi
        done
    ) &
    FIFO_PID=$!
    echo "✅ Command processor started with PID: $FIFO_PID"
    
    # 提示用户如何使用
    echo ""
    echo "========================================="
    echo "💡 Interactive Command Feature"
    echo "========================================="
    echo "You can send commands to the container using:"
    echo "  echo 'your_command' > /tmp/abution_cmd.fifo"
    echo ""
    echo "Example:"
    echo "  echo 'abution-graph --version' > /tmp/abution_cmd.fifo"
    echo "  echo 'ps aux | grep java' > /tmp/abution_cmd.fifo"
    echo "  echo 'ls -la \$ABUTION_HOME' > /tmp/abution_cmd.fifo"
    echo "  echo 'exit' > /tmp/abution_cmd.fifo  # Stop processor"
    echo "========================================="
}


setup_environment() {
    echo "📝 Setting up environment variables in /etc/profile..."
    
    # 检查是否已存在配置，避免重复添加
    if ! grep -q "ABUTION_HOME=/thutmose/app/abution" /etc/profile; then
        cat >> /etc/profile << 'EOF'

# AbutionGraph Environment Variables
export ABUTION_HOME=/thutmose/app/abution
export ABUTION_CONF_DIR=$ABUTION_HOME/conf
export PATH=$ABUTION_HOME/bin:$PATH

export JAVA_HOME=${ABUTION_HOME}/jdk
export JRE_HOME=${JAVA_HOME}/jre
export CLASSPATH=.:${JAVA_HOME}/lib/dt.jar:${JAVA_HOME}/lib/tools.jar
EOF
        echo "✅ Environment variables added to /etc/profile"
    else
        echo "✅ Environment variables already exist in /etc/profile"
    fi
    
    # 使环境变量在当前会话生效
    echo "🔄 Sourcing /etc/profile..."
    . /etc/profile
    
    # 验证环境变量
    echo "📊 Verifying environment variables:"
    echo "   ABUTION_HOME=${ABUTION_HOME:-'Not set'}"
    echo "   JAVA_HOME=${JAVA_HOME:-'Not set'}"
    echo "   PATH contains: $(echo $PATH | grep -o 'abution[^:]*' || echo 'Not found')"
}


# 在后台启动配置监控
watch_config &

# 设置环境变量
setup_environment

# 设置 FIFO 交互
setup_fifo

# 实时监控日志（包含所有调试日志）
tail -F /thutmose/logs/nginx/access.log /thutmose/logs/nginx/error.log /thutmose/logs/nginx/execute.log /thutmose/logs/nginx/error_requests.log 2>/dev/null | while read line; do
    echo "[$(date '+%H:%M:%S')] $line"
done &

wait