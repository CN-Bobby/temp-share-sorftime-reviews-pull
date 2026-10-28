# CHANGELOG · sorftime-reviews-pull

## v1.0.0 (2026-08-21)
- **初始版本**：沉淀自 2026-08-21 Nail Art Rhinestones (US, 17269957011) Top100 评论全量拉取+翻译实战（2831 条 / 200 次调用 / 91 ASIN）
- 三种输入模式：A 品类榜单 top50/top100、B 指定 ASIN 列表、C 混合
- 固定 `review_type=Both`（积极+消极全拉）
- 固定全量语境化中文翻译（P0 消极+中性优先，P1 积极分批，复合键合并防错位）
- 固定 Sorftime MCP（少量走工具，批量走 HTTP 直连）
- 脚本模板：`pull_reviews.py`（含重试/节流/增量落盘）、`build_excel.py`（3 Sheet 交付）
- 沉淀关键坑：post 元组解包、SSE 多 data 块解析、P0/P1 索引冲突、托管/系统 Python 分工

## RED 基线记录（v1.0.0 的失败清单）
本次实战中无 SKILL 情况下踩过的坑（已写入 SKILL 防复发）：
1. `category_report` 返回 None → `post()` 返回 `(result, sid)` 元组未解包
2. 429 限流 → 无节流连续 200 次调用
3. SSE 响应多个 `data:` 事件只取最后一个 → 结构错乱
4. P0/P1 翻译索引各自从 0 开始 → 直接合并互相覆盖、消极评论翻译错位
5. 托管 Python 无 openpyxl → 需切系统 Python 3.12
6. 2831 条全量翻译单次放不下 → 按 chunk 分批写文件再合并
