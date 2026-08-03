#!/usr/bin/env python3
"""Daily learning tip from stock-learning knowledge path."""

from __future__ import annotations

from datetime import datetime

# 对应 knowledge.md 阶段一 + 少量阶段二，按日轮换
_TIPS = [
    {
        "title": "什么是指数",
        "body": "沪深300（Shanghai-Shenzhen 300 Index，沪深两市规模大、流动性好的300家公司）像“大盘平均分”。你买的300ETF，本质上就是在跟踪这个平均分。",
    },
    {
        "title": "PE（市盈率）",
        "body": "PE = 股价 ÷ 每股收益，粗看股票贵不贵。银行/能源股常见区间更低；神华这类更常结合股息率一起看，别只看PE。",
    },
    {
        "title": "PB（市净率）",
        "body": "PB = 股价 ÷ 每股净资产。工行常长期低于1，意思是市价比账面净资产还低——不等于一定便宜，但银行股里 PB 往往比 PE 更常用。",
    },
    {
        "title": "股息率",
        "body": "股息率 = 每股分红 ÷ 股价。偏防守时，高于约4%常被看作有一定现金回报缓冲。神华、工行的观察重点之一就是分红是否稳定。",
    },
    {
        "title": "ETF 适合新手的原因",
        "body": "ETF（交易型开放式指数基金）一篮子持股，分散单家公司暴雷风险。半导体/新能源这种高波动行业，用 ETF 比赌单票更适合学习仓。",
    },
    {
        "title": "T+1 是什么",
        "body": "A股当天买进，最早第二天才能卖。所以冲动追高的容错更低——买之前先问自己：逻辑还在吗，还是只是看着涨？",
    },
    {
        "title": "满仓的代价",
        "body": "现金几乎为0时，回调里没有子弹加仓。新手版仓位：核心防御60–70%，成长卫星20–30%，现金尽量留10–20%。",
    },
    {
        "title": "板块轮动",
        "body": "资金常在行业间切换，不是“好公司永远天天涨”。追昨天上涨板块，容易买在情绪高点；先看逻辑，再看价格。",
    },
    {
        "title": "净息差（银行）",
        "body": "净息差 = 贷款利率与存款利率的差距，是银行赚钱能力的核心之一。工行观察点：净息差是否继续收窄，以及不良贷款率。",
    },
    {
        "title": "护城河（初识）",
        "body": "护城河指公司难以被抢走的优势。长电的水电资产、神华的煤电一体，都是“不好复制”的例子——但护城河也会随产业政策变化。",
    },
]


def pick_learning_tip(when: datetime | None = None) -> dict[str, str]:
    when = when or datetime.now()
    tip = _TIPS[when.toordinal() % len(_TIPS)]
    return {
        "title": tip["title"],
        "body": tip["body"],
        "section": "📚 今日学习点",
    }


DISCLAIMER = (
    "⚡ 免责：以上内容仅供学习参考，不构成投资建议；投资有风险，决策需谨慎。"
)
