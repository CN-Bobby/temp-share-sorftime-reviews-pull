# 执行流程 · Sorftime 评论拉取→翻译→交付

> 按顺序执行。每阶段有明确产物。规模大时用 TaskCreate 跟踪。

## Phase 0 · 输入确认（< 1 min）

| 字段 | 必填 | 示例 | 说明 |
|------|------|------|------|
| 站点 amz_site | ✅ | `US` / `DE` / `UK` / `CA` / `JP` | 与 Sorftime MCP 参数一致 |
| 模式 | ✅ | A / B / C | 见 SKILL.md 三种模式 |
| node_id | A/C 必填 | `17269957011` | 品类节点，需能映射品类名 |
| ASIN 列表 | B/C 必填 | `B0D5TQJXRN,B0FPF67JWL` | 逗号分隔 |
| 榜单规模 | A 必填 | `top50` / `top100` | 决定 category_report 后取多少 |

确认后向用户复述一次：站点 + 模式 + 规模/ASIN 数，避免拉错。

## Phase 1 · 获取 ASIN 清单

### 模式 A/C（品类榜单）
- 调用 Sorftime MCP：`category_report`，参数 `{"node_id": NODE_ID, "amz_site": SITE}`
- 从返回 `data.top100_products`（或 `result.content[].text` 内嵌 JSON 的 `top100_products`）取 ASIN + 标题
- 按规模截取：top50 → 前 50 个；top100 → 全部
- 落盘 `top100_asins.json`：`[{"asin": "...", "title": "..."}]`

### 模式 B（指定 ASIN）
- 直接用用户给的 ASIN 列表，跳过 category_report
- 无标题时后续用空标题，来源标记仍完整

## Phase 2 · 批量拉取评论（核心）

### 路由决策
- ASIN 数 ≤ 10 → 直接用 MCP 工具逐个调 `product_reviews`
- ASIN 数 > 10 → 用 `scripts/pull_reviews.py`（HTTP 直连，见 api-map.md）

### 每个 ASIN 的拉取协议
```
对每个 asin:
  for pass in [1, 2]:            # 拉 2 次，内容一致则去重合并
    调 product_reviews {asin, review_type: "Both", amz_site: SITE}
    每条评论:
      去重键 = (asin, review_date, title, content)
      若新: 追加 {source_site, source_node, asin, product_title,
                  variant_attribute, review_date, star_rating,
                  sentiment, title, content, pull_pass}
```
- **sentiment 判定**：`star >= 4 → Positive`；`star <= 2 → Negative`；`== 3 → Mixed`
- 每次调用后打印 `[i/N] asin=... pass=.. returned=.. new=.. (total_unique=..)`
- 增量落盘：每个 ASIN 完成后写一次 `reviews_raw.json`（进程中断不丢数据）

### 节流（防 429）
```python
if total_calls % 5 == 0: time.sleep(1.2)
else: time.sleep(0.35)
```

### 结束条件
- 所有 ASIN × 2 pass 完成 → 落盘汇总
- 打印：`DONE. total_unique_reviews=.. total_api_calls=..` + sentiment 分布

## Phase 3 · 翻译（固定全量）

### 3.1 切分翻译目标
- **P0 = Negative + Mixed**（痛点/中性，信息量最高）—— 全量优先
- **P1 = Positive** —— 全量，但按 chunk 分批（每 500 条左右）

### 3.2 翻译执行
1. 导出待翻译清单：`[{"idx": i, "asin", "star", "date", "title", "content"}]`
   - P0 清单 = neg(0..N-1) + mix(0..M-1)，索引 `0..N+M-1`（**Negative 全部在前，Mixed 在后**）
   - P1 清单 = pos(0..K-1)，索引独立从 0 开始
2. **LLM 语境化翻译**：结合品类语境（如美甲水钻→注意"胶水/混色/镀层"等术语），逐条翻译标题+正文为中文
3. 分批写 JSON：`_tr_part{1,2,3}.json`（P0），`_tr_p1_chunk{a,b,c}.json`（P1）
   - 每批 ≤ ~170 条，避免单文件过大
4. **JSON 陷阱**：译文里出现英文双引号会破坏 JSON——写成中文引号「」或转义 `\"`

### 3.3 合并（关键！）
```python
# P0 键: Negative → str(neg组内idx)；Mixed → str(181 + mix组内idx)
# P1 键: Positive → str(pos组内idx)
# 对 reviews_raw.json 每条评论:
#   sentiment==Positive → p1tr[str(pos.index(r))]
#   else → p0tr[str(neg.index(r))] 或 p0tr[str(181+mix.index(r))]
```
- 合并后**必须抽查**：取 3 条 Negative 评论，确认 t_title 与英文 title 语义对应
- 输出 `_reviews_merged.json`（每条含 t_title/t_content）

## Phase 4 · Excel 交付

用 `scripts/build_excel.py`（系统 Python 3.12，openpyxl）：

| Sheet | 内容 |
|-------|------|
| 全部评论 | 14 列：`# 来源站点 品类节点 ASIN 商品标题 变体 评论日期 星级 情感 评论标题(EN) 评论内容(EN) 评论标题(中文) 评论内容(中文) 拉取批次`；情感着色（绿=积极/红=消极/黄=中性）；冻结首行 + 筛选 |
| 商品评论统计 | 按 ASIN 聚合：评论数 / 积极 / 中性 / 消极 / 好评率 |
| 统计汇总 | 总数 / ASIN 数 / API 次数 / 情感占比 / 翻译覆盖 / 五星一星占比 |

文件名：`{站点}_YYMMDD_{品类英文}_评论全量_中英对照.xlsx`（如 `US_260821_Nail_Art_Rhinestones_评论全量_中英对照.xlsx`）

## Phase 5 · 验证与交付

1. 重开 Excel 验证：行数 = 去重评论数；中文列无空；抽查 3 条消极翻译对应
2. `present_files` 交付 xlsx
3. 保留原始数据：`reviews_raw.json` / `top100_asins.json` / `_reviews_merged.json`
4. 汇报：评论总数 / 情感分布 / 涉及 ASIN 数 / 高频痛点摘要

## 规模与成本提示

| 场景 | 调用次数 | 耗时 | 翻译量 |
|------|---------|------|--------|
| top50 × 2 | 100 | ~2 min | 千余条 |
| top100 × 2 | 200 | ~3-4 min | 2000-3000 条 |
| 指定 10 ASIN × 2 | 20 | 走工具逐个 | 数百条 |

> 翻译是大头：2831 条约 40 万 token，必须分批。P0（消极+中性）优先保证质量，P1 分批推进，全部完成才交付。
