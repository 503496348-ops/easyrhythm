# EasyRhythm 松弛有度 — Agent 智能客服系统

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![NextJS](https://img.shields.io/badge/Built_with-NextJS-blue)
![Python](https://img.shields.io/badge/Backend-Python_3.11+-yellow)
![OpenAI API](https://img.shields.io/badge/Powered_by-OpenAI_API-orange)

> 松弛有度（EasyRhythm）— 多Agent编排 + LLM护栏 + SSE流式 + CRM集成的智能客服系统。

**EasyRhythm** is an intelligent customer service system built on multi-agent orchestration. Based on [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), it integrates patterns from enterprise-grade support ticket systems and CRM platforms to deliver a production-ready customer service solution.

---

## ✨ 核心特性 / Key Features
- **多Agent编排 / Multi-Agent Orchestration** — Triage Agent 自动路由到专业 Agent（航班、预订、座位、FAQ、退款等）
- **LLM护栏 / Guardrails** — 内置相关性检查和防越狱护栏，确保对话安全
- **SSE流式输出 / Streaming** — 实时流式显示Agent推理和回复过程
- **CRM集成模式 / CRM Integration Patterns** — 参考企业级工单系统和多市场CRM集成方案
- **ChatKit前端 / ChatKit UI** — 基于 @openai/chatkit-react 的高质量聊天界面
- **意图分类引擎 / Intent Classification Engine** — 混合模式+LLM意图分类，支持置信度评分、低置信度回退处理和自动Agent路由（对标Rasa NLU）
- **实体抽取管道 / Entity Extraction Pipeline** — 正则+LLM实体抽取，支持航班号、确认码、座位号、机场、日期、行李标签等，自动填充对话上下文

## 🏗️ Architecture / 系统架构

```
┌─────────────────────────────────────────────┐
│                  Next.js UI                 │
│         (ChatKit + Agent Panel)             │
└──────────────────┬──────────────────────────┘
                   │ SSE
┌──────────────────▼──────────────────────────┐
│            Python Backend (FastAPI)          │
│  ┌──────────────┐  ┌───────────────────┐    │
│  │ Intent       │  │ Entity            │    │
│  │ Classifier   │→ │ Extractor         │    │
│  └──────┬───────┘  └────────┬──────────┘    │
│         │ Confidence        │ Context       │
│         │ + Routing         │ Hydration     │
│  ┌──────▼───────────────────▼──────────┐    │
│  │ Triage → Specialized Agents         │    │
│  │ (Flight, Booking, Seat, FAQ, Refund)│    │
│  └─────────────────┬───────────────────┘    │
│  ┌─────────────────▼───────────────────┐    │
│  │ Guardrails (Relevance + Jailbreak)  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

Built with enterprise-grade patterns for multi-agent orchestration, conversation management, and quality evaluation.

## 🚀 Quick Start / 快速开始

### 1. 设置API密钥 / Set API Key

```bash
export OPENAI_API_KEY=your_api_key
```

### 2. 安装后端依赖 / Install Backend

```bash
cd python-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 安装前端依赖 / Install Frontend

```bash
cd ui
npm install
```

### 4. 运行 / Run

```bash
# 后端 Backend
cd python-backend && python -m uvicorn main:app --reload --port 8000

# 前端 Frontend (also starts backend)
cd ui && npm run dev
```

> Configure `OPENAI_API_KEY` and run backend + frontend as described above.

## 🤖 Agent 说明 / Agents Included
| Agent | 说明 |
|-------|------|
| Intent Classifier | 意图分类引擎，混合模式+LLM，支持置信度评分和回退处理 |
| Entity Extractor | 实体抽取管道，正则+LLM抽取航班号、座位号、机场等结构化实体 |
| Triage Agent | 入口路由，智能分配到专业Agent |
| Flight Information Agent | 航班状态、中转风险、备选方案 |
| Booking & Cancellation Agent | 预订、改签、取消 |
| Seat & Special Services Agent | 座位管理、医疗/前排需求 |
| FAQ Agent | 政策问答（行李、赔偿、WiFi等） |
| Refunds & Compensation Agent | 开case、酒店/餐食补偿 |

## 🔌 API 端点 / API Endpoints

| Method | Path | 说明 |
|--------|------|------|
| POST | `/chatkit` | ChatKit 消息处理 (SSE) |
| GET | `/chatkit/state` | 获取线程状态 |
| GET | `/chatkit/bootstrap` | 初始化引导 |
| GET | `/chatkit/state/stream` | 状态SSE流 |
| POST | `/analyze` | **NEW** 意图分类+实体抽取分析 (无需Agent运行) |
| GET | `/health` | 健康检查 |

### POST /analyze 示例
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the status of flight PA441?"}'

# Response:
# {
#   "intent": {"intent": "flight_status", "confidence": 0.96, "source": "pattern", ...},
#   "entities": [{"entity_type": "flight_number", "value": "PA441", "confidence": 0.92, ...}],
#   "message": "What is the status of flight PA441?"
# }
```

## 📦 技术栈 / Tech Stack

- **Backend**: Python 3.11+, FastAPI, openai-agents SDK
- **Frontend**: Next.js, TypeScript, Tailwind CSS, @openai/chatkit-react
- **NLU**: 意图分类引擎 (Pattern+LLM), 实体抽取管道 (Regex+LLM), 置信度评分
- **Patterns**: 多Agent编排, LLM Guardrails, SSE Streaming, 低置信度回退

## 📄 License

MIT License. Copyright 2026 AtomCollide-智械工坊.

---

*Built with ❤️ by AtomCollide-智械工坊团队*
