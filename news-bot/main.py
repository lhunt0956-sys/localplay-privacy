#!/usr/bin/env python3
"""CLI entry: fetch news, write digest files, optionally push."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from digest import (
    ROOT,
    build_digest,
    format_html,
    format_markdown,
    format_plain,
    load_config,
)
from push import push_all


def main() -> int:
    parser = argparse.ArgumentParser(description="自动化新闻抓取与推送")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT.parent / "news",
        help="摘要输出目录",
    )
    parser.add_argument("--push", action="store_true", help="向已配置渠道推送")
    parser.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = parser.parse_args()

    config = load_config(args.config)
    digest = build_digest(config)
    md = format_markdown(digest)
    plain = format_plain(digest)
    html = format_html(digest)
    fmt = (config.get("message_format") or "markdown").lower()
    push_body = {"markdown": md, "plain": plain, "html": html}.get(fmt, md)

    print(md)
    if digest.errors:
        print("Warnings:", file=sys.stderr)
        for err in digest.errors:
            print(f"  - {err}", file=sys.stderr)

    if args.dry_run:
        return 0 if digest.items else 1

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    date_tag = digest.generated_at.strftime("%Y-%m-%d")
    (out_dir / "latest.md").write_text(md, encoding="utf-8")
    (out_dir / "latest.html").write_text(html, encoding="utf-8")
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / f"{date_tag}.md").write_text(md, encoding="utf-8")
    (out_dir / f"{date_tag}.html").write_text(html, encoding="utf-8")
    (out_dir / "latest.json").write_text(
        json.dumps(
            {
                "title": digest.title,
                "generated_at": digest.generated_at.isoformat(),
                "timezone": digest.timezone,
                "count": len(digest.items),
                "items": [item.to_dict() for item in digest.items],
                "errors": digest.errors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote digest to {out_dir}", file=sys.stderr)

    if args.push:
        results = push_all(digest.title, push_body if fmt == "markdown" else md, plain, html)
        for line in results:
            print(f"push: {line}", file=sys.stderr)
        if any(r.startswith("error:") for r in results):
            return 2
        if all(r.startswith("skip:") for r in results):
            print(
                "No push channels configured. Set PUSHPLUS_TOKEN / TELEGRAM_* / WEBHOOK_URL / SMTP_* secrets.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
