---
title: "The 40K-token system prompt that wasn't slow"
date: 2026-05-18
tag: Inference
summary: "I spent a week chasing latency on a local LLM setup. The bottleneck wasn't the GPU, the model, or the quantization — it was the prefill stage doing the same 40K tokens of work on every request."
---

Spent a week chasing latency on my local LLM setup. The answer was not the one I expected.

**The setup.** RTX 5090. Ollama. A ~40K-token system prompt — instructions, tool schemas, few-shot
examples, the usual modern agent stack. Each request was a fresh user query against that fixed preamble.

Inference felt sluggish. My first instinct was the cliché list: bad quantization, model too large,
batch size wrong, maybe a driver issue with the 5090. None of it.

## Where the time was actually going

A transformer forward pass has two phases:

1. **Prefill** — process the entire prompt, build the KV cache.
2. **Decode** — autoregressively generate output tokens, one at a time.

Decode is what people quote when they say "120 tokens/sec." Prefill is what you wait through before
the first token ever appears — **time-to-first-token**, TTFT.

For a 40K-token prompt, prefill is doing forty thousand attention computations before the model
emits a single new token. And here is the cruelty of my setup: I was paying that cost on *every*
request, even though 40,000 of those tokens were byte-identical from one call to the next.

## Prefix caching

The fix has a name: prefix caching. Store the KV cache of the shared prefix once, reuse it for any
subsequent request that starts with the same tokens. The model skips straight to processing the
user's new suffix.

```
request 1:  [system 40K][user query A]  → compute KV for 40K + suffix
request 2:  [system 40K][user query B]  → reuse KV for 40K, compute only suffix
request 3:  [system 40K][user query C]  → reuse KV for 40K, compute only suffix
```

That is the simple version. SGLang's **RadixAttention** generalises it: cached prefixes live in a
radix tree, so *any* request that shares a prefix path — even a partial one — with prior requests
skips the redundant compute. Multi-tenant serving, multi-turn conversations, branching agent trees
all benefit from the same machinery.

## What changed

Same model. Same hardware. Same 40K system prompt. Different serving engine.

TTFT dropped close to an order of magnitude. Not a 10–20% optimisation — the cached path turns a
prefill pass into a lookup. End-to-end latency on short outputs went from "noticeable pause" to
"feels instant." For an agent loop that fires off five or ten LLM calls per user turn, the
cumulative effect is the difference between a toy and something you would ship.

## Lessons I'm keeping

- **Profile before you guess.** TTFT vs. decode is the first split to make. If TTFT dominates,
  no amount of quantisation will save you — you are bottlenecked on prefill compute, not on
  memory bandwidth during decode.
- **Long static prefixes are everywhere now.** Agent system prompts, RAG context, tool catalogues,
  multi-turn history. If the first N tokens of your requests are stable, prefix caching is no
  longer an optimisation — it's the design.
- **The serving engine is an architectural choice.** Ollama and llama.cpp are wonderful for
  prototyping and single-user workloads. For anything resembling production with shared prefixes,
  look at engines that treat prefix caching as a first-class feature: SGLang, vLLM, TGI.

The 5090 is a beast. The real unlock was making it do less.

> If the first N tokens of every request are the same,
> compute them once.

— Antonie
