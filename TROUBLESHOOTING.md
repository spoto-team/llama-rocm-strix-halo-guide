# 故障排除指南

## 常见问题

### 1. hipMalloc / cudaMalloc 失败

**症状：**
```
cudaMalloc failed: out of memory
alloc_tensor_range: failed to allocate ROCm0 buffer
```

**原因：** Strix Halo 的统一内存架构下，ROCm SVM 管理与大内存分配冲突

**解决：**
```bash
export HSA_USE_SVM=0
export HSA_ENABLE_SDMA=0
export HSA_XNACK=1
export OCL_SET_SVM_SIZE=262144
```

### 2. rocBLAS 库缺失

**症状：**
```
rocBLAS error: Cannot read TensileLibrary.dat: No such file or directory for GPU arch : gfx1151
```

**解决：**
```bash
# 方法1: 复制到容器
nerdctl cp /path/to/rocblas/library ollama-rocm:/opt/rocblas/

# 方法2: 设置环境变量
export ROCBLAS_TENSILE_LIB_PATH=/opt/rocblas/library
```

### 3. libatomic.so.1 缺失

**症状：**
```
error while loading shared libraries: libatomic.so.1
```

**解决：**
```bash
# 宿主机上查找
find /usr -name "libatomic.so*"

# 复制到容器
nerdctl cp /usr/lib/x86_64-linux-gnu/libatomic.so.1 ollama-rocm:/usr/lib/x86_64-linux-gnu/
```

### 4. 模型加载失败 - rope.dimension_sections 错误

**症状：**
```
error loading model hyperparameters: key qwen35moe.rope.dimension_sections has wrong array length; expected 4, got 3
```

**原因：** ollama 的 GGUF 格式与 llama.cpp 不兼容

**解决：** 使用标准 GGUF 格式（如 bartowski 转换的版本），不要使用 ollama 内部格式

### 5. SSH 连接中断

**症状：** 执行长命令时 SSH 断开

**原因：** n5 的 SSH 服务器配置了较短的超时

**解决：**
```bash
# 客户端设置
ssh -o ServerAliveInterval=60 -o ServerAliveCountMax=3 root@192.168.0.206

# 或者写入 ~/.ssh/config
Host n5
    HostName 192.168.0.206
    User root
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

### 6. 端口无法从外部访问

**症状：**
```
Connection refused on port 8080
```

**原因：** 容器端口未映射到宿主机

**解决：**
```yaml
# docker-compose.yaml 中添加端口映射
ports:
  - mode: ingress
    target: 8080
    published: "8080"
    protocol: tcp
```

然后重新创建容器：
```bash
cd /home/spoto/main/syspool/Compose/open-webui-amd-gpu
nerdctl compose up -d ollama
```

### 7. 防火墙阻止访问

**症状：** 端口映射正确但无法连接

**原因：** n5 使用 SYY-INPUT 白名单链

**解决：**
```bash
# 添加 8080 端口到白名单
iptables -I SYY-INPUT -p tcp --dport 8080 -j ACCEPT
iptables-save > /etc/iptables/rules.v4
```

### 8. llama-server 启动后崩溃

**症状：** 启动后立即退出，无错误日志

**原因：** 可能是 rocBLAS 库路径不正确

**解决：**
```bash
# 检查库文件是否存在
nerdctl exec ollama-rocm ls -la /opt/rocblas/library/
nerdctl exec ollama-rocm ls -la /usr/lib/x86_64-linux-gnu/libatomic.so.1

# 手动测试启动查看完整错误
nerdctl exec ollama-rocm bash -c "
  export HSA_USE_SVM=0
  export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
  /usr/local/bin/llama-server --version
"
```

### 9. 性能低于预期

**症状：** 生成速度明显低于参考值

**可能原因：**
1. 模型未完全 GPU 加载（检查 `-ngl 999`）
2. CPU 频率被限制（检查电源管理）
3. 温度过热导致降频

**诊断：**
```bash
# 检查 GPU 温度
nerdctl exec ollama-rocm bash -c "cat /sys/class/hwmon/hwmon*/temp1_input 2>/dev/null || true"

# 检查 CPU 频率
cat /proc/cpuinfo | grep MHz | head -5

# 检查进程内存
ps aux | grep llama-server | grep -v grep
```

### 10. 缓存不生效

**症状：** 多轮对话时 TTFT 没有降低

**原因：** 
- llama-server 需要 `--slot-save-path` 参数
- 或者客户端需要保持 session_id

**解决：**
```bash
# 启动时添加缓存路径
llama-server ... --slot-save-path /tmp/cache

# API 调用时保持 slot_id
# 第一次请求后记录 slot_id
# 后续请求使用相同的 slot_id
```

## 调试技巧

### 查看详细日志

```bash
# llama-server 详细日志
llama-server ... --verbose 2>&1 | tee /tmp/llama-debug.log

# ROCm 调试信息
export AMD_LOG_LEVEL=3
export HIP_LAUNCH_BLOCKING=1
```

### 测试内存分配

```bash
# 检查可用 GPU 内存
cat /sys/class/drm/card0/device/mem_info_vram_total
cat /sys/class/drm/card0/device/mem_info_vram_used
cat /sys/class/drm/card0/device/mem_info_gtt_total
cat /sys/class/drm/card0/device/mem_info_gtt_used

# KFD 拓扑信息
cat /sys/class/kfd/kfd/topology/nodes/0/properties
cat /sys/class/kfd/kfd/topology/nodes/0/mem_banks/0/properties
```

### 网络诊断

```bash
# 检查端口监听
ss -tlnp | grep 8080

# 检查 iptables 规则
iptables -t nat -L PREROUTING -n | grep 8080
iptables -L SYY-INPUT -n | grep 8080

# 容器网络
nerdctl inspect ollama-rocm | grep IPAddress
```

## 获取帮助

如果以上方法无法解决问题：

1. 收集以下信息：
   - `llama-server --version` 输出
   - `/tmp/llama.log` 完整日志
   - `rocminfo` 输出（如果可用）
   - `dmesg | grep -i amdgpu | tail -20`

2. 在以下社区寻求帮助：
   - [ROCm GitHub Issues](https://github.com/ROCm/ROCm/issues)
   - [llama.cpp GitHub Issues](https://github.com/ggml-org/llama.cpp/issues)
   - [Strix Halo LLM Performance](https://github.com/visorcraft/strix-halo-llm-perf)
