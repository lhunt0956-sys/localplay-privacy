#!/usr/bin/env python3
"""A-share market / policy / industry brief from stock-learning skill."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent


@dataclass
class IndexQuote:
    name: str
    price: float
    change: float
    pct: float
    amount_yi: float | None = None  # 成交额（亿元，接口口径）

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HoldingQuote:
    name: str
    symbol: str
    shares: int
    cost: float
    price: float | None
    market_value: float | None
    pnl: float | None
    pnl_pct: float | None
    weight_hint: str = ""
    note: str = ""
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SectorQuote:
    name: str
    pct: float
    why: str = ""
    main_flow_yi: float | None = None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NewsBite:
    title: str
    link: str
    level: str = "中"  # 高/中/低
    tag: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketBrief:
    indices: list[IndexQuote]
    holdings: list[HoldingQuote]
    sectors: list[SectorQuote]
    policy_news: list[NewsBite]
    industry_news: list[NewsBite]
    market_news: list[NewsBite]
    total_market_value: float | None
    total_pnl: float | None
    total_amount_yi: float | None
    bias: str
    volume_note: str
    sector_note: str
    tip: str
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "indices": [i.to_dict() for i in self.indices],
            "holdings": [h.to_dict() for h in self.holdings],
            "sectors": [s.to_dict() for s in self.sectors],
            "policy_news": [n.to_dict() for n in self.policy_news],
            "industry_news": [n.to_dict() for n in self.industry_news],
            "market_news": [n.to_dict() for n in self.market_news],
            "total_market_value": self.total_market_value,
            "total_pnl": self.total_pnl,
            "total_amount_yi": self.total_amount_yi,
            "bias": self.bias,
            "volume_note": self.volume_note,
            "sector_note": self.sector_note,
            "tip": self.tip,
            "errors": self.errors,
        }


def load_portfolio(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (ROOT / "portfolio.yaml")
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers=headers
        or {
            "User-Agent": "Mozilla/5.0 NewsBot/1.0",
            "Referer": "https://finance.sina.com.cn",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _fetch_sina(codes: list[str]) -> dict[str, list[str]]:
    if not codes:
        return {}
    raw = _http_get(
        "https://hq.sinajs.cn/list=" + ",".join(codes),
        {
            "User-Agent": "Mozilla/5.0 NewsBot/1.0",
            "Referer": "https://finance.sina.com.cn",
        },
    ).decode("gbk", errors="replace")
    out: dict[str, list[str]] = {}
    for line in raw.splitlines():
        m = re.match(r'var hq_str_([^=]+)="(.*)";?', line.strip())
        if not m:
            continue
        code, payload = m.group(1), m.group(2)
        out[code] = payload.split(",") if payload else []
    return out


def _parse_index(name: str, fields: list[str]) -> IndexQuote | None:
    # s_ 简要行情: name, price, change, pct, volume, amount(万元)
    if len(fields) < 4:
        return None
    try:
        amount_yi = None
        if len(fields) >= 6 and fields[5]:
            amount_yi = round(float(fields[5]) / 10000.0, 2)  # 万元 -> 亿元
        return IndexQuote(
            name=name,
            price=float(fields[1]),
            change=float(fields[2]),
            pct=float(fields[3]),
            amount_yi=amount_yi,
        )
    except ValueError:
        return None


def _parse_stock_price(fields: list[str]) -> float | None:
    if len(fields) < 4:
        return None
    try:
        price = float(fields[3])
        return price if price > 0 else None
    except ValueError:
        return None


def _fetch_sina_industries() -> list[tuple[str, float]]:
    raw = _http_get(
        "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php",
        {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
    ).decode("gbk", errors="replace")
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", raw, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    rows: list[tuple[str, float]] = []
    for value in data.values():
        parts = str(value).split(",")
        if len(parts) < 6:
            continue
        try:
            rows.append((parts[1], float(parts[5])))
        except ValueError:
            continue
    return rows


def _fetch_eastmoney_sectors() -> list[tuple[str, float, float | None]]:
    url = (
        "https://push2delay.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=120&po=1&np=1&fltt=2&invt=2&fid=f3"
        "&fs=m:90+t:2&fields=f12,f14,f2,f3,f62"
    )
    raw = _http_get(
        url,
        {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
    ).decode("utf-8", errors="replace")
    data = json.loads(raw)
    diff = (data.get("data") or {}).get("diff") or []
    rows: list[tuple[str, float, float | None]] = []
    for row in diff:
        name = str(row.get("f14") or "")
        try:
            pct = float(row.get("f3"))
        except (TypeError, ValueError):
            continue
        flow = row.get("f62")
        try:
            flow_yi = float(flow) / 1e8 if flow is not None else None
        except (TypeError, ValueError):
            flow_yi = None
        rows.append((name, pct, flow_yi))
    return rows


def _news_is_fresh(item: dict[str, Any], max_age_days: int = 7) -> bool:
    """Prefer URL date / ctime; drop old republished articles."""
    import time
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc)
    link = str(item.get("url") or item.get("URL") or "")
    m = re.search(r"/(20\d{2})-(\d{2})-(\d{2})/", link)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            return (now - dt).days <= max_age_days
        except ValueError:
            pass
    ctime = item.get("ctime") or item.get("intime")
    try:
        ts = int(ctime)
        # sina sometimes returns milliseconds
        if ts > 10_000_000_000:
            ts //= 1000
        age_days = (time.time() - ts) / 86400
        return age_days <= max_age_days
    except (TypeError, ValueError):
        return True


def _fetch_sina_roll(pageid: str, lid: str, num: int = 20) -> list[dict[str, str]]:
    url = (
        "https://feed.mix.sina.com.cn/api/roll/get?"
        + urllib.parse.urlencode({"pageid": pageid, "lid": lid, "num": str(num), "page": "1"})
    )
    raw = _http_get(
        url,
        {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
    ).decode("utf-8", errors="replace")
    data = json.loads(raw)
    items = (data.get("result") or {}).get("data") or []
    out: list[dict[str, str]] = []
    for it in items:
        if not _news_is_fresh(it):
            continue
        title = (it.get("title") or "").strip()
        link = (it.get("url") or it.get("URL") or "").strip()
        if title and link:
            out.append({"title": title, "link": link})
    return out


def _level_for_title(title: str, portfolio: dict[str, Any]) -> str:
    pri = portfolio.get("news_priority_keywords") or {}
    for k in pri.get("critical") or []:
        if str(k) and str(k) in title:
            return "高"
    for k in pri.get("high") or []:
        if str(k) and str(k) in title:
            return "高"
    for k in pri.get("medium") or []:
        if str(k) and str(k) in title:
            return "中"
    return "中"


def _pick_watched_sectors(portfolio: dict[str, Any], errors: list[str]) -> list[SectorQuote]:
    watched = list(portfolio.get("watched_industries") or [])
    found: dict[str, SectorQuote] = {}

    try:
        for name, pct in _fetch_sina_industries():
            for w in watched:
                if any(m in name for m in (w.get("match") or [])):
                    key = w["name"]
                    prev = found.get(key)
                    if prev is None or abs(pct) > abs(prev.pct):
                        found[key] = SectorQuote(
                            name=f"{w['name']} · {name}",
                            pct=pct,
                            why=str(w.get("why") or ""),
                            source="新浪行业",
                        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"新浪行业板块失败: {exc}")

    try:
        for name, pct, flow in _fetch_eastmoney_sectors():
            for w in watched:
                if any(m in name for m in (w.get("match") or [])):
                    key = f"em:{w['name']}:{name}"
                    found[key] = SectorQuote(
                        name=f"{w['name']} · {name}",
                        pct=pct,
                        why=str(w.get("why") or ""),
                        main_flow_yi=round(flow, 2) if flow is not None else None,
                        source="东财行业",
                    )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"东财行业板块失败: {exc}")

    # 每个关注主题最多保留 2 条，避免刷屏
    by_theme: dict[str, list[SectorQuote]] = {}
    for sec in found.values():
        theme = sec.name.split(" · ")[0]
        by_theme.setdefault(theme, []).append(sec)
    selected: list[SectorQuote] = []
    for theme, rows in by_theme.items():
        rows.sort(key=lambda s: abs(s.pct), reverse=True)
        selected.extend(rows[:2])
    selected.sort(key=lambda s: s.pct, reverse=True)
    return selected


def _is_cn_policy(title: str) -> bool:
    strong = (
        "央行", "中国人民银行", "降息", "降准", "LPR", "MLF", "逆回购",
        "证监会", "国资委", "发改委", "工信部", "财政部", "国务院", "政治局",
        "金融监管总局", "银保监", "窗口指导",
    )
    if any(k in title for k in strong):
        return True
    # 弱词需搭配国内资本市场语境，避免把海外“政策”误收
    weak = ("政策", "监管", "货币政策", "流动性", "利率")
    cn_ctx = ("A股", "沪深", "资本市场", "证监会", "央行", "国务院", "中国", "国内")
    return any(k in title for k in weak) and any(k in title for k in cn_ctx)


def _collect_news(portfolio: dict[str, Any], errors: list[str]) -> tuple[list[NewsBite], list[NewsBite], list[NewsBite]]:
    industry_kw = [str(k) for k in (portfolio.get("industry_news_keywords") or []) if k]
    hold_kw = holdings_keywords(portfolio)

    feeds = [
        ("153", "2509"),  # 财经要闻（含证监会等）
        ("153", "2516"),
        ("153", "2517"),
        ("155", "1687"),  # 市场/宏观研究向
        ("155", "1690"),
        ("155", "1688"),
    ]
    seen: set[str] = set()
    pool: list[NewsBite] = []
    for pageid, lid in feeds:
        try:
            for item in _fetch_sina_roll(pageid, lid, num=20):
                title = item["title"]
                if title in seen:
                    continue
                seen.add(title)
                level = _level_for_title(title, portfolio)
                pool.append(NewsBite(title=title, link=item["link"], level=level))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"新闻源 {pageid}/{lid} 失败: {exc}")

    policy: list[NewsBite] = []
    industry: list[NewsBite] = []
    market: list[NewsBite] = []
    for bite in pool:
        title = bite.title
        is_policy = _is_cn_policy(title)
        is_industry = any(k in title for k in industry_kw + hold_kw)
        if is_policy:
            bite.tag = "政策"
            bite.level = "高"
            policy.append(bite)
        elif is_industry:
            bite.tag = "行业"
            industry.append(bite)
        elif any(k in title for k in ("A股", "沪深", "上证", "创业板", "成交", "板块", "股市", "行情", "资金", "操盘", "公告")):
            bite.tag = "股市"
            market.append(bite)

    def _rank(items: list[NewsBite]) -> list[NewsBite]:
        weight = {"高": 2, "中": 1, "低": 0}
        return sorted(items, key=lambda x: weight.get(x.level, 0), reverse=True)

    return _rank(policy)[:6], _rank(industry)[:6], _rank(market)[:5]


_TIPS = [
    "今天涨不代表明天涨，A股短期走势受情绪影响很大",
    "板块轮动是常态，不要追高换仓",
    "成交量放大+上涨，比缩量上涨更有参考价值",
    "一条政策新闻短期可能反应过度，等市场消化1-3天再判断方向",
]


def build_market_brief(portfolio: dict[str, Any] | None = None) -> MarketBrief:
    portfolio = portfolio or load_portfolio()
    errors: list[str] = []
    index_cfgs = list(portfolio.get("indices") or [])
    holding_cfgs = list(portfolio.get("holdings") or [])
    codes = [c["code"] for c in index_cfgs] + [h["code"] for h in holding_cfgs]

    try:
        table = _fetch_sina(codes)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"行情接口失败: {exc}")
        table = {}

    indices: list[IndexQuote] = []
    for cfg in index_cfgs:
        fields = table.get(cfg["code"]) or []
        q = _parse_index(cfg["name"], fields)
        if q:
            indices.append(q)
        else:
            errors.append(f"指数无数据: {cfg['name']}")

    holdings: list[HoldingQuote] = []
    total_mv = 0.0
    total_pnl = 0.0
    any_price = False
    for cfg in holding_cfgs:
        fields = table.get(cfg["code"]) or []
        price = _parse_stock_price(fields)
        shares = int(cfg.get("shares") or 0)
        cost = float(cfg.get("cost") or 0)
        if price is None:
            holdings.append(
                HoldingQuote(
                    name=cfg["name"],
                    symbol=str(cfg.get("symbol") or ""),
                    shares=shares,
                    cost=cost,
                    price=None,
                    market_value=None,
                    pnl=None,
                    pnl_pct=None,
                    note=cfg.get("note") or "暂无实时价",
                    available=False,
                )
            )
            continue
        mv = price * shares
        pnl = (price - cost) * shares
        pnl_pct = ((price / cost) - 1) * 100 if cost else 0.0
        total_mv += mv
        total_pnl += pnl
        any_price = True
        holdings.append(
            HoldingQuote(
                name=cfg["name"],
                symbol=str(cfg.get("symbol") or ""),
                shares=shares,
                cost=cost,
                price=price,
                market_value=round(mv, 2),
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                note=cfg.get("note") or "",
                available=True,
            )
        )

    if any_price and total_mv > 0:
        for h in holdings:
            if h.market_value is not None:
                h.weight_hint = f"{h.market_value / total_mv * 100:.1f}%"

    if indices:
        avg = sum(i.pct for i in indices) / len(indices)
        if avg >= 0.5:
            bias = "偏多"
        elif avg <= -0.5:
            bias = "偏空"
        else:
            bias = "震荡"
    else:
        bias = "数据不足"

    total_amount = None
    amounts = [i.amount_yi for i in indices if i.amount_yi is not None]
    if amounts:
        # 上证+深证更能代表两市量能；若只有部分则求和并标注接口口径
        total_amount = round(sum(amounts[:2]) if len(amounts) >= 2 else sum(amounts), 2)
    if total_amount is None:
        volume_note = "量能：暂无成交额数据"
    elif total_amount >= 12000:
        volume_note = f"量能：两市合计约 {total_amount:.0f} 亿元（接口口径），成交偏活跃"
    elif total_amount >= 8000:
        volume_note = f"量能：两市合计约 {total_amount:.0f} 亿元（接口口径），成交中等"
    else:
        volume_note = f"量能：两市合计约 {total_amount:.0f} 亿元（接口口径），成交偏清淡"

    sectors = _pick_watched_sectors(portfolio, errors)
    if sectors:
        up = [s for s in sectors if s.pct >= 0]
        down = [s for s in sectors if s.pct < 0]
        head = "、".join(s.name.split(" · ")[-1] for s in up[:3]) or "暂无"
        tail = "、".join(s.name.split(" · ")[-1] for s in down[:3]) or "暂无"
        sector_note = f"行业分化：偏强 {head}；偏弱 {tail}"
    else:
        sector_note = "行业分化：关注行业数据暂缺"

    policy_news, industry_news, market_news = _collect_news(portfolio, errors)
    tip = _TIPS[abs(hash(bias + volume_note)) % len(_TIPS)]

    return MarketBrief(
        indices=indices,
        holdings=holdings,
        sectors=sectors,
        policy_news=policy_news,
        industry_news=industry_news,
        market_news=market_news,
        total_market_value=round(total_mv, 2) if any_price else None,
        total_pnl=round(total_pnl, 2) if any_price else None,
        total_amount_yi=total_amount,
        bias=bias,
        volume_note=volume_note,
        sector_note=sector_note,
        tip=tip,
        errors=errors,
    )


def holdings_keywords(portfolio: dict[str, Any] | None = None) -> list[str]:
    portfolio = portfolio or load_portfolio()
    keys: list[str] = []
    for h in portfolio.get("holdings") or []:
        for k in h.get("keywords") or []:
            word = str(k)
            if word and word not in keys:
                keys.append(word)
    for k in portfolio.get("industry_news_keywords") or []:
        word = str(k)
        if word and word not in keys:
            keys.append(word)
    return keys


def news_priority(text: str, portfolio: dict[str, Any] | None = None) -> int:
    portfolio = portfolio or load_portfolio()
    pri = portfolio.get("news_priority_keywords") or {}
    score = 0
    for k in pri.get("critical") or []:
        if str(k) and str(k) in text:
            score += 30
    for k in pri.get("high") or []:
        if str(k) and str(k) in text:
            score += 20
    for k in pri.get("medium") or []:
        if str(k) and str(k) in text:
            score += 10
    for k in holdings_keywords(portfolio):
        if k in text:
            score += 25
    for k in portfolio.get("policy_keywords") or []:
        if str(k) and str(k) in text:
            score += 15
    return score


def _fmt_news_md(title: str, items: list[NewsBite]) -> list[str]:
    if not items:
        return [f"### {title}", "", "- 今日暂无高相关条目（或源站暂不可用）", ""]
    lines = [f"### {title}", ""]
    for n in items:
        lines.append(f"- 【{n.level}】[{n.title}]({n.link})")
    lines.append("")
    return lines


def format_market_markdown(brief: MarketBrief) -> str:
    lines = ["## 📈 A股晨间雷达（stock-learning）", ""]
    lines.append(f"**结论**：今日整体倾向 **{brief.bias}**")
    lines.append(f"**{brief.volume_note}**")
    lines.append(f"**{brief.sector_note}**")
    lines.append("")

    if brief.indices:
        lines.append("### 股市面 · 指数")
        lines.append("")
        for i in brief.indices:
            sign = "+" if i.pct >= 0 else ""
            amt = f" · 成交约 {i.amount_yi:.0f} 亿" if i.amount_yi is not None else ""
            lines.append(
                f"- {i.name}：{i.price:.2f}（{sign}{i.change:.2f} / {sign}{i.pct:.2f}%{amt}）"
            )
        lines.append("")

    if brief.sectors:
        lines.append("### 行业面 · 你关注的板块")
        lines.append("")
        for s in brief.sectors:
            sign = "+" if s.pct >= 0 else ""
            flow = f" · 主力净流入约 {s.main_flow_yi:.2f} 亿" if s.main_flow_yi is not None else ""
            why = f" — {s.why}" if s.why else ""
            lines.append(f"- **{s.name}** {sign}{s.pct:.2f}%{flow}{why}")
        lines.append("")

    if brief.holdings:
        lines.append("### 持仓快照")
        lines.append("")
        for h in brief.holdings:
            if not h.available or h.price is None:
                lines.append(f"- {h.name}（{h.symbol}）：暂无报价" + (f" · {h.note}" if h.note else ""))
                continue
            sign = "+" if (h.pnl or 0) >= 0 else ""
            lines.append(
                f"- **{h.name}**（{h.symbol}）现价 {h.price:.3f} · 成本 {h.cost:.4f} · "
                f"盈亏 {sign}{h.pnl:.2f}元（{sign}{h.pnl_pct:.2f}%） · 仓位约 {h.weight_hint}"
            )
        lines.append("")
        if brief.total_market_value is not None:
            sign = "+" if (brief.total_pnl or 0) >= 0 else ""
            lines.append(
                f"持仓合计市值约 **{brief.total_market_value:.2f} 元**，"
                f"浮动盈亏约 **{sign}{brief.total_pnl:.2f} 元**（相对成本）。"
            )
            lines.append("")

    lines.extend(_fmt_news_md("政策面 · 值得关注", brief.policy_news))
    lines.extend(_fmt_news_md("行业面 · 相关资讯", brief.industry_news))
    lines.extend(_fmt_news_md("股市面 · 市场资讯", brief.market_news))

    lines.append(f"> 新手提醒：{brief.tip}")
    lines.append("")
    return "\n".join(lines)


def format_market_html(brief: MarketBrief) -> str:
    import html as html_mod

    def li_indices() -> str:
        rows = []
        for i in brief.indices:
            sign = "+" if i.pct >= 0 else ""
            color = "#0e7c66" if i.pct >= 0 else "#b42318"
            amt = f" · 约{i.amount_yi:.0f}亿" if i.amount_yi is not None else ""
            rows.append(
                f"<li><strong>{html_mod.escape(i.name)}</strong> {i.price:.2f} "
                f"<span style='color:{color}'>{sign}{i.pct:.2f}%</span>{html_mod.escape(amt)}</li>"
            )
        return "".join(rows)

    def li_sectors() -> str:
        rows = []
        for s in brief.sectors:
            sign = "+" if s.pct >= 0 else ""
            color = "#0e7c66" if s.pct >= 0 else "#b42318"
            flow = f" · 净流入约{s.main_flow_yi:.2f}亿" if s.main_flow_yi is not None else ""
            why = f"<div class='meta'>{html_mod.escape(s.why)}</div>" if s.why else ""
            rows.append(
                "<li>"
                f"<strong>{html_mod.escape(s.name)}</strong> "
                f"<span style='color:{color}'>{sign}{s.pct:.2f}%</span>"
                f"{html_mod.escape(flow)}{why}</li>"
            )
        return "".join(rows) or "<li>暂无关注行业数据</li>"

    def li_holdings() -> str:
        rows = []
        for h in brief.holdings:
            if not h.available or h.price is None:
                rows.append(
                    f"<li>{html_mod.escape(h.name)}（{html_mod.escape(h.symbol)}）：暂无报价</li>"
                )
                continue
            sign = "+" if (h.pnl or 0) >= 0 else ""
            color = "#0e7c66" if (h.pnl or 0) >= 0 else "#b42318"
            rows.append(
                "<li>"
                f"<strong>{html_mod.escape(h.name)}</strong>（{html_mod.escape(h.symbol)}） "
                f"现价 {h.price:.3f} · 盈亏 "
                f"<span style='color:{color}'>{sign}{h.pnl:.2f}（{sign}{h.pnl_pct:.2f}%）</span>"
                f" · 仓位约 {html_mod.escape(h.weight_hint)}</li>"
            )
        return "".join(rows)

    def li_news(items: list[NewsBite]) -> str:
        if not items:
            return "<li>今日暂无高相关条目</li>"
        rows = []
        for n in items:
            rows.append(
                "<li>"
                f"【{html_mod.escape(n.level)}】"
                f"<a href='{html_mod.escape(n.link)}' target='_blank' rel='noopener'>"
                f"{html_mod.escape(n.title)}</a></li>"
            )
        return "".join(rows)

    totals = ""
    if brief.total_market_value is not None:
        sign = "+" if (brief.total_pnl or 0) >= 0 else ""
        totals = (
            f"<p class='sum'>持仓合计约 {brief.total_market_value:.2f} 元，"
            f"浮动盈亏约 {sign}{brief.total_pnl:.2f} 元。</p>"
        )

    return (
        f'<section class="cat market"><h2>📈 A股晨间雷达</h2>'
        f"<p class='sum'><strong>结论：</strong>今日整体倾向 {html_mod.escape(brief.bias)}；"
        f"{html_mod.escape(brief.volume_note)}；{html_mod.escape(brief.sector_note)}</p>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>股市面 · 指数</h3><ul>{li_indices()}</ul>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>行业面 · 你关注的板块</h3><ul>{li_sectors()}</ul>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>持仓快照</h3><ul>{li_holdings()}</ul>{totals}"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>政策面 · 值得关注</h3><ul>{li_news(brief.policy_news)}</ul>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>行业面 · 相关资讯</h3><ul>{li_news(brief.industry_news)}</ul>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>股市面 · 市场资讯</h3><ul>{li_news(brief.market_news)}</ul>"
        f"<p class='sum'>新手提醒：{html_mod.escape(brief.tip)}</p></section>"
    )
