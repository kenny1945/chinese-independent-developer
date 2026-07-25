#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取产品关联 GitHub 仓库的 star 数。

用法：
    python3 scripts/fetch_stars.py            # 生成 data/stars.json
    python3 scripts/fetch_stars.py --limit 50 # 只取前 50 个仓库（调试）

Token 来源（按序尝试）：环境变量 GITHUB_TOKEN → `gh auth token`。
使用 GraphQL 批量查询（100 个仓库/请求），599 个仓库约 6 次请求即可完成，
远优于逐个 REST 调用。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HAS_GH = shutil.which("gh") is not None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "projects.json"
API = "https://api.github.com/graphql"

# 从 URL 提取 owner/repo（保留其后路径用于判断是否 issue/PR 等）
RE_REPO = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)(?P<rest>/[^\s]*)?"
)
# owner/repo 允许的字符
RE_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
# 这些不是用户名，是 GitHub 自己的路径
RESERVED = {"orgs", "topics", "collections", "sponsors", "features",
            "about", "settings", "marketplace", "explore", "pricing"}
# 指向仓库「附属页面」而非仓库本身的链接：清单里常见
# 「更多介绍 → 本仓库的某个 issue」，那不是产品自己的仓库
NON_REPO_SEGMENTS = {"issues", "pull", "pulls", "discussions", "wiki",
                     "releases", "actions", "projects", "commits", "compare",
                     "milestone", "labels", "stargazers", "network", "graphs"}
# 索引仓库自身（含各种 fork），永远不算某个产品的仓库
INDEX_REPO_NAME = "chinese-independent-developer"

BATCH = 100


def repo_of(url: str | None) -> str | None:
    """从 URL 解析出 owner/repo，非仓库链接返回 None。"""
    m = RE_REPO.match(url or "")
    if not m:
        return None
    owner, name = m.group(1), m.group(2)
    name = re.sub(r"\.git$", "", name).rstrip(").,;")
    if owner.lower() in RESERVED:
        return None
    if not (RE_SAFE.match(owner) and RE_SAFE.match(name)):
        return None
    # 索引仓库自身：清单里大量「更多介绍」指向它的 issue，不是产品仓库
    if name.lower() == INDEX_REPO_NAME:
        return None
    # github.com/owner/repo/issues/123 这类附属页面不算仓库链接
    rest = (m.group("rest") or "").strip("/").split("/")
    if rest and rest[0].lower() in NON_REPO_SEGMENTS:
        return None
    return f"{owner}/{name}"


def repo_for_project(p: dict) -> str | None:
    """产品主链接优先；否则看描述里的附加链接（如「开源」「源码」）。"""
    r = repo_of(p.get("url"))
    if r:
        return r
    for l in p.get("extra_links", []):
        r = repo_of(l.get("url"))
        if r:
            return r
    return None


def get_token() -> str:
    """取 token；有 gh 时它自己管认证，拿不到也无妨。"""
    import os
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    if HAS_GH:
        return ""  # 交给 gh 处理认证
    raise SystemExit(
        "❌ 找不到 GitHub token。请设置环境变量 GITHUB_TOKEN，或先运行 `gh auth login`。"
    )


def graphql(query: str, token: str) -> dict:
    """发送 GraphQL 请求。

    优先用 `gh api`（它自带认证与证书处理，本地和 Actions runner 都预装）；
    没有 gh 时回退到 urllib + token。
    """
    payload = json.dumps({"query": query})
    if HAS_GH:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            f.write(payload)
            tmp = f.name
        try:
            out = subprocess.run(["gh", "api", "graphql", "--input", tmp],
                                 capture_output=True, text=True, timeout=90)
            # 批量查询里若有仓库已删除/改名，GraphQL 会返回「部分数据 + 错误」，
            # 此时 gh 以非零退出，但 stdout 里的有效数据仍可用。
            try:
                body = json.loads(out.stdout)
            except (json.JSONDecodeError, ValueError):
                body = None
            if body and body.get("data"):
                return body
            if out.returncode != 0:
                raise RuntimeError(f"gh api 失败：{out.stderr[:300]}")
            return body or {}
        finally:
            Path(tmp).unlink(missing_ok=True)

    req = urllib.request.Request(
        API,
        data=payload.encode("utf-8"),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "chinese-independent-developer-stars",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_batch(repos: list[str], token: str) -> dict[str, int]:
    """一次查询一批仓库，返回 {owner/repo: stars}。"""
    parts = []
    alias_map = {}
    for i, full in enumerate(repos):
        owner, name = full.split("/", 1)
        alias = f"r{i}"
        alias_map[alias] = full
        parts.append(
            f'{alias}: repository(owner: "{owner}", name: "{name}") '
            f"{{ stargazerCount }}"
        )
    query = "query {\n" + "\n".join(parts) + "\n}"
    body = graphql(query, token)

    out = {}
    for alias, node in (body.get("data") or {}).items():
        # 仓库被删/改名/私有时 node 为 null，跳过即可
        if node and isinstance(node, dict):
            out[alias_map[alias]] = node.get("stargazerCount", 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "data" / "stars.json"))
    args = ap.parse_args()

    projects = json.loads(DATA.read_text(encoding="utf-8"))["projects"]
    repos = sorted({r for p in projects if (r := repo_for_project(p))})
    if args.limit:
        repos = repos[: args.limit]
    print(f"待查询仓库：{len(repos)}")

    token = get_token()
    stars: dict[str, int] = {}
    for i in range(0, len(repos), BATCH):
        chunk = repos[i:i + BATCH]
        try:
            stars.update(query_batch(chunk, token))
        except urllib.error.HTTPError as e:
            print(f"  ⚠️ 批次 {i//BATCH + 1} 失败：HTTP {e.code} {e.read()[:200]!r}")
            continue
        print(f"  …已查询 {min(i+BATCH, len(repos))}/{len(repos)}")

    missing = [r for r in repos if r not in stars]
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_count": len(stars),
        "missing_count": len(missing),
        "stars": stars,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    top = sorted(stars.items(), key=lambda kv: -kv[1])[:10]
    print(f"\n✅ {out_path.relative_to(ROOT)}："
          f"{len(stars)} 个仓库有星数，{len(missing)} 个无法获取（已删除/私有/改名）")
    print("\n⭐ Top 10：")
    for repo, n in top:
        print(f"  {n:>7,}  {repo}")


if __name__ == "__main__":
    main()
