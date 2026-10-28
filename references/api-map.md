# Sorftime MCP 工具映射 + HTTP 直连协议

## 一、MCP 工具（少量 ASIN 时用）

| 工具 | 用途 | 关键参数 | 返回结构要点 |
|------|------|---------|-------------|
| `category_report` | 品类 Top100 商品列表 | `node_id`（下划线）、`amz_site` | `data.top100_products` 或 `result.content[].text` 内嵌 JSON |
| `product_reviews` | 单商品评论（≤100 条/次） | `asin`、`review_type`、`amz_site` | 评论数组：`variant_attribute / review_date(yyyyMMdd) / star_rating / title / content` |

**⚠️ 参数命名坑（跨工具不一致）**
- `category_report` / `category_tree`：参数名是 **`node_id`**（全小写下划线）
- `category_trend`：参数名是 **`nodeId`**（驼峰）
- 口诀：**report/tree = node_id，trend = nodeId**

**review_type 取值**：`Positive` / `Negative` / `Both`。本 SKILL 固定用 `Both`。

**无独立评论 ID**：去重靠 `(asin, review_date, title, content)` 复合键。

## 二、HTTP 直连（批量 >10 ASIN 时）

端点（从 MCP 配置读取，示例）：
```
https://mcp.sorftime.com?key=<YOUR_KEY>
```

### 协议要点
1. **握手**：`initialize`（protocolVersion `2024-11-05`）→ 记录响应头 `Mcp-Session-Id`（可能为 None，不影响）
2. **通知**：`notifications/initialized`
3. **调用**：`tools/call`，参数 `{name, arguments}`
4. **响应解析**：SSE 流式，`event: message` + `data: {...}`；**逐行遍历所有 `data:` 块，保留最后一个合法 JSON**
5. **⚠️ 最大坑**：`post()` 返回 `(result, session_id)` 元组 —— 必须 `rep, _ = post(...)` 解包，否则 `extract_data(rep)` 拿到元组返回 None

### extract_data 逻辑
```python
def extract_data(rep):
    if not isinstance(rep, dict): return None
    res = rep.get('result', {})
    if not isinstance(res, dict): return None
    if 'data' in res and 'content' not in res:
        return res['data']                      # 直接 data 字段
    content = res.get('content')
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get('type') == 'text':
                try: obj = json.loads(part['text'])
                except Exception: return part['text']
                if isinstance(obj, dict) and 'data' in obj: return obj['data']
                return obj
    return None
```

### 重试与容错
- 单次请求 3 次重试（间隔 1.5s），超时 90s
- `category_report` 拉取失败 5 次后落盘原始报文 `category_raw_dump.json` 供排查，再退出
- 单 ASIN 拉取失败打 `WARN` 继续（不中断全量）

### 节流
```python
if total_calls % 5 == 0: time.sleep(1.2)
else: time.sleep(0.35)
```

## 三、运行环境

- **批量脚本**：托管 Python `C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`（无 openpyxl 无妨，脚本只做 HTTP + JSON）
- **Excel 构建**：系统 Python 3.12 `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`（自带 openpyxl 3.1.5 / pandas 3.0.3）
- **编码**：脚本内 `open(..., encoding='utf-8')`，必要时 `sys.stdout.reconfigure(encoding='utf-8')` 防 GBK 崩溃
