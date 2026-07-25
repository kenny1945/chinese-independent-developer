#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量检测产品链接存活状态（仅用标准库，便于在 CI 中运行）。

用法：
    python3 scripts/check_links.py                 # 检测全部
    python3 scripts/check_links.py --limit 50      # 只测前 50 条（本地调试）
    python3 scripts/check_links.py --workers 32     # 并发数
    python3 scripts/check_links.py --report dead_links.md   # 额外输出失效清单

判定策略（保守，尽量不误杀）：
    alive    2xx / 3xx，以及 401/403/405/429/503 等「站点存在但拦截爬虫/限流」
    dead     404 / 410 / DNS 解析失败 / 连接被拒绝
    unknown  超时、SSL 错误、其它未知情况（不轻易判死）
"""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "projects.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# 这些状态码代表「站点存在」，不算失效
ALIVE_CODES = {401, 403, 405, 406, 429, 503, 999}
DEAD_CODES = {404, 410}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE  # 证书问题不作为「失效」依据


def _request(url: str, method: str, timeout: int):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX)


def classify(url: str, timeout: int = 12):
    """返回 (state, code, note)。"""
    for method in ("HEAD", "GET"):
        try:
            resp = _request(url, method, timeout)
            code = resp.getcode()
            resp.close()
            return "alive", code, None
        except urllib.error.HTTPError as e:
            code = e.code
            if code in DEAD_CODES:
                return "dead", code, None
            if code in ALIVE_CODES or 200 <= code < 400:
                return "alive", code, None
            # 405 之类可能只是 HEAD 不支持 —— GET 再试一次
            if method == "HEAD":
                continue
            return "unknown", code, f"http {code}"
        except urllib.error.URLError as e:
            reason = str(getattr(e, "reason", e)).lower()
            if any(k in reason for k in ("name or service not known",
                                         "nodename nor servname",
                                         "getaddrinfo failed",
                                         "no address associated")):
                return "dead", None, "dns"
            if "refused" in reason:
                return "dead", None, "connection refused"
            if "timed out" in reason or "timeout" in reason:
                if method == "HEAD":
                    continue
                return "unknown", None, "timeout"
            if method == "HEAD":
                continue
            return "unknown", None, reason[:80]
        except Exception as e:  # noqa: BLE001
            if method == "HEAD":
                continue
            return "unknown", None, str(e)[:80]
    return "unknown", None, "unreachable"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0, help="0 = 全部")
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--out", default=str(ROOT / "data" / "link_status.json"))
    ap.add_argument("--report", default="", help="失效清单 markdown 输出路径")
    args = ap.parse_args()

    projects = json.loads(DATA.read_text(encoding="utf-8"))["projects"]
    # 去重 URL（多个产品可能同 URL），按 URL 检测一次
    seen = {}
    for p in projects:
        seen.setdefault(p["url"], p)
    targets = list(seen.values())
    if args.limit:
        targets = targets[: args.limit]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(classify, p["url"], args.timeout): p for p in targets}
        for fut in as_completed(futures):
            p = futures[fut]
            state, code, note = fut.result()
            results[p["url"]] = {
                "state": state,
                "code": code,
                "note": note,
                "checked_at": now,
            }
            done += 1
            if done % 100 == 0:
                print(f"  …已检测 {done}/{len(targets)}")

    summary = {"alive": 0, "dead": 0, "unknown": 0}
    for r in results.values():
        summary[r["state"]] += 1

    out = {
        "generated_at": now,
        "checked": len(results),
        "summary": summary,
        "results": results,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {out_path.relative_to(ROOT)}  "
          f"存活 {summary['alive']} · 失效 {summary['dead']} · 未知 {summary['unknown']}")

    # 失效清单（按产品，含开发者，便于人工核对）
    dead = []
    for p in projects:
        r = results.get(p["url"])
        if r and r["state"] == "dead":
            dead.append((p, r))
    if args.report and dead:
        lines = [f"# 失效链接清单（{now}）", "",
                 f"共 {len(dead)} 条疑似失效：", "",
                 "| 产品 | 开发者 | 版面 | 原因 | 链接 |",
                 "| --- | --- | --- | --- | --- |"]
        for p, r in dead:
            reason = r["note"] or (f"HTTP {r['code']}" if r["code"] else "")
            lines.append(f"| {p['name']} | {p['developer']} | {p['edition']} "
                         f"| {reason} | {p['url']} |")
        Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"📝 失效清单 -> {args.report}（{len(dead)} 条）")

    # 供 CI step summary 使用
    if summary["dead"]:
        print(f"::warning::发现 {summary['dead']} 条疑似失效链接")


if __name__ == "__main__":
    main()
