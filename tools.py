"""
自定义工具：论文规范与引用检查
==============================

4 个工具都供 Deep Agents 调用：函数名即工具名，docstring 即工具说明，
模型完全依靠 docstring 判断何时调用，所以描述要写清楚"做什么、什么时候用"。

工具清单：
1. parse_reference        解析参考文献条目 + 统计漏引用
2. check_citation_format  对照 GB/T 7714-2015 检查单条格式
3. search_paper_doi       调 Crossref API 核验文献真实性（断网优雅降级）
4. generate_report        写出《引用校验报告》md + xlsx 到 workspace/

设计原则：
- 全部工具都不依赖大模型，规则可解释，便于答辩时讲解"工具不调用模型会怎样"。
- search_paper_doi 联网失败/超时也只返回提示，绝不抛出未捕获异常让 Agent 崩溃。
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# 本文件所在目录即项目根；workspace/ 是 Agent 唯一可写产出目录
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = BASE_DIR / "workspace"
WORKSPACE.mkdir(exist_ok=True)

# Crossref 推荐在请求头附带邮箱，仅用于匿名统计，可随意填写
CROSSREF_MAILTO = "paper-check-demo@example.edu.cn"

# GB/T 7714-2015 常见文献类型标识
_DOC_TYPES = ["[J]", "[M]", "[C]", "[D]", "[R]", "[N]", "[S]", "[P]", "[EB/OL]", "[DB/OL]", "[Z]"]


# ---------------------------------------------------------------------------
# 工具 1：parse_reference —— 解析条目 + 漏引用统计
# ---------------------------------------------------------------------------
def parse_reference(raw_text: str) -> str:
    """解析论文文稿里的参考文献条目，并统计「漏引用」情况。

    先尝试定位「参考文献 / References」小节；找不到则把全文当作参考文献列表处理。
    同时扫描正文里的 [1]、(作者, 2020) 等引用标记，与参考文献序号比对，找出：
    ① 正文引用了但列表缺失　② 列表有但正文从未引用。

    Args:
        raw_text: 用户粘贴/上传的完整论文文稿（含正文与参考文献）
    """
    text = raw_text or ""

    # 定位「参考文献」小节（兼容 Markdown 标题 ## 参考文献）
    m = re.search(r"(?:^|\n)\s*#{0,6}\s*(参考文献|References|REFERENCES|引用文献)\s*(?:\n|$)", text)
    if m:
        body = text[: m.start()]
        ref_block = text[m.end():]
        body_detected = True
    else:
        # 没找到分节：无法区分正文与参考文献，跳过漏引分析
        body = ""
        ref_block = text
        body_detected = False

    # 解析参考文献条目：按行首 [n] 切分
    entries = []
    for m in re.finditer(r"\[(\d+)\]\s*(.*?)(?=\n\[\d+\]\s*|\Z)", ref_block, re.S):
        idx, content = m.group(1), m.group(2).strip()
        if content:
            entries.append({"index": int(idx), "text": re.sub(r"\s+", " ", content)})
    ref_indices = {e["index"] for e in entries}

    # 扫描正文引用标记 [1]、[1-3]、[2,5]，展开成被引用的序号集合
    cited = set()
    for m in re.finditer(r"\[([0-9,\-\s]+)\]", body):
        for part in m.group(1).split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-")[:2]
                try:
                    cited.update(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    cited.add(int(part))
                except ValueError:
                    pass

    missing_in_list = sorted(cited - ref_indices)   # 正文引了但列表没有
    not_cited = sorted(ref_indices - cited)         # 列表有但正文没引（可能漏引）

    result = {
        "entry_count": len(entries),
        "entries": entries,
        "in_text_citations": sorted(cited),
        "coverage": {
            "body_detected": body_detected,
            "cited_in_text": sorted(cited),
            "not_cited_in_text": not_cited,
            "cited_but_missing_from_list": missing_in_list,
        },
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 工具 2：check_citation_format —— GB/T 7714-2015 确定性校验
# ---------------------------------------------------------------------------
def check_citation_format(reference: str) -> str:
    """对照 GB/T 7714-2015 检查单条参考文献的格式错误。

    检查项（确定性规则，可解释，不调模型）：
    - 是否以 [n] 序号开头
    - 是否包含文献类型标识（[J]/[M]/[C] 等）
    - 是否包含 4 位出版年份
    - 作者超过 3 人是否使用「等」或「et al.」
    - 是否混用中文全角逗号
    - 2015 年后的文献是否补充了 DOI
    - 期刊文献是否含「年, 卷(期): 页码」结构

    Args:
        reference: 一条参考文献原文，例如 "[1] 作者. 题名[J]. 刊名, 2020, 43(5): 1-15."
    """
    ref = (reference or "").strip()
    errors, warnings = [], []

    if not re.match(r"^\[\d+\]", ref):
        errors.append("缺少规范的序号标记，应以 [n] 开头（如 [1]）")

    if not any(dt in ref for dt in _DOC_TYPES):
        errors.append("缺少文献类型标识（期刊用 [J]、专著用 [M]、会议用 [C]）")

    if not re.search(r"(19|20)\d{2}", ref):
        errors.append("缺少出版年份（应为 4 位数字，如 2020）")

    # 作者超过 3 人应使用「等」/「et al.」
    comma_cn = ref.count("，")
    comma_en = ref.count(",")
    if (comma_cn >= 3 or comma_en >= 2) and ("等" not in ref and "et al" not in ref.lower()):
        warnings.append("作者数量较多，超过 3 人时建议用「等」(中文) 或「et al.」(英文) 省略")

    if "，" in ref:
        warnings.append("出现中文全角逗号，GB/T 7714 建议使用半角逗号分隔作者与字段")

    # 2015 年后建议补充 DOI
    ym = re.search(r"(19|20)(\d{2})", ref)
    has_doi = bool(re.search(r"10\.\d{4,9}/", ref)) or "doi" in ref.lower()
    if ym and int(ym.group(0)) >= 2015 and not has_doi:
        warnings.append("2015 年后的文献建议补充 DOI，便于检索与核验")

    if "[J]" in ref and not re.search(r"\d+\s*\(\d+\)\s*[:：]\s*\d+", ref):
        warnings.append("期刊文献建议包含「年, 卷(期): 页码」结构")

    return json.dumps({
        "reference": ref,
        "ok": len(errors) == 0,
        "errors": [{"rule": "GB/T 7714-2015", "message": e, "severity": "error"} for e in errors],
        "warnings": [{"rule": "GB/T 7714-2015", "message": w, "severity": "warning"} for w in warnings],
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 工具 3：search_paper_doi —— Crossref 核验文献真实性
# ---------------------------------------------------------------------------
def search_paper_doi(query: str) -> str:
    """通过 Crossref API 核验一篇文献是否真实存在（作者/题名/DOI 均可）。

    输入看起来像 DOI（含 10.xxxx/）则按 DOI 直接查询，否则按题名检索。
    联网失败、超时或查不到都优雅返回「无法核验」，绝不让 Agent 崩溃。

    Args:
        query: 文献标题或 DOI，例如 "Attention Is All You Need" 或 "10.48550/arXiv.1706.03762"
    """
    q = (query or "").strip()
    if not q:
        return json.dumps({"found": False, "reason": "查询内容为空"}, ensure_ascii=False)

    is_doi = bool(re.search(r"10\.\d{4,9}/", q))
    if is_doi:
        m = re.search(r"10\.\d{4,9}/[^\s,]+", q)
        url = f"https://api.crossref.org/works/{m.group(0)}" if m else None
    else:
        url = "https://api.crossref.org/works?query=" + urllib.parse.quote(q) + "&rows=1"

    if not url:
        return json.dumps({"found": False, "reason": "无法解析查询"}, ensure_ascii=False)

    req = urllib.request.Request(
        url, headers={"User-Agent": f"paper-check/1.0 (mailto:{CROSSREF_MAILTO})"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({
            "found": False,
            "reason": f"联网核验失败：{type(exc).__name__}",
            "note": "当前网络不可用或 Crossref 无响应，请稍后重试或手动确认文献真实性。",
        }, ensure_ascii=False)

    items = data.get("message", {}).get("items", [])
    if not items:
        return json.dumps({
            "found": False,
            "reason": "Crossref 未收录该文献（题名可能有误，或为预印本/中文文献）",
            "note": "未找到不等于一定虚假，请结合其他渠道确认。",
        }, ensure_ascii=False)

    it = items[0]
    title = (it.get("title") or [""])[0]

    # 轻量相关性校验：查询含英文/数字词时，要求返回题名至少命中其一，避免模糊匹配到无关文献
    alnum = re.findall(r"[a-z0-9]{3,}", q.lower())
    if alnum and not any(w in (title or "").lower() for w in alnum):
        return json.dumps({
            "found": False,
            "reason": "Crossref 返回的条目与查询差异较大，可能并非同一篇文献",
            "returned_title": title,
            "note": "请人工确认题名/作者是否准确。",
        }, ensure_ascii=False)

    authors = [
        f"{(a.get('given', '') + ' ' + a.get('family', '')).strip()}"
        for a in it.get("author", [])[:5]
    ]
    year = ""
    for key in ("published", "published-print", "issued", "created"):
        val = it.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            dp = val[0].get("date-parts")
            if dp and isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0] and dp[0][0]:
                year = str(dp[0][0])
                break
    if not year:  # 兜底：从记录中抓取第一个 4 位年份
        ym = re.search(r"(19|20)\d{2}", json.dumps(it, ensure_ascii=False))
        if ym:
            year = ym.group(0)
    return json.dumps({
        "found": True,
        "title": title,
        "authors": authors,
        "year": year,
        "doi": it.get("DOI", ""),
        "publisher": it.get("publisher", ""),
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 工具 4：generate_report —— 写出校验报告（明确产出物）
# ---------------------------------------------------------------------------
def generate_report(results: str, fmt: str = "markdown") -> str:
    """把前面的解析、格式检查、DOI 核验结果整理成《引用校验报告》写入 workspace/。

    始终生成 Markdown 报告；当 fmt 含 "excel" 且环境装有 openpyxl 时，
    额外生成一份 Excel 错误汇总表。返回生成文件的路径。

    Args:
        results: 收集自上述工具的结构化/文本结果（由 Agent 汇总后传入）
        fmt: 输出格式，默认 "markdown"；写 "excel" 或 "markdown,excel" 可同时导出表格
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = (results or "").strip() or "（未收到检查结果）"

    md = f"""# 引用校验报告

> 生成时间：{ts}　|　格式依据：GB/T 7714-2015　|　核验渠道：Crossref API
> 说明：本报告由「论文规范与引用检查助手」自动生成，仅供修改参考，最终以学校要求为准。

## 一、检查结论摘要
- 参考文献条目数、格式错误、漏引用、文献真实性核验结果见下方明细。
- 标注「待核实」的项目需你结合学校规定与原文再次确认。

## 二、详细结果

{body}

## 三、修改建议
1. 优先处理带「错误」级别的项（缺序号、缺文献类型码、缺年份）。
2. 对「警告」级别项按 GB/T 7714-2015 调整标点、补充 DOI、规范多作者写法。
3. 对核验「未找到」的文献，确认题名/作者是否准确，避免引用虚假或错误文献。
4. 处理「漏引用」：列表有但正文未引的，确认是否真的需要；正文引了但列表缺失的，补录文献。

---
*本工具仅做格式与真实性检查，不代写、不生成论文正文。*
"""
    WORKSPACE.mkdir(exist_ok=True)
    md_path = WORKSPACE / "引用校验报告.md"
    md_path.write_text(md, encoding="utf-8")

    paths = [str(md_path)]
    if "excel" in fmt.lower():
        try:
            paths.append(_write_excel(body, ts))
        except Exception as exc:  # noqa: BLE001
            md += f"\n\n> Excel 生成失败：{exc}（已生成 Markdown 报告）"

    return json.dumps({
        "ok": True,
        "saved_files": paths,
        "message": "报告已生成，可在侧边栏 workspace/ 查看与下载。",
    }, ensure_ascii=False, indent=2)


def _write_excel(body: str, ts: str) -> str:
    """把检查结果写成 Excel：一个"完整报告"工作表 + 一个"错误汇总"工作表。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "完整报告"
    ws1.append(["引用校验报告（" + ts + "）"])
    for line in body.splitlines():
        ws1.append([line])

    ws2 = wb.create_sheet("错误汇总")
    ws2.append(["序号", "问题描述"])
    keywords = ["错误", "缺失", "缺少", "未引", "未找到", "无法", "建议", "warning", "需", "待核实"]
    n = 0
    for line in body.splitlines():
        if any(k in line for k in keywords):
            n += 1
            ws2.append([n, line.strip()])
    if n == 0:
        ws2.append([1, "未发现明显格式/真实性问题"])

    xlsx_path = WORKSPACE / "引用校验报告.xlsx"
    wb.save(xlsx_path)
    return str(xlsx_path)


# 在这里登记要交给 Agent 的自定义工具
CUSTOM_TOOLS = [parse_reference, check_citation_format, search_paper_doi, generate_report]
