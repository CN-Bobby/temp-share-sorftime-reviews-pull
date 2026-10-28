# -*- coding: utf-8 -*-
"""
Sorftime 评论批量拉取脚本模板（模式 A：品类榜单 top100；模式 B：指定 ASIN 列表）
用法：
  模式 A: python pull_reviews.py --node 17269957011 --site US --top 100 --out reviews_raw.json
  模式 B: python pull_reviews.py --asins B0D5TQJXRN,B0FPF67JWL --site US --out reviews_raw.json

产物：
  - <out>            全部去重评论 (reviews_raw.json)
  - top100_asins.json ASIN 清单（模式 A）
  - pull_log.txt      运行日志
"""
import json, urllib.request, time, os, sys, argparse
from collections import Counter
from urllib.parse import urlencode
from urllib.parse import quote

# ============ 配置区：从 MCP 配置读取端点与 key ============
SORFTIME_API_KEY = os.environ.get("SORFTIME_API_KEY")
ENDPOINT = ("https://mcp.sorftime.com?" + urlencode({"key": SORFTIME_API_KEY}) if SORFTIME_API_KEY else None)

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open("pull_log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def post(payload, session_id=None, retries=3):
    if not SORFTIME_API_KEY:
        raise RuntimeError("Set SORFTIME_API_KEY before running this script")
    if not SORFTIME_API_KEY:
        raise RuntimeError("Set SORFTIME_API_KEY before running this script")
    last = None
    for attempt in range(retries):
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(ENDPOINT, data=data, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Accept', 'application/json, text/event-stream')
            if session_id:
                req.add_header('Mcp-Session-Id', session_id)
            resp = urllib.request.urlopen(req, timeout=90)
            ct = resp.headers.get('Content-Type', '')
            raw = resp.read().decode('utf-8', 'replace')
            sid = resp.headers.get('Mcp-Session-Id') or resp.headers.get('mcp-session-id')
            if 'text/event-stream' in ct:
                # SSE：逐行遍历所有 data: 块，保留最后一个合法 JSON
                result = None
                for block in raw.split('\n\n'):
                    for line in block.split('\n'):
                        if line.startswith('data:'):
                            chunk = line[5:].strip()
                            if chunk:
                                try:
                                    result = json.loads(chunk)
                                except Exception:
                                    pass
                return result, sid
            try:
                return json.loads(raw), sid
            except Exception:
                return {'_raw': raw}, sid
        except Exception as e:
            last = e
            time.sleep(1.5)
    error_type = type(last).__name__ if last else "UnknownError"
    raise RuntimeError(f"post failed after {retries} retries ({error_type})")
    raise RuntimeError(f"post failed after {retries} retries: {detail}")

def extract_data(rep):
    """⚠️ rep 必须是 post() 解包后的 result，不能是 (result, sid) 元组"""
    if not isinstance(rep, dict):
        return None
    res = rep.get('result', {})
    if not isinstance(res, dict):
        return None
    if 'data' in res and 'content' not in res:
        return res['data']
    content = res.get('content')
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                try:
                    obj = json.loads(part['text'])
                except Exception:
                    return part['text']
                if isinstance(obj, dict) and 'data' in obj:
                    return obj['data']
                return obj
    return None

def sentiment_of(star):
    if star is None:
        return "Unknown"
    try:
        s = float(star)
    except Exception:
        return "Unknown"
    if s >= 4: return "Positive"
    if s <= 2: return "Negative"
    return "Mixed"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", help="品类 node_id（模式 A）")
    ap.add_argument("--asins", help="逗号分隔 ASIN 列表（模式 B）")
    ap.add_argument("--site", default="US", help="amz_site")
    ap.add_argument("--top", type=int, default=100, help="top50 或 top100")
    ap.add_argument("--out", default="reviews_raw.json")
    ap.add_argument("--node-name", default="", help="品类名（用于来源标记）")
    args = ap.parse_args()

    if not args.node and not args.asins:
        sys.exit("必须提供 --node 或 --asins")

    # ---- init ----
    rep, sid = post({"jsonrpc":"2.0","id":1,"method":"initialize",
        "params":{"protocolVersion":"2024-11-05","capabilities":{},
                  "clientInfo":{"name":"pull-script","version":"1.0"}}})
    log(f"INIT ok, sid={sid}")
    post({"jsonrpc":"2.0","method":"notifications/initialized","params":{}}, sid)

    # ---- 获取 ASIN 清单 ----
    if args.asins:
        asins = [{"asin": a.strip(), "title": ""} for a in args.asins.split(",") if a.strip()]
        node_label = f"ASIN_LIST({len(asins)})"
        log(f"Got {len(asins)} ASINs from user list")
    else:
        cat = None
        for attempt in range(5):
            try:
                rep, _ = post({"jsonrpc":"2.0","id":2,"method":"tools/call",
                    "params":{"name":"category_report","arguments":{"node_id":args.node,"amz_site":args.site}}}, sid)
                cat = extract_data(rep)
                if isinstance(cat, dict) and 'top100_products' in cat and isinstance(cat['top100_products'], list):
                    break
                else:
                    log(f"  category_report attempt {attempt+1}: unexpected structure, retrying...")
                    cat = None
            except Exception as e:
                log(f"  category_report attempt {attempt+1} ERR: {e}")
            time.sleep(2)
        if not isinstance(cat, dict) or 'top100_products' not in cat:
            try:
                with open("category_raw_dump.json", "w", encoding="utf-8") as f:
                    json.dump(rep, f, ensure_ascii=False, indent=1)
                log("FATAL: cannot get top100_products; dumped raw")
            except Exception:
                log("FATAL: cannot get top100_products and cannot dump raw")
            sys.exit(1)
        products = cat['top100_products'][:args.top]
        asins = [{"asin": p.get('asin'), "title": p.get('title','')} for p in products]
        node_label = f"{args.node} / {args.node_name or ''}"
        with open("top100_asins.json", "w", encoding="utf-8") as f:
            json.dump(asins, f, ensure_ascii=False, indent=1)
        log(f"Got {len(asins)} ASINs from category {args.node} (top{args.top})")

    # ---- 拉取评论 ----
    all_reviews = []
    seen = set()
    total_calls = 0

    for idx, item in enumerate(asins, start=1):
        asin = item['asin']; title = item['title']
        for p in (1, 2):
            try:
                rep, _ = post({"jsonrpc":"2.0","id":100+total_calls,"method":"tools/call",
                    "params":{"name":"product_reviews",
                              "arguments":{"asin":asin,"review_type":"Both","amz_site":args.site}}}, sid)
                total_calls += 1
                data = extract_data(rep)
            except Exception as e:
                log(f"  ERR asin={asin} pass={p}: {e}")
                continue
            if not isinstance(data, list):
                log(f"  WARN asin={asin} pass={p}: data not list ({type(data).__name__})")
                continue
            added = 0
            for r in data:
                key = (asin, r.get('review_date',''), r.get('title',''), r.get('content',''))
                if key in seen:
                    continue
                seen.add(key)
                all_reviews.append({
                    "source_site": f"Amazon {args.site.upper()}",
                    "source_node": node_label,
                    "asin": asin,
                    "product_title": title,
                    "variant_attribute": r.get('variant_attribute',''),
                    "review_date": r.get('review_date',''),
                    "star_rating": r.get('star_rating'),
                    "sentiment": sentiment_of(r.get('star_rating')),
                    "title": r.get('title',''),
                    "content": r.get('content',''),
                    "pull_pass": p,
                })
                added += 1
            log(f"  [{idx}/{len(asins)}] asin={asin} pass={p}: returned={len(data)} new={added} (total_unique={len(all_reviews)})")
            # 节流防 429
            if total_calls % 5 == 0:
                time.sleep(1.2)
            else:
                time.sleep(0.35)
        # 增量落盘
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(all_reviews, f, ensure_ascii=False, indent=1)

    # ---- summary ----
    cnt = Counter(r['sentiment'] for r in all_reviews)
    per_pass = Counter(r['pull_pass'] for r in all_reviews)
    log("=" * 50)
    log(f"DONE. total_unique_reviews={len(all_reviews)} total_api_calls={total_calls}")
    log(f"sentiment: {dict(cnt)}")
    log(f"by_pass: {dict(per_pass)}")
    log(f"raw file: {os.path.abspath(args.out)}")

if __name__ == "__main__":
    main()
