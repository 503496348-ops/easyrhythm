---
name: easyrhythm
description: "松弛有度智能客服 — 意图分类、实体抽取、FastAPI 服务"
triggers:
  - "客服"
  - "意图分类"
  - "实体抽取"
  - "智能客服"
  - "easyrhythm"
---

# EasyRhythm — 松弛有度智能客服

航空客服场景的意图分类 + 实体抽取 + FastAPI 服务端。

## 核心能力

| 命令 | 说明 |
|------|------|
| `easyrhythm serve` | 启动 FastAPI 服务 |
| `easyrhythm classify <text>` | 意图分类 |
| `easyrhythm extract <text>` | 实体抽取 |
| `easyrhythm info` | 产品信息 |

## 快速开始

```bash
# 启动服务
python3 scripts/cli.py serve --port 8000

# 意图分类
python3 scripts/cli.py classify "帮我查一下今天的航班"

# 实体抽取
python3 scripts/cli.py extract "北京到上海的航班"
```

## 架构

- `python-backend/server.py` — FastAPI 服务端
- `python-backend/airline/intent_classifier.py` — 意图分类器
- `python-backend/airline/entity_extractor.py` — 实体抽取器
- `python-backend/airline/tools.py` — 航空工具集
- `python-backend/memory_store.py` — 记忆存储

## 测试

```bash
python3 -m pytest tests/ -q
```
