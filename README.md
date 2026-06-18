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
- **CRM集成模式 / CRM Integration Patterns** — 参考 eShopSupport（.NET Aspire微服务架构）和悟空CRM（中国市场CRM集成）
- **ChatKit前端 / ChatKit UI** — 基于 @openai/chatkit-react 的高质量聊天界面

## 🏗️ Architecture / 系统架构

```
┌─────────────────────────────────────────────┐
│                  Next.js UI                 │
│         (ChatKit + Agent Panel)             │
└──────────────────┬──────────────────────────┘
                   │ SSE
┌──────────────────▼──────────────────────────┐
│            Python Backend (FastAPI)          │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Triage  │→ │ Special  │→ │ Guardrails│  │
│  │ Agent   │  │ Agents   │  │           │  │
│  └─────────┘  └──────────┘  └───────────┘  │
└─────────────────────────────────────────────┘
```

Inspired by:
- **eShopSupport** — .NET Aspire 微服务架构，支持文本分类、情感分析、摘要生成
- **悟空CRM** — 中国市场CRM集成，多语言支持，一键部署

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

Frontend: http://localhost:3000 | Backend: http://localhost:8000

## 🤖 Agent 说明 / Agents Included

| Agent | 说明 |
|-------|------|
| Triage Agent | 入口路由，智能分配到专业Agent |
| Flight Information Agent | 航班状态、中转风险、备选方案 |
| Booking & Cancellation Agent | 预订、改签、取消 |
| Seat & Special Services Agent | 座位管理、医疗/前排需求 |
| FAQ Agent | 政策问答（行李、赔偿、WiFi等） |
| Refunds & Compensation Agent | 开case、酒店/餐食补偿 |

## 📦 技术栈 / Tech Stack

- **Backend**: Python 3.11+, FastAPI, openai-agents SDK
- **Frontend**: Next.js, TypeScript, Tailwind CSS, @openai/chatkit-react
- **Patterns**: 多Agent编排, LLM Guardrails, SSE Streaming

## 📄 License

MIT License. Copyright 2026 AtomCollide-智械工坊.

---

*Built with ❤️ by AtomCollide-智械工坊团队*
