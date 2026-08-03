#!/usr/bin/env python3
"""A-share market snapshot + holdings radar from stock-learning skill."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import asdict, dataclass
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
class MarketBrief:
    indices: list[IndexQuote]
    holdings: list[HoldingQuote]
    total_market_value: float | None
    total_pnl: float | None
    bias: str
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "indices": [i.to_dict() for i in self.indices],
            "holdings": [h.to_dict() for h in self.holdings],
            "total_market_value": self.total_market_value,
            "total_pnl": self.total_pnl,
            "bias": self.bias,
            "errors": self.errors,
        }


def load_portfolio(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (ROOT / "portfolio.yaml")
    with cfg_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fetch_sina(codes: list[str]) -> dict[str, list[str]]:
    if not codes:
        return {}
    url = "https://hq.sinajs.cn/list=" + ",".join(codes)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 NewsBot/1.0",
            "Referer": "https://finance.sina.com.cn",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("gbk", errors="replace")

    out: dict[str, list[str]] = {}
    for line in raw.splitlines():
        m = re.match(r'var hq_str_([^=]+)="(.*)";?', line.strip())
        if not m:
            continue
        code, payload = m.group(1), m.group(2)
        if not payload:
            out[code] = []
            continue
        out[code] = payload.split(",")
    return out


def _parse_index(name: str, fields: list[str]) -> IndexQuote | None:
    # s_ 简要行情: name, price, change, pct, volume, amount
    if len(fields) < 4:
        return None
    try:
        return IndexQuote(
            name=name,
            price=float(fields[1]),
            change=float(fields[2]),
            pct=float(fields[3]),
        )
    except ValueError:
        return None


def _parse_stock_price(fields: list[str]) -> float | None:
    # 个股: name, open, close_y, price, high, low, ...
    if len(fields) < 4:
        return None
    try:
        price = float(fields[3])
        return price if price > 0 else None
    except ValueError:
        return None


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

    # 涨跌结论：用主要指数平均涨跌幅粗判
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

    return MarketBrief(
        indices=indices,
        holdings=holdings,
        total_market_value=round(total_mv, 2) if any_price else None,
        total_pnl=round(total_pnl, 2) if any_price else None,
        bias=bias,
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
    return keys


def news_priority(text: str, portfolio: dict[str, Any] | None = None) -> int:
    """Higher is more important. Aligns with market-info.md priority table."""
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
    return score


def format_market_markdown(brief: MarketBrief) -> str:
    lines = ["## 📈 A股晨间雷达（stock-learning）", ""]
    lines.append(f"**结论**：今日整体倾向 **{brief.bias}**（按主要指数涨跌粗判）")
    lines.append("")
    if brief.indices:
        lines.append("### 指数")
        lines.append("")
        for i in brief.indices:
            sign = "+" if i.pct >= 0 else ""
            lines.append(
                f"- {i.name}：{i.price:.2f}（{sign}{i.change:.2f} / {sign}{i.pct:.2f}%）"
            )
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
    lines.append(
        "> 观察重点：涨跌结论 → 核心驱动 → 行业分化 → 量能。"
        "新手提醒：今天涨不代表明天涨；板块轮动是常态，别追高换仓。"
    )
    lines.append("")
    return "\n".join(lines)


def format_market_html(brief: MarketBrief) -> str:
    import html as html_mod

    rows = []
    for i in brief.indices:
        sign = "+" if i.pct >= 0 else ""
        color = "#0e7c66" if i.pct >= 0 else "#b42318"
        rows.append(
            f"<li><strong>{html_mod.escape(i.name)}</strong> "
            f"{i.price:.2f} "
            f"<span style='color:{color}'>{sign}{i.pct:.2f}%</span></li>"
        )
    hold_rows = []
    for h in brief.holdings:
        if not h.available or h.price is None:
            hold_rows.append(
                f"<li>{html_mod.escape(h.name)}（{html_mod.escape(h.symbol)}）：暂无报价</li>"
            )
            continue
        sign = "+" if (h.pnl or 0) >= 0 else ""
        color = "#0e7c66" if (h.pnl or 0) >= 0 else "#b42318"
        hold_rows.append(
            "<li>"
            f"<strong>{html_mod.escape(h.name)}</strong>（{html_mod.escape(h.symbol)}） "
            f"现价 {h.price:.3f} · 盈亏 "
            f"<span style='color:{color}'>{sign}{h.pnl:.2f}（{sign}{h.pnl_pct:.2f}%）</span>"
            f" · 仓位约 {html_mod.escape(h.weight_hint)}"
            "</li>"
        )
    totals = ""
    if brief.total_market_value is not None:
        sign = "+" if (brief.total_pnl or 0) >= 0 else ""
        totals = (
            f"<p class='sum'>持仓合计约 {brief.total_market_value:.2f} 元，"
            f"浮动盈亏约 {sign}{brief.total_pnl:.2f} 元。</p>"
        )
    return (
        f'<section class="cat market"><h2>📈 A股晨间雷达</h2>'
        f"<p class='sum'><strong>结论：</strong>今日整体倾向 {html_mod.escape(brief.bias)}"
        f"（按主要指数涨跌粗判）</p>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>指数</h3><ul>{''.join(rows)}</ul>"
        f"<h3 style='margin:14px 0 8px;font-size:0.95rem'>持仓快照</h3><ul>{''.join(hold_rows)}</ul>"
        f"{totals}"
        f"<p class='sum'>观察：涨跌结论 → 核心驱动 → 行业分化 → 量能。"
        f"提醒：今天涨不代表明天涨；别追高换仓。</p></section>"
    )
