## 一键安装 / One-click Quickstart

```bash
bash install.sh
python3 scripts/doctor.py
python3 scripts/smoke.py
```

- `bash install.sh`：自动执行 setup + smoke，适合第一次使用。
- `python3 scripts/doctor.py`：检查环境、入口文件和产品门禁，失败时给出修复建议。
- `python3 scripts/smoke.py`：执行产品收敛门禁和轻量核心冒烟验证。

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

---



---

## 🚀 加入AtomCollide-AI智能体实验室

**元素碰撞-AtomCollide-AI 智能体实验室** 是一个专注于AI领域的开源组织，汇聚了众多优秀学习者。

### 核心价值

**找工作：更省力，也更精准**
- 一线大厂内推通道（字节、阿里、腾讯等）
- 全链路求职赋能包（面试题库、简历优化、晋升指导）
- 线下技术沙龙 & 人脉网络

**学AI测试：真正落地，拒绝空谈**
- 从0到1实战落地体系（Skills、MCP、RAG、AI IDE等）
- 独家自研资料与工具矩阵
- 前沿技术同步与提效方案

### 知识库

- [踩坑合集](https://vcnvmnln7wit.feishu.cn/wiki/CjV9wG8IHiIpWikCdFEcxfErnne)
- [商业化案例库](https://vcnvmnln7wit.feishu.cn/wiki/LdIxwlrKGibFEVkWMocc2K9KnBh)
- [科普专栏](https://vcnvmnln7wit.feishu.cn/wiki/K1RPwM8zji9ZchkxlOmcivUgnJe)
- [Open Build](https://vcnvmnln7wit.feishu.cn/wiki/CThswol0PiNJJbkhgT1cZIxanLb)
- [LLM/Agent/研究报告知识库](https://vcnvmnln7wit.feishu.cn/wiki/KwGQwS2TciT2EdkSBBtcYnbsnSd)
- [Skill封装合集](https://vcnvmnln7wit.feishu.cn/wiki/PDfpwqJZUibTyBkUa7TcZZ6Onpd)
- [社区治理运营知识库](https://vcnvmnln7wit.feishu.cn/wiki/MSEGwrdnTiiF9Dk8qCVcNW6InJg)

### 加入社群

| 社群 | 链接 |
|------|------|
| AI探索交流1区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=074vd565-6084-455c-ac52-9703e89a0697) |
| AI探索交流2区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=60bj94f0-1a67-48a7-abbb-9172b161c2b0) |
| AI探索交流3区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=13do1920-db46-4444-b635-005680beaf58) |
| AI探索交流4区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=f17o1b86-06f6-4f10-911a-69a299a25fe3) |
| AI探索交流5区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=2bbh6ab6-22c2-4753-b973-74bb1a2edcc9) |
| AI探索交流6区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=d19r19f7-2f47-42ba-b1ec-cb0342cf2e80) |
| AI探索交流7区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=fe9vdacc-7316-4b4d-ae4a-fdbcf56315e6) |
| AI探索交流8区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=103kfae8-1fd7-424f-984f-d66c210e42d1) |
| AI探索交流9区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=239p3cad-2f83-4baa-a230-f40386067548) |
| AI探索交流10区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=880r7cf5-3638-45ff-afb9-7944de991872) |
| AI探索交流-网文作家 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=6a3v579b-ab43-4e1a-87f9-be63bab88da7) |
| AI探索交流群-音乐达人 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=76at299e-73da-4eeb-9eba-32161e98f2f8) |
| AI探索交流群-微笑驿站 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=f2av73d0-6bb4-4a9f-9095-5fbbe83e49ec) |

---

*AtomCollide-智械工坊团队出品*

---

## 组织与社群入口

**元素碰撞 · AtomCollide-AI 智能体实验室**：面向学习者、创作者与自动化实践者，持续沉淀可复用的 AI Agent 产品、工作流与工程经验。使命：**for the learner**。

> 请选择 1 个常用社群加入，内容全域同步，无需重复加入。

### 知识库

| 知识库 | 链接 |
|---|---|
| 踩坑合集 | [进入](https://vcnvmnln7wit.feishu.cn/wiki/CjV9wG8IHiIpWikCdFEcxfErnne) |
| 商业化案例库 | [进入](https://vcnvmnln7wit.feishu.cn/wiki/LdIxwlrKGibFEVkWMocc2K9KnBh) |
| 科普专栏 | [进入](https://vcnvmnln7wit.feishu.cn/wiki/K1RPwM8zji9ZchkxlOmcivUgnJe) |
| Open Build | [进入](https://vcnvmnln7wit.feishu.cn/wiki/CThswol0PiNJJbkhgT1cZIxanLb) |
| LLM / Agent / 研究报告 | [进入](https://vcnvmnln7wit.feishu.cn/wiki/KwGQwS2TciT2EdkSBBtcYnbsnSd) |
| Skill 封装合集 | [进入](https://vcnvmnln7wit.feishu.cn/wiki/PDfpwqJZUibTyBkUa7TcZZ6Onpd) |
| 社区治理运营 | [进入](https://vcnvmnln7wit.feishu.cn/wiki/MSEGwrdnTiiF9Dk8qCVcNW6InJg) |

### 社群邀请

| 社群 | 链接 |
|---|---|
| AI 探索交流 1 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=074vd565-6084-455c-ac52-9703e89a0697) |
| AI 探索交流 2 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=60bj94f0-1a67-48a7-abbb-9172b161c2b0) |
| AI 探索交流 3 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=13do1920-db46-4444-b635-005680beaf58) |
| AI 探索交流 4 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=f17o1b86-06f6-4f10-911a-69a299a25fe3) |
| AI 探索交流 5 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=2bbh6ab6-22c2-4753-b973-74bb1a2edcc9) |
| AI 探索交流 6 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=d19r19f7-2f47-42ba-b1ec-cb0342cf2e80) |
| AI 探索交流 7 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=fe9vdacc-7316-4b4d-ae4a-fdbcf56315e6) |
| AI 探索交流 8 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=103kfae8-1fd7-424f-984f-d66c210e42d1) |
| AI 探索交流 9 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=239p3cad-2f83-4baa-a230-f40386067548) |
| AI 探索交流 10 区 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=880r7cf5-3638-45ff-afb9-7944de991872) |
| AI 探索交流 — 网文作家 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=6a3v579b-ab43-4e1a-87f9-be63bab88da7) |
| AI 探索交流群 — 音乐达人 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=76at299e-73da-4eeb-9eba-32161e98f2f8) |
| AI 探索交流群 — 微笑驿站 | [加入](https://applink.feishu.cn/client/chat/chatter/add_by_link?link_token=f2av73d0-6bb4-4a9f-9095-5fbbe83e49ec) |

---

AtomCollide-智械工坊团队出品。更多产品见：[AtomCollide Product Matrix](https://503496348-ops.github.io/atomcollide-product-matrix/)。

## Governance Links

- [LICENSE](LICENSE)
- [CHANGELOG](CHANGELOG.md)
- [SECURITY](SECURITY.md)
- [CONTRIBUTING](CONTRIBUTING.md)



## 2026-07-03 运行时增强

- 新增客服上下文裁剪与改写验证：保留重要承诺、限制过度扩写、校验必要术语不丢失。
- 交付物包含可导入模块与定向单元测试。

## 2026-07-03 产品收敛门禁

- 新增 `scripts/product_convergence_gate.py`：从远端干净 clone 后可运行 `python3 scripts/product_convergence_gate.py --json`，检查 SKILL/README、入口文件、smoke 目标、测试与外部融合引用是否自洽。
- 新增 `tests/test_product_convergence_gate.py`：确保门禁在产品仓库中真实可执行，避免后续增强只停留在孤岛模块。
