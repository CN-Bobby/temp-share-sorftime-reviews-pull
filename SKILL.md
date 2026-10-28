---
name: sorftime-reviews-pull
description: Use when pulling Amazon product reviews (positive + negative) via Sorftime MCP for a marketplace category top50/top100 list or a specific set of ASINs, then translating all reviews into Chinese and delivering a bilingual Excel. Triggers: "拉评论" / "拉取评论" / "top100 评论" / "top50 评论" / "评论翻译" / "reviews pull" / "pull reviews" with a node_id or ASIN list on any Amazon site (US/DE/UK/CA/JP...).
version: 1.0.0
updated: 2026-08-21
license: 内部使用
---

# 📥 Sorftime 评论拉取·翻译·交付

> 用 **Sorftime MCP** 批量拉取亚马逊商品评论（积极+消极），**全部**做语境化中文翻译，产出中英对照 Excel。

## 参考文件

| 文件 | 内容 | 查阅时机 |
|------|------|----------|
| `references/workflow.md` | 三种输入模式的完整执行流程（node 榜单 / ASIN 列表 / 翻译与合并） | 每次执行前 |
| `references/api-map.md` | Sorftime MCP 工具参数映射 + HTTP 直连协议（批量场景） | 批量拉取时 |
| `scripts/pull_reviews.py` | 全量拉取脚本模板（含重试/节流/增量落盘） | 批量拉取时 |
| `scripts/build_excel.py` | Excel 交付构建脚本模板（含翻译合并、3 Sheet 结构） | 交付前 |
| `CHANGELOG.md` | 版本更新日志 | 查看历史变更 |
| `VERSION` | 当前版本号唯一来源 | 自动化脚本读取 |

## 核心铁律（不可协商）

1. **工具固定**：评论数据只走 **Sorftime MCP**（`product_reviews` / `category_report`）。禁止用其他来源拼数据。
2. **情感固定**：每次拉取 `review_type = "Both"`（积极+消极都要），不单独拉单向。
3. **翻译固定**：**全部**去重评论都必须有语境化中文翻译（标题+正文）。不翻译 = 任务未完成。
4. **索引陷阱**：P0（消极+中性）与 P1（积极）翻译文件索引各自从 0 开始，合并时必须用 **(情感, 组内idx)** 复合键，否则错位。
5. **量级路由**：≤ ~10 个 ASIN 走 MCP 工具逐个调；>10 个 ASIN 改用 HTTP 直连脚本（同 key 同协议），避免工具往返 200 次。

## 三种输入模式（开工前先确认属于哪种）

| 模式 | 输入 | 流程起点 | 输出 |
|------|------|---------|------|
| A. 品类榜单 | `node_id` + 站点 + top50/top100 | `category_report` 拿 Top N 商品 ASIN → 逐 ASIN 拉评论 | 榜单商品评论全集 |
| B. 指定 ASIN | 站点 + ASIN 列表（任意数量） | 直接逐 ASIN 拉评论 | 指定商品评论全集 |
| C. 混合（进阶） | node_id + 指定 ASIN 子集 | 榜单定位 → 只拉指定 ASIN | 子集评论 |

> 输入必须含：**站点**（amz_site，如 `US`/`DE`/`UK`）、**node_id 或 ASIN 列表**。缺站点先问，不猜。

## 快速自检卡（交付前逐项过）

- [ ] 评论数据全部来自 Sorftime MCP
- [ ] `review_type=Both`，积极与消极都在
- [ ] 去重键 = `(asin, review_date, title, content)`，无重复行
- [ ] 每条含来源标记：站点 / node / ASIN / 商品标题 / 变体 / 日期 / 星级 / 情感 / 拉取批次
- [ ] **全部**评论有中文翻译（t_title + t_content 无空值）
- [ ] 翻译合并用 (情感, 组内idx) 复合键，抽查 3 条消极评论验证未错位
- [ ] Excel 含「全部评论 / 商品评论统计 / 统计汇总」3 个 Sheet，情感着色 + 筛选
- [ ] 交付时附原始 JSON（`reviews_raw.json`）便于复用

## 常见错误与修复

| 症状 | 根因 | 修复 |
|------|------|------|
| `category_report` 返回 None | `post()` 返回 `(result, sid)` 元组未解包 | `rep, _ = post(...)` |
| 评论拉取 429 限流 | 无节流连续调用 | 每 5 次 `sleep(1.2)`，其余 `sleep(0.35)` |
| SSE 报文解析失败 | 多个 `data:` 事件只取了最后一个 | 逐行遍历，保留最后有效 JSON 块 |
| 翻译错位（消极评论标题对不上） | P0/P1 索引各自从 0 起，直接合并互相覆盖 | 用 (sentiment, 组内idx) 复合键映射 |
| openpyxl 找不到 | 托管 Python 无该包 | 用系统 Python 3.12（自带 openpyxl 3.1.5 / pandas） |
| 翻译量过大（数千条） | 单次输出放不下 | 按 chunk 分文件写，最后合并；先 P0 全量再 P1 |

## 成本与规模预估

- 每个 ASIN 2 次调用（pass1/pass2，pass2 用于捕获更多评论，内容一致则去重）
- top100 × 2 = 200 次调用 ≈ 3-4 分钟（直连脚本 + 节流）
- 评论数参考：美甲水钻类目 91 ASIN → 2831 条去重评论；单商品上限 100 条/次
- 翻译 token：约 180 字/条原文 → 100-150 中文字；2831 条约 40 万 token（分批）
