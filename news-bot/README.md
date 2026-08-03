# Hunt 个性化新闻推送

按个人兴趣定制的每日简报：通信安防、A股/能源、AI·Android、健康出行，末尾带「郭式一乐」。

## 板块

1. A股与宏观  
2. 能源与电力  
3. 通信与安防  
4. AI与科技  
5. Android开发  
6. 健康生活  
7. 摩托出行  
8. 😄【郭式一乐】

## 个性化规则

- 宽源（FT、CNBC、IT之家、36氪等）必须命中兴趣关键词才会入选  
- 关键词覆盖：神华/长江电力/工行、能源电力、铁塔基站/视频监控/安防、AI/Android/Kotlin、血压睡眠饮食、摩托出行  
- 命中越多排序越靠前；每板块有上限，避免某一类刷屏  

改兴趣：编辑 `config.yaml` 里的 `feeds` 和 `keywords`。

## 本地运行

```bash
pip install -r requirements.txt
python main.py --dry-run
python main.py --push
```

## 推送渠道

在 GitHub Secrets 配置任一：

| Secret | 用途 |
| --- | --- |
| `PUSHPLUS_TOKEN` | 微信（推荐） |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Telegram |
| `WEBHOOK_URL` | Discord / 企业微信 / 钉钉 |
| `SMTP_*` / `MAIL_TO` | 邮件 |

每天北京时间 08:00 自动跑；也可在 Actions 里手动触发。
