---
name: easyrhythm
version: 1.0.0
description: 松弛有度（EasyRhythm）— Agent智能客服系统。多Agent编排+LLM护栏+SSE流式+CRM集成
author: AtomCollide-智械工坊团队
license: MIT
---

# EasyRhythm 松弛有度

Agent智能客服系统，基于OpenAI Agents SDK构建，支持多Agent编排、LLM护栏、SSE流式输出和CRM集成。

## Capabilities
- Multi-agent orchestration with automatic triage routing
- LLM guardrails (relevance check, jailbreak prevention)
- SSE streaming for real-time agent output
- CRM integration patterns (enterprise support ticket systems, multi-market CRM integration)
- ChatKit-based chat UI with agent visualization panel
- **Intent Classification Engine** — Hybrid pattern+LLM intent classification with confidence scoring, low-confidence fallback handling, and automatic agent routing (comparable to Rasa NLU)
- **Entity Extraction Pipeline** — Regex + LLM entity extraction for flight numbers, confirmation codes, seat numbers, airports, dates, baggage tags, and more — auto-hydrates conversation context

## Dependencies

- Python 3.11+
- Node.js 18+
- OPENAI_API_KEY environment variable
