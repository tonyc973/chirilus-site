---
title: "My RTX 5090 was running an LLM 3× slower than it should — and the fix was four lines of config"
date: 2026-05-27
tag: Inference
summary: "qwen3-coder:30b should fit comfortably on a single 5090, but it was silently spilling 14 GB to the CPU for a 256k context window I never used. One Modelfile parameter took inference from 12s to 4s per turn."
---

This week I spent two days debugging why `qwen3-coder:30b` — a model that should fit comfortably on a single RTX 5090's 32 GB of VRAM — was taking 12 seconds to plan a simple operation that a smaller model handled in four.

Spoiler: the GPU was fine. Ollama was fine. The model was fine. I had quietly allocated 28 GB of KV cache for a context window I'd never use, which forced 17% of the model onto the CPU. Every token had to round-trip across PCIe between GPU and system RAM, and the GPU sat at 66% utilization with the rest of the 5090 idle.

Here's the path I walked.

## The setup

I'm building an AI assistant that turns natural-language requests like "create two TAP collection points and route them to my IDS tool" into GraphQL mutations for a network-monitoring platform. One LLM call emits a structured plan validated against a Pydantic schema. Standard structured-output stuff.

I'd been getting solid results from `qwen2.5-coder:32b` — reliable, around 48 seconds for a complex six-resource plan. Then I switched to `qwen3-coder:30b` expecting a speedup on newer hardware. Same prompt, same plan: 12 seconds for a rename, and the model felt like it was crawling.

## The investigation

I started where most people would — measure prompt size, look at the LLM call, check the network. The prompt was ~9500 tokens. Big but well within budget for a 32 GB GPU loading an 18 GB Q4-quantized model.

Then I ran `nvidia-smi dmon` during a request. The GPU peaked at 66% SM utilization and 188W (out of a 575W TDP). That's a GPU waiting for something, not a GPU working hard.

The smoking gun was a single line from `ollama ps`:

```
qwen3-coder:30b   46 GB   17%/83% CPU/GPU   262144
```

Three things in that one row:

- The model was using **46 GB**, not 18.
- **17% of it was running on CPU**, not GPU.
- The loaded context was **262,144 tokens (256k)** — even though my real prompts top out at ~10k.

## Why a "small" model was using 46 GB

KV cache scales linearly with context size. A 256k loaded context for a 30B model with grouped-query attention works out to roughly 28 GB of KV cache memory, on top of 18 GB of weights.

A 32 GB GPU can't hold 46 GB. Ollama silently spilled 14 GB to system RAM and ran those layers on the CPU. Every token of inference had to round-trip across PCIe between GPU and CPU. CPU layers are 10–50× slower than GPU layers, so even though only 17% of the model was offloaded, that 17% was in the critical path and dominated wall-clock time.

That's why the GPU was at 66% utilization. It wasn't compute-bound. It was waiting.

## The fix

The Modelfile for qwen3-coder advertises 256k context by default — its theoretical maximum. I didn't need 256k. I needed 32k.

```
FROM qwen3-coder:30b
PARAMETER num_ctx 32768
```

`ollama create qwen3-coder:30b-32k -f Modelfile`. Five seconds. Updated my config to use the new name, restarted the app, and:

```
qwen3-coder:30b-32k   22 GB   100% GPU   32768
```

Same model. Same hardware. 22 GB instead of 46. Fully on GPU. Inference dropped from 12 seconds to ~4 seconds per turn. GPU SM utilization climbed past 95%. Power hit 450W. The 5090 finally got to do what it was built for.

## Five things I'd want every engineer running local LLMs to know

1. **A model's default context window is a maximum, not a recommendation.** Modelfiles ship with the biggest context the model architecture can handle. That made sense when nobody ran 256k-context LLMs on consumer hardware. Today it silently allocates tens of GB you'll never use.

2. **Ollama's CPU spill is silent.** No warning, no log line. The only signal is the `PROCESSOR` column in `ollama ps` — and you have to know to look at it.

3. **Multi-GPU on consumer cards isn't what it seems.** Consumer RTX cards (40-series onward) dropped NVLink. Two GPUs can only share work over PCIe — ~64 GB/s vs NVLink's ~900 GB/s on data-center cards. Splitting a model across two consumer GPUs is often slower than fitting it on one with a tighter context.

4. **GPU utilization is the diagnostic that doesn't lie.** SM% at 95+ means GPU-bound (healthy). SM% at 60–70% with VRAM headroom means you're starving the GPU — usually on CPU layers, sometimes on PCIe transfers, occasionally on host-side Python overhead. Always check `nvidia-smi dmon`, not just "is the GPU busy?"

5. **OpenAI-compatible API layers don't always pass everything through.** Setting `options.num_ctx` per request via the OpenAI client silently failed on my Ollama version — the OpenAI-compat layer dropped the field. Baking the context into the Modelfile worked unconditionally. When in doubt, change the model's defaults at the source.

## The takeaway

Before you upgrade hardware, check whether you're using the hardware you have. The most valuable command in my toolkit this week was `ollama ps` — one line tells you whether your model is actually running on the GPU you paid for.

What's the most surprising local-LLM performance gotcha you've hit? Curious whether others have run into the silent-CPU-spill pattern.
