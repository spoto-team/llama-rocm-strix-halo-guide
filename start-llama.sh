#!/bin/bash
# llama-server 启动脚本 - Strix Halo (Ryzen AI MAX+ 395)
# 使用方法: ./start-llama.sh [context_size] [model_path]

set -e

# 默认值
CONTEXT_SIZE="${1:-262144}"  # 默认 256K 上下文
MODEL_PATH="${2:-/root/.ollama/qwen3.6-35b-a3b-q4_k_m.gguf}"
PORT="${3:-8080}"

# Strix Halo 关键环境变量
export HSA_USE_SVM=0
export HSA_ENABLE_SDMA=0
export HSA_XNACK=1
export OCL_SET_SVM_SIZE=262144
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
export ROCBLAS_TENSILE_LIB_PATH=/opt/rocblas/library

echo "========================================"
echo "Starting llama-server on Strix Halo"
echo "========================================"
echo "Model: $MODEL_PATH"
echo "Context: $CONTEXT_SIZE"
echo "Port: $PORT"
echo ""

# 检查模型文件
if [ ! -f "$MODEL_PATH" ]; then
    echo "ERROR: Model file not found: $MODEL_PATH"
    exit 1
fi

# 创建缓存目录
mkdir -p /tmp/cache

# 停止已运行的 llama-server
pkill -f llama-server 2>/dev/null || true
sleep 2

# 启动 llama-server
nohup /usr/local/bin/llama-server \
    -m "$MODEL_PATH" \
    --host 0.0.0.0 \
    --port "$PORT" \
    -ngl 999 \
    -fa 1 \
    -c "$CONTEXT_SIZE" \
    --parallel 1 \
    --slot-save-path /tmp/cache \
    > /tmp/llama.log 2>&1 &

PID=$!
echo "llama-server started with PID: $PID"
echo ""

# 等待服务就绪
echo "Waiting for service to be ready..."
for i in {1..60}; do
    if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
        echo "✓ llama-server is ready!"
        echo ""
        echo "Health check: curl http://localhost:$PORT/health"
        echo "API endpoint: http://localhost:$PORT/v1/chat/completions"
        exit 0
    fi
    sleep 2
done

echo "✗ Timeout waiting for llama-server to start"
echo "Check logs: tail -f /tmp/llama.log"
exit 1
