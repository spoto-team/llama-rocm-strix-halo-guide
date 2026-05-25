# llama.cpp ROCm 部署指南 - Strix Halo (Ryzen AI MAX+ 395)

> 在 AMD Ryzen AI MAX+ 395 (Radeon 8060S, gfx1151) 上部署 llama.cpp 运行 Qwen3.6-35B 的完整记录

## 硬件环境

| 组件 | 规格 |
|------|------|
| CPU | AMD Ryzen AI MAX+ 395 (32C/64T, Zen 5) |
| GPU | Radeon 8060S (gfx1151, RDNA 3.5, 40 CUs) |
| 内存 | 128GB LPDDR5X-8000 统一内存 |
| 系统 | Debian 12 (NAS) |

## 关键问题与解决方案

### 1. ROCm 内存分配失败

**现象：**
```
cudaMalloc failed: out of memory
alloc_tensor_range: failed to allocate ROCm0 buffer of size 20869704192
```

**原因：** Strix Halo 的统一内存架构下，ROCm 的 SVM (Shared Virtual Memory) 管理与大内存分配冲突

**解决方案：**
```bash
export HSA_USE_SVM=0
export HSA_ENABLE_SDMA=0
export HSA_XNACK=1
export OCL_SET_SVM_SIZE=262144
```

### 2. rocBLAS 库缺失

**现象：**
```
rocBLAS error: Cannot read /usr/lib/x86_64-linux-gnu/rocblas/library/TensileLibrary.dat
```

**解决方案：** 从预编译包复制 rocblas 库到容器内：
```bash
nerdctl cp /tmp/llama-rocm/rocblas ollama-rocm:/opt/
# 或者映射到默认路径
mkdir -p /usr/lib/x86_64-linux-gnu/rocblas/library
cp /opt/rocblas/library/* /usr/lib/x86_64-linux-gnu/rocblas/library/
```

### 3. libatomic 缺失

**现象：**
```
error while loading shared libraries: libatomic.so.1
```

**解决方案：**
```bash
nerdctl cp /usr/lib/x86_64-linux-gnu/libatomic.so.1 ollama-rocm:/usr/lib/x86_64-linux-gnu/
```

## 部署步骤

### 1. 准备环境

基于已有的 ollama/ollama:rocm 容器（已包含 ROCm runtime）：

```bash
# 确保 compose 配置包含端口映射
cat docker-compose.yaml
```

### 2. 复制 llama.cpp 二进制文件

```bash
# 下载预编译的 gfx1151 版本
# 来源: https://github.com/lemonade-sdk/llamacpp-rocm/releases/download/b1223/llama-b1223-ubuntu-rocm-gfx1151-x64.zip

cd /tmp
curl -L -o llama-rocm-gfx1151.zip \
  'https://github.com/lemonade-sdk/llamacpp-rocm/releases/download/b1223/llama-b1223-ubuntu-rocm-gfx1151-x64.zip'
python3 -c 'import zipfile; zipfile.ZipFile("llama-rocm-gfx1151.zip").extractall("llama-rocm")'

# 复制到容器
nerdctl cp /tmp/llama-rocm/llama-server ollama-rocm:/usr/local/bin/
nerdctl cp /tmp/llama-rocm/llama-cli ollama-rocm:/usr/local/bin/
nerdctl cp /tmp/llama-rocm/llama-bench ollama-rocm:/usr/local/bin/
nerdctl exec ollama-rocm chmod +x /usr/local/bin/llama-*

# 复制共享库
for f in /tmp/llama-rocm/*.so*; do
  nerdctl cp "$f" ollama-rocm:/usr/lib/x86_64-linux-gnu/
done

# 复制 rocblas 库
nerdctl cp /tmp/llama-rocm/rocblas ollama-rocm:/opt/

# 复制 libatomic
nerdctl cp /usr/lib/x86_64-linux-gnu/libatomic.so.1 \
  ollama-rocm:/usr/lib/x86_64-linux-gnu/
```

### 3. 准备模型

```bash
# 从 SMB 共享复制 GGUF 模型
# 模型路径: //192.168.0.233/tools/models/Qwen3.6-35B-A3B/qwen3.6-35b-a3b-q4_k_m.gguf

# 挂载 SMB
mount -t cifs //192.168.0.233/tools /mnt/tools \
  -o username=test,password=test1234,vers=3.0

# 复制到容器挂载目录
cp /mnt/tools/models/Qwen3.6-35B-A3B/qwen3.6-35b-a3b-q4_k_m.gguf \
  /home/spoto/main/syspool/Compose/open-webui-amd-gpu/ollama/
```

### 4. 启动 llama-server

```bash
nerdctl exec ollama-rocm bash -c "
  export HSA_USE_SVM=0
  export HSA_ENABLE_SDMA=0
  export HSA_XNACK=1
  export OCL_SET_SVM_SIZE=262144
  export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
  export ROCBLAS_TENSILE_LIB_PATH=/opt/rocblas/library
  
  /usr/local/bin/llama-server \
    -m /root/.ollama/qwen3.6-35b-a3b-q4_k_m.gguf \
    --host 0.0.0.0 \
    --port 8080 \
    -ngl 999 \
    -fa 1 \
    -c 262144 \
    --parallel 1
"
```

### 5. 验证运行

```bash
# 检查健康状态
curl -s http://192.168.0.206:8080/health
# {"status":"ok"}

# 测试 API
curl -s http://192.168.0.206:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.6-35b-a3b-q4_k_m.gguf",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }'
```

## 性能基准

### 测试环境
- llama.cpp: b1223 (commit 48cda24)
- ROCm: 容器内自带 (ollama/ollama:rocm)
- 模型: Qwen3.6-35B-A3B Q4_K_M (21GB)
- 环境变量: HSA_USE_SVM=0, HSA_ENABLE_SDMA=0, HSA_XNACK=1
- 缓存配置: `--slot-save-path /tmp/slot_cache`

### 单轮性能（不同上下文长度）

| 上下文 | Prompt Tokens | Output Tokens | TTFT (ms) | Prefill (t/s) | Gen (t/s) | Total (s) |
|--------|--------------|---------------|-----------|---------------|-----------|-----------|
| 0k | 16 | 100 | 164.2 | 97.4 | **55.5** | 2.10 |
| 4k | 2,296 | 100 | 2,121.1 | 1,082 | **54.7** | 4.12 |
| 8k | 4,582 | 100 | 2,612.2 | 1,754 | **54.0** | 4.61 |
| 64k | 36,582 | 100 | 47,009.2 | 778 | **46.5** | 49.42 |
| 120k | 68,582 | 100 | 73,071.8 | 939 | **40.9** | 75.95 |
| 240k | 137,153 | 100 | 254,651.0 | 539 | **32.9** | 258.10 |

### tg128 专项测试

| 指标 | 数值 |
|------|------|
| 平均 Generation Speed | **55.3 t/s** |
| TTFT | ~70 ms |

### 与参考数据对比

| 后端 | 参考 tg128 | n5 实际 |
|------|-----------|---------|
| ROCm 7.2 (参考) | 39.7 t/s | **55.3 t/s** |
| Vulkan RADV (参考) | 39 t/s | - |
| Vulkan AMDVLK (参考) | 49 t/s | - |

### Agent Benchmark - 缓存验证测试

**测试配置：**
- 工具: agent-bench.py (llm-inference-benchmarking skill)
- 目标上下文: 240,000 tokens
- 每轮输入: ~500 tokens
- 每轮输出: 100 tokens
- 缓存: `--slot-save-path /tmp/slot_cache` 启用

**测试结果：**

| 指标 | 数值 |
|------|------|
| 总轮数 | **227 轮** |
| 最终上下文 | **240,673 tokens** |
| 缓存状态 | ✅ **生效** |
| 测试耗时 | ~4.5 小时 |

**缓存验证分析：**

TTFT 随轮数变化（关键节点）：

| 轮数 | 上下文 | TTFT (ms) | 状态 |
|------|--------|-----------|------|
| 10 | ~10K | 1,600 | 基准 |
| 50 | ~53K | 3,100 | 线性增长 |
| 100 | ~106K | 4,800 | 线性增长 |
| 150 | ~159K | 6,500 | 线性增长 |
| 200 | ~212K | 8,100 | 线性增长 |
| 227 | ~240K | 9,048 | 线性增长 |

**结论：**
- ✅ TTFT 呈**线性增长**，表明每轮只处理新输入的 ~956 tokens
- ✅ 无突然跳升（>3× 基线），缓存未失效
- ✅ `--slot-save-path` 确保缓存持久化到磁盘，避免内存驱逐

**性能衰减趋势：**

| 阶段 | Prefill (t/s) | Generation (t/s) |
|------|--------------|------------------|
| 早期 (0-50轮) | 585 → 300 | 52 → 43 |
| 中期 (50-150轮) | 300 → 150 | 43 → 35 |
| 后期 (150-227轮) | 150 → 105 | 35 → 25.5 |

完整数据: [results/agent_bench_llama_cache.json](results/agent_bench_llama_cache.json)  
可视化报告: [results/agent_bench_llama_cache.html](results/agent_bench_llama_cache.html)

## 内存占用分析

### GPU 内存架构

Strix Halo 使用统一内存架构，ROCm 将其分为：
- **VRAM**: 2GB (GPU 专用)
- **GTT**: 50GB+ (系统内存映射给 GPU)

### 实际占用

| 组件 | 大小 |
|------|------|
| 模型权重 | ~21GB |
| KV cache (256K) | ~4.6GB (f16, 10 layers) |
| Compute buffer | ~493MB |
| Host compute buffer | ~136MB |
| **总计** | **~27-28GB** |

### 进程内存

```
VmPeak:  88.8 GB (峰值虚拟内存)
VmHWM:   20.9 GB (峰值物理内存)
VmRSS:    2.5 GB (当前物理内存)
```

## 关键配置说明

### HSA_USE_SVM=0

禁用共享虚拟内存管理，解决 Strix Halo 上大内存分配的 SVM thrashing 问题。

**不设置时：**
- hipMalloc >4GB 失败
- 模型无法加载到 GPU

**设置后：**
- 大内存分配正常
- 模型完全 GPU 可访问

### --slot-save-path

**关键参数**，启用 llama-server 的缓存持久化：

```bash
llama-server ... --slot-save-path /tmp/slot_cache
```

**作用：**
- 将 KV cache 检查点持久化到磁盘
- 防止长上下文下缓存被内存驱逐
- 确保 prefix caching 在 240K+ 上下文仍然有效

**测试验证：**
- 无 `--slot-save-path`: 缓存可能在 ~3-5 轮后失效（llama-server 默认行为）
- 有 `--slot-save-path`: 缓存稳定到 240K+ 上下文（本测试验证）

### -ngl 999

将所有层卸载到 GPU。对于 qwen3.6-35b：
- 总层数: 40
- 实际 GPU 层数: 40 (MoE 模型，但 attention 层全部 GPU 执行)

### -fa 1

启用 Flash Attention，减少 KV cache 内存占用。

## 已知限制

1. **ollama 缓存不工作**: ollama 0.24.0 的 prefix caching 对 qwen3.6 不生效（template 问题）
2. **ROCm 驱动限制**: 需要 HSA_USE_SVM=0 才能分配大内存
3. **GTT 性能**: 模型权重在 GTT 中，比专用 VRAM 略慢
4. **长上下文 TTFT**: 240K 上下文需要 ~9 秒预热（每轮）
5. **缓存冷启动**: 首次加载模型后，前几轮 TTFT 较高（模型预热）

## 参考链接

- [ROCm Issue #5940 - Strix Halo Memory Allocations](https://github.com/ROCm/ROCm/issues/5940)
- [ROCm HIP Issue #3644 - hipMalloc >4GB](https://github.com/ROCm/HIP/issues/3644)
- [TheRock Discussion #2684 - HSA_USE_SVM=0 Fix](https://github.com/ROCm/TheRock/discussions/2684)
- [llama.cpp ROCm gfx1151 Prebuilt](https://github.com/lemonade-sdk/llamacpp-rocm)
- [Strix Halo LLM Performance Benchmarks](https://github.com/visorcraft/strix-halo-llm-perf)
- [llm-inference-benchmarking Skill](https://github.com/spoto-team/agent-bench)

## 许可证

MIT License - 自由使用和改进
