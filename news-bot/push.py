#!/usr/bin/env python3
"""Push news digests to Telegram / PushPlus / generic webhook / email."""

from __future__ import annotations

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib import error, request


class PushError(RuntimeError):
    pass


def _post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "NewsBot/1.0"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body) if body else {}
            except json.JSONDecodeError:
                return {"raw": body}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise PushError(f"HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise PushError(str(exc)) from exc


def push_telegram(text: str) -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return "skip:telegram (missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"

    # Telegram 单条上限约 4096，过长则截断
    body = text if len(text) <= 3900 else text[:3890] + "\n\n…(已截断)"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    _post_json(
        url,
        {
            "chat_id": chat_id,
            "text": body,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
    )
    return "ok:telegram"


def push_pushplus(text: str, title: str) -> str:
    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not token:
        return "skip:pushplus (missing PUSHPLUS_TOKEN)"

    payload = {
        "token": token,
        "title": title,
        "content": text if len(text) <= 18000 else text[:17900] + "\n\n…(已截断)",
        "template": "markdown",
    }
    result = _post_json("https://www.pushplus.plus/send", payload)
    code = result.get("code")
    if code not in (None, 200, "200"):
        raise PushError(f"PushPlus 失败: {result}")
    return "ok:pushplus"


def push_webhook(text: str, title: str) -> str:
    url = os.environ.get("WEBHOOK_URL", "").strip()
    if not url:
        return "skip:webhook (missing WEBHOOK_URL)"

    # 兼容 Discord / 通用 webhook / 企业微信机器人简易格式
    kind = os.environ.get("WEBHOOK_TYPE", "auto").strip().lower()
    if kind == "discord" or ("discord.com" in url or "discordapp.com" in url):
        payload: dict[str, Any] = {"content": text if len(text) <= 1900 else text[:1890] + "\n…"}
    elif kind in {"wecom", "wechat", "qywx"} or "qyapi.weixin.qq.com" in url:
        payload = {"msgtype": "markdown", "markdown": {"content": text[:4000]}}
    elif kind in {"dingtalk", "ding"} or "oapi.dingtalk.com" in url:
        payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text[:18000]}}
    else:
        payload = {"title": title, "text": text, "content": text}

    _post_json(url, payload)
    return "ok:webhook"


def push_email(text: str, title: str, html_body: str | None = None) -> str:
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    mail_to = os.environ.get("MAIL_TO", "").strip() or user
    mail_from = os.environ.get("MAIL_FROM", "").strip() or user
    port = int(os.environ.get("SMTP_PORT", "465"))

    if not host or not user or not password or not mail_to:
        return "skip:email (missing SMTP_HOST / SMTP_USER / SMTP_PASS / MAIL_TO)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = title
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.sendmail(mail_from, [addr.strip() for addr in mail_to.split(",")], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(mail_from, [addr.strip() for addr in mail_to.split(",")], msg.as_string())
    return "ok:email"


def push_all(title: str, markdown: str, plain: str, html_body: str | None = None) -> list[str]:
    results: list[str] = []
    for fn in (
        lambda: push_telegram(markdown),
        lambda: push_pushplus(markdown, title),
        lambda: push_webhook(markdown, title),
        lambda: push_email(plain, title, html_body),
    ):
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001
            results.append(f"error:{exc}")
    return results
