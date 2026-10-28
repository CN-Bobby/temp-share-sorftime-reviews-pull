# -*- coding: utf-8 -*-
"""
Excel 交付构建脚本模板（含翻译合并）
用法: python build_excel.py <reviews_raw.json> [--translations-dir DIR] [--out OUT.xlsx]

输入:
  - reviews_raw.json: 拉取脚本产物（每条含 sentiment/asin/title/content...）
  - 翻译文件目录（默认当前目录）:
      _tr_part*.json        P0 消极+中性翻译，键 = 组内 idx（neg 0..N-1, mix N..N+M-1）
      _tr_p1_chunk*.json    P1 积极翻译，键 = pos 组内 idx（0..K-1）
输出:
  - {站点}_{YYMMDD}_{品类}_评论全量_中英对照.xlsx（3 Sheet）
"""
import json, glob, sys, os
from collections import Counter, defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def load_translations(dir_path):
    """返回 (p0tr, p1tr)。⚠️ 索引各自从 0 开始，合并时必须用 (sentiment, 组内idx)"""
    p0tr, p1tr = {}, {}
    for p in sorted(glob.glob(os.path.join(dir_path, '_tr_part*.json'))):
        p0tr.update(json.load(open(p, encoding='utf-8')))
    for p in sorted(glob.glob(os.path.join(dir_path, '_tr_p1_chunk*.json'))):
        p1tr.update(json.load(open(p, encoding='utf-8')))
    return p0tr, p1tr

def merge_translations(revs, p0tr, p1tr):
    """关键：用 (情感, 组内idx) 复合键，避免 P0/P1 索引互相覆盖"""
    neg_list = [r for r in revs if r['sentiment'] == 'Negative']
    mix_list = [r for r in revs if r['sentiment'] == 'Mixed']
    pos_list = [r for r in revs if r['sentiment'] == 'Positive']

    def nm_key(r):
        if r['sentiment'] == 'Negative':
            return str(neg_list.index(r))          # 0..N-1
        return str(len(neg_list) + mix_list.index(r))  # N..N+M-1

    out, miss = [], 0
    for r in revs:
        row = dict(r)
        if r['sentiment'] == 'Positive':
            tr = p1tr.get(str(pos_list.index(r)), {})
        else:
            tr = p0tr.get(nm_key(r), {})
        row['t_title'] = tr.get('t_title', '')
        row['t_content'] = tr.get('t_content', '')
        if not tr:
            miss += 1
        out.append(row)
    return out, miss

def build_excel(revs, out_path, node_label="", site="", api_calls=0):
    wb = Workbook()
    ws = wb.active
    ws.title = "全部评论"
    headers = ["#", "来源站点", "品类节点", "ASIN", "商品标题", "变体", "评论日期", "星级", "情感",
               "评论标题(EN)", "评论内容(EN)", "评论标题(中文)", "评论内容(中文)", "拉取批次"]
    ws.append(headers)

    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c in range(1, len(headers)+1):
        cell = ws.cell(row=1, column=c)
        cell.fill = head_fill; cell.font = head_font
        cell.alignment = Alignment(horizontal="center", vertical="center"); cell.border = border

    sent_fill = {"Positive": PatternFill("solid", fgColor="C6EFCE"),
                 "Negative": PatternFill("solid", fgColor="FFC7CE"),
                 "Mixed":    PatternFill("solid", fgColor="FFEB9C")}
    sent_font = {"Positive": Font(color="006100", bold=True),
                 "Negative": Font(color="9C0006", bold=True),
                 "Mixed":    Font(color="9C6500", bold=True)}

    for i, r in enumerate(revs, start=1):
        date = r.get('review_date') or ''
        if len(date) == 8:
            date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        ws.append([i, r.get('source_site', site), r.get('source_node', node_label),
                   r.get('asin',''), r.get('product_title',''), r.get('variant_attribute',''),
                   date, r.get('star_rating',''), r.get('sentiment',''),
                   r.get('title',''), r.get('content',''),
                   r.get('t_title',''), r.get('t_content',''),
                   f"pass{r.get('pull_pass',1)}"])
        rr = ws.max_row
        for c in range(1, len(headers)+1):
            cell = ws.cell(row=rr, column=c)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=(c in (5, 10, 11, 12, 13)))
        sc = ws.cell(row=rr, column=9)
        s = r.get('sentiment')
        if s in sent_fill:
            sc.fill = sent_fill[s]; sc.font = sent_font[s]
            sc.alignment = Alignment(horizontal="center", vertical="center")

    for i, w in enumerate([6, 12, 40, 13, 50, 18, 12, 7, 10, 28, 60, 28, 60, 8], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:N{ws.max_row}"

    # Sheet2: 商品评论统计
    ws2 = wb.create_sheet("商品评论统计")
    h2 = ["ASIN", "商品标题", "评论数", "积极", "中性", "消极", "好评率"]
    ws2.append(h2)
    for c in range(1, len(h2)+1):
        cell = ws2.cell(row=1, column=c)
        cell.fill = head_fill; cell.font = head_font
        cell.alignment = Alignment(horizontal="center"); cell.border = border
    asin_map = defaultdict(list)
    for r in revs:
        asin_map[r['asin']].append(r)
    for idx, (asin, lst) in enumerate(sorted(asin_map.items(), key=lambda x: -len(x[1])), start=2):
        cnt = Counter(x['sentiment'] for x in lst)
        pos, mix, neg = cnt.get('Positive',0), cnt.get('Mixed',0), cnt.get('Negative',0)
        rate = pos/len(lst)*100 if lst else 0
        ws2.append([asin, lst[0]['product_title'], len(lst), pos, mix, neg, f"{rate:.1f}%"])
        for c in range(1, len(h2)+1):
            ws2.cell(row=idx, column=c).border = border
    for i, w in enumerate([13, 55, 8, 8, 8, 8, 10], start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"

    # Sheet3: 统计汇总
    ws3 = wb.create_sheet("统计汇总")
    h3 = ["指标", "数值"]
    ws3.append(h3)
    for c in range(1, 3):
        cell = ws3.cell(row=1, column=c); cell.fill = head_fill; cell.font = head_font; cell.border = border
    tot = Counter(x['sentiment'] for x in revs)
    summary = [
        ("品类节点", node_label),
        ("站点", site),
        ("去重后评论总数", len(revs)),
        ("涉及商品数(ASIN)", len(asin_map)),
        ("API 调用次数", api_calls),
        ("拉取批次", "站点 × 2 (内容一致去重合并)"),
        ("积极评论", f"{tot.get('Positive',0)} ({tot.get('Positive',0)/len(revs)*100:.1f}%)"),
        ("中性评论", f"{tot.get('Mixed',0)} ({tot.get('Mixed',0)/len(revs)*100:.1f}%)"),
        ("消极评论", f"{tot.get('Negative',0)} ({tot.get('Negative',0)/len(revs)*100:.1f}%)"),
        ("翻译覆盖", f"{sum(1 for x in revs if x.get('t_title'))}/{len(revs)} 条"),
        ("五星占比", f"{sum(1 for x in revs if x.get('star_rating')==5)/len(revs)*100:.1f}%"),
        ("一星占比", f"{sum(1 for x in revs if x.get('star_rating')==1)/len(revs)*100:.1f}%"),
    ]
    for i, (k, v) in enumerate(summary, start=2):
        ws3.append([k, v])
        ws3.cell(row=i, column=1).font = Font(bold=True)
        ws3.cell(row=i, column=1).border = border
        ws3.cell(row=i, column=2).border = border
    ws3.column_dimensions['A'].width = 22
    ws3.column_dimensions['B'].width = 80

    wb.save(out_path)
    return len(revs)

def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python build_excel.py <reviews_raw.json> [--translations-dir DIR] [--out OUT]")
    raw_path = sys.argv[1]
    tdir = "."
    out_path = None
    if "--translations-dir" in sys.argv:
        tdir = sys.argv[sys.argv.index("--translations-dir")+1]
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out")+1]

    revs = json.load(open(raw_path, encoding='utf-8'))
    p0tr, p1tr = load_translations(tdir)
    merged, miss = merge_translations(revs, p0tr, p1tr)
    print(f"merged {len(merged)} reviews, missing translations: {miss}")
    if miss:
        print("⚠️ 有缺失翻译，检查 _tr_part* / _tr_p1_chunk* 文件")

    node_label = revs[0].get('source_node', '') if revs else ''
    site = revs[0].get('source_site', '') if revs else ''
    if not out_path:
        out_path = f"reviews_全量_中英对照.xlsx"
    n = build_excel(merged, out_path, node_label=node_label, site=site)
    print(f"saved: {out_path} ({n} rows)")

if __name__ == "__main__":
    main()
