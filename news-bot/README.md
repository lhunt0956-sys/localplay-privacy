# Hunt 个性化新闻推送（含 stock-learning）

按个人兴趣 + **stock-learning Skill** 定制的每日简报。

## 板块

1. **📈 A股晨间雷达**（指数涨跌 + 持仓现价/盈亏）
2. **持仓相关**新闻（神华/长电/工行/半导体/新能源/沪深300 优先）
3. A股与宏观 / 能源与电力
4. 通信与安防
5. AI与科技
6. Android开发
7. 健康生活
8. **📚 今日学习点**（来自 knowledge 成长路径）
9. 😄【郭式一乐】
10. 免责声明

## stock-learning 已并入

- `portfolio.yaml`：持仓成本、代码、观察指标
- `stock-learning/`：原 Skill 参考文档
- 新闻优先级：央行政策 > 行业监管 > 财报分红 > 普通消息
- 术语学习点按日轮换；输出带免责声明

持仓变更时改 `news-bot/portfolio.yaml` 即可。

## 个性化规则

- 宽源必须命中兴趣关键词才入选
- 英文自动译简体；繁体转简体
- 持仓关键词命中的新闻提升到「持仓相关」

## 本地运行

```bash
pip install -r requirements.txt
python main.py --dry-run
python main.py --push
```

## 推送渠道

| Secret | 用途 |
| --- | --- |
| `PUSHPLUS_TOKEN` | 微信（推荐） |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Telegram |
| `WEBHOOK_URL` | Discord / 企业微信 / 钉钉 |
| `SMTP_*` / `MAIL_TO` | 邮件 |

每天北京时间 08:00 自动跑；也可在 Actions 手动触发。
