---
name: easyrhythm
version: 1.2.0
description: "多平台智能客服系统。飞书/Telegram/Discord/微信四平台适配+向量知识库+RAG检索。当需要搭建智能客服、配置自动回复、管理知识库时使用。"
author: AtomCollide-智械工坊团队
license: MIT

triggers:
  - 智能客服
  - 对话系统
  - chatbot
  - easyrhythm
  - 松弛有度
---

# EasyRhythm 松弛有度

> 📖 详细文档见 `references/` 目录

Agent智能客服系统，支持多Agent编排、LLM护栏、SSE流式输出和CRM集成。

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

## 工作流

使用此技能时，按以下步骤执行：
- [ ] 1. 确认用户需求和使用场景
- [ ] 2. 加载相关代码和配置
- [ ] 3. 执行核心功能
- [ ] 4. 验证输出结果
- [ ] 5. 反馈给用户

## 2026-07-03 运行时增强

- 新增客服上下文裁剪与改写验证：保留重要承诺、限制过度扩写、校验必要术语不丢失。
- 验证：新增模块通过 py_compile 和定向 pytest，代码不依赖外部服务。
