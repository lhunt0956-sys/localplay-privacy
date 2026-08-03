# 自动化新闻推送

每天定时抓取 RSS 新闻源，生成摘要页面，并可推送到微信 / Telegram / 邮件 / Webhook。

## 功能

- 多 RSS 源聚合（可在 `news-bot/config.yaml` 配置）
- 按分类整理，去重，按时间排序
- 输出 `news/latest.html` / `news/latest.md` / `news/latest.json`
- GitHub Actions 每天自动运行
- 支持推送渠道：
  - **PushPlus**（微信，推荐国内用户）
  - **Telegram Bot**
  - **通用 Webhook**（Discord / 企业微信 / 钉钉）
  - **邮件 SMTP**

## 快速开始

### 1. 本地试跑

```bash
cd news-bot
pip install -r requirements.txt
python main.py --dry-run          # 只打印
python main.py                    # 写出到 ../news/
```

### 2. 配置推送（任选其一）

在 GitHub 仓库 **Settings → Secrets and variables → Actions** 添加：

| Secret | 说明 |
| --- | --- |
| `PUSHPLUS_TOKEN` | [pushplus.plus](https://www.pushplus.plus/) 的 token，推送到微信 |
| `TELEGRAM_BOT_TOKEN` | Telegram BotFather 发放的 token |
| `TELEGRAM_CHAT_ID` | 接收消息的 chat id |
| `WEBHOOK_URL` | Discord / 企业微信 / 钉钉机器人地址 |
| `WEBHOOK_TYPE` | 可选：`discord` / `wecom` / `dingtalk` / `auto` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `MAIL_TO` | 邮件推送 |

未配置任何渠道时，Actions 仍会生成并提交摘要文件，只是跳过推送。

### 3. 手动触发

打开 **Actions → Daily News Push → Run workflow**。

默认每天 **北京时间 08:00** 自动执行。

## 自定义新闻源

编辑 `news-bot/config.yaml`：

```yaml
feeds:
  - name: 你的源
    url: https://example.com/rss.xml
    category: 科技
```

## 查看摘要

打开仓库中的 [`news/latest.html`](../news/latest.html)，或启用 GitHub Pages 后访问该页面。

## 目录

```
news-bot/
  config.yaml      # 新闻源与参数
  digest.py        # 抓取与格式化
  push.py          # 多渠道推送
  main.py          # 入口
  requirements.txt
news/              # 自动生成的摘要
.github/workflows/news-push.yml
```
