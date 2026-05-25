#!/usr/bin/env python3
"""
llama.cpp benchmark script for Strix Halo (Ryzen AI MAX+ 395)
Tests generation speed at different context lengths
"""

import requests
import json
import time
import sys

# Configuration
URL = "http://192.168.0.206:8080/v1/chat/completions"
MODEL = "qwen3.6-35b-a3b-q4_k_m.gguf"


def generate_text(n_tokens):
    """Generate text of approximately N tokens"""
    words = ["analysis", "process", "system", "data", "model",
             "compute", "memory", "cache", "token", "context"]
    text = ""
    i = 0
    while len(text) < n_tokens * 4:
        text += words[i % len(words)] + " "
        i += 1
    return text[:n_tokens * 4]


def run_benchmark(label, prompt_tokens, max_tokens):
    """Run a single benchmark test"""
    prompt = generate_text(prompt_tokens)

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False
    }

    start = time.time()
    try:
        resp = requests.post(URL, json=payload, timeout=600)
        data = resp.json()
        elapsed = time.time() - start

        if "error" in data:
            return {
                "label": label,
                "error": data["error"]
            }

        usage = data.get("usage", {})
        timings = data.get("timings", {})

        return {
            "label": label,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "ttft_ms": timings.get("prompt_ms", 0),
            "gen_tps": timings.get("predicted_per_second", 0),
            "total_s": elapsed
        }

    except Exception as e:
        return {
            "label": label,
            "error": str(e)
        }


def main():
    print("=" * 70)
    print("llama.cpp Benchmark - Strix Halo (Ryzen AI MAX+ 395)")
    print("=" * 70)
    print()

    # Test configurations: (label, prompt_tokens, max_output_tokens)
    tests = [
        ("0k", 10, 100),
        ("4k", 4000, 100),
        ("8k", 8000, 100),
        ("64k", 64000, 100),
        ("120k", 120000, 100),
        ("240k", 240000, 100),
    ]

    results = []

    print(f"{'Context':>8} | {'Prompt':>8} | {'Output':>8} | {'TTFT(ms)':>10} | {'Gen(t/s)':>10} | {'Total(s)':>8}")
    print("-" * 70)

    for label, prompt_tokens, max_tokens in tests:
        result = run_benchmark(label, prompt_tokens, max_tokens)
        results.append(result)

        if "error" in result:
            print(f"{label:>8} | ERROR: {result['error']}")
        else:
            print(f"{result['label']:>8} | {result['prompt_tokens']:>8} | "
                  f"{result['output_tokens']:>8} | {result['ttft_ms']:>10.1f} | "
                  f"{result['gen_tps']:>10.1f} | {result['total_s']:>8.2f}")

        # Wait between tests
        time.sleep(5)

    # Summary
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)

    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        avg_gen = sum(r["gen_tps"] for r in valid_results) / len(valid_results)
        print(f"Average generation speed: {avg_gen:.1f} t/s")
        print(f"Tests completed: {len(valid_results)}/{len(tests)}")

    # Save results
    with open("/tmp/benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: /tmp/benchmark_results.json")


if __name__ == "__main__":
    main()
