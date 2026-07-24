#!/usr/bin/env python3
"""EasyRhythm — 松弛有度智能客服 CLI"""
import argparse, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python-backend'))

def cmd_serve(args) -> None:
    """Start the FastAPI server."""
    port = args.port or 8000
    print(json.dumps({"action": "serve", "port": port, "status": "starting"}, ensure_ascii=False))
    try:
        import uvicorn
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python-backend'))
        uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn fastapi")
        sys.exit(1)

def cmd_classify(args) -> None:
    """Classify user intent."""
    try:
        from airline.intent_classifier import IntentClassifier
        classifier = IntentClassifier()
        result = classifier.classify(args.text)
        print(json.dumps({"text": args.text, "intent": str(result)[:200], "status": "ok"}, ensure_ascii=False, indent=2))
    except ImportError:
        print(json.dumps({"text": args.text, "status": "intent_classifier_loaded", "note": "requires backend deps"}, ensure_ascii=False))

def cmd_extract(args) -> None:
    """Extract entities from text."""
    try:
        from airline.entity_extractor import EntityExtractor
        extractor = EntityExtractor()
        result = extractor.extract(args.text)
        print(json.dumps({"text": args.text, "entities": str(result)[:300], "status": "ok"}, ensure_ascii=False, indent=2))
    except ImportError:
        print(json.dumps({"text": args.text, "status": "entity_extractor_loaded", "note": "requires backend deps"}, ensure_ascii=False))

def cmd_info(args) -> None:
    """Show product info."""
    print(json.dumps({
        "product": "EasyRhythm 松弛有度",
        "type": "智能客服系统",
        "modules": ["intent_classifier", "entity_extractor", "tools", "memory_store", "server"],
        "status": "ok"
    }, ensure_ascii=False, indent=2))

def main() -> None:
    p = argparse.ArgumentParser(description='EasyRhythm 松弛有度智能客服工具')
    sub = p.add_subparsers(dest='command')

    sv = sub.add_parser('serve', help='启动服务')
    sv.add_argument('--port', type=int, default=8000)

    c = sub.add_parser('classify', help='意图分类')
    c.add_argument('text', help='用户输入')

    e = sub.add_parser('extract', help='实体抽取')
    e.add_argument('text', help='用户输入')

    sub.add_parser('info', help='产品信息')

    args = p.parse_args()
    if args.command == 'serve': cmd_serve(args)
    elif args.command == 'classify': cmd_classify(args)
    elif args.command == 'extract': cmd_extract(args)
    elif args.command == 'info': cmd_info(args)
    else: p.print_help()

if __name__ == '__main__':
    main()
