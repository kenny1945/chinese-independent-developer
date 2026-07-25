#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 README 及子版面解析为结构化 JSON。

用法：
    python3 scripts/parse_readme.py            # 生成 data/projects.json
    python3 scripts/parse_readme.py --stats    # 额外打印统计信息

数据结构（projects.json）：
{
  "generated_at": "2026-07-24T12:00:00Z",
  "count": 1234,
  "editions": {...},          # 各版面产品数
  "projects": [
    {
      "id": "…",              # 由 名称+url 生成的稳定 id
      "name": "产品名",
      "url": "https://…",
      "description": "一句话介绍",
      "status": "online|developing|closed|unknown",
      "edition": "main|programmer|game|archive",
      "developer": "开发者名",
      "developer_links": [{"label": "GitHub", "url": "…"}],
      "extra_links": [{"label": "更多介绍", "url": "…"}],
      "date_added": "2026-07-24",   # 可能为 null
      "source_file": "README.md",
      "source_line": 30
    }
  ]
}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from categorize import categorize, CATEGORY_LABELS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 版面 -> 源文件
SOURCES = {
    "main": ROOT / "README.md",
    "programmer": ROOT / "pages" / "README-Programmer-Edition.md",
    "game": ROOT / "pages" / "README-Game.md",
    "archive": ROOT / "pages" / "README-2018-2020.md",
}

# emoji 短码 -> 状态
STATUS_MAP = {
    ":white_check_mark:": "online",     # 已上线
    ":clock8:": "developing",           # 开发中
    ":x:": "closed",                    # 已关闭/缺乏维护
}

# 日期分组标题：### 2026 年 7 月 24 号添加 / ### 2020年12月23号添加
RE_DATE_HEADER = re.compile(
    r"^###\s+(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*号"
)
# 开发者标题：#### 名字 - [GitHub](url), [博客](url)   或   #### 名字
RE_DEV_HEADER = re.compile(r"^####\s+(.*\S)\s*$")
# 产品条目：*/- :emoji: [名称](url)：描述
RE_PRODUCT = re.compile(
    r"^\s*[*\-]\s*(:[a-z0-9_+]+:)?\s*\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)"
    r"\s*[：:]\s*(?P<desc>.*)$"
)
# markdown 链接
RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def parse_dev_header(text: str):
    """从 #### 标题拆出开发者名 + 主页链接列表。"""
    links = [{"label": m.group(1), "url": m.group(2)} for m in RE_MD_LINK.finditer(text)]
    # 开发者名：取第一个 " - " 之前的部分，并去掉 markdown 链接语法
    name_part = text.split(" - ")[0].strip()
    name_part = RE_MD_LINK.sub(lambda m: m.group(1), name_part).strip()
    return name_part, links


def make_id(name: str, url: str) -> str:
    return hashlib.sha1(f"{name}|{url}".encode("utf-8")).hexdigest()[:12]


def parse_file(edition: str, path: Path):
    projects = []
    if not path.exists():
        return projects

    cur_date = None
    cur_dev = None
    cur_dev_links = []

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()

        m = RE_DATE_HEADER.match(line)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            try:
                cur_date = f"{y:04d}-{mo:02d}-{d:02d}"
            except ValueError:
                cur_date = None
            continue

        if line.startswith("#### "):
            cur_dev, cur_dev_links = parse_dev_header(line[len("#### "):])
            continue

        m = RE_PRODUCT.match(line)
        if m:
            emoji = m.group(1)
            desc_raw = m.group("desc").strip()
            # 描述里附带的额外链接（如「更多介绍」「鸿蒙版本」）
            extra = [
                {"label": lm.group(1), "url": lm.group(2)}
                for lm in RE_MD_LINK.finditer(desc_raw)
            ]
            # 描述纯文本：去掉尾部的「- [xxx](url)」链接装饰
            desc_clean = RE_MD_LINK.sub(lambda lm: lm.group(1), desc_raw).strip()
            desc_clean = re.sub(r"\s*-\s*$", "", desc_clean).strip(" -")

            name = m.group("name").strip()
            url = m.group("url").strip()
            # 跳过指向子版面的相对链接（非真实产品）
            if not url.startswith("http"):
                continue
            projects.append(
                {
                    "id": make_id(name, url),
                    "name": name,
                    "url": url,
                    "description": desc_clean,
                    "status": STATUS_MAP.get(emoji, "unknown"),
                    "category": categorize(name, desc_clean, url, edition),
                    "edition": edition,
                    "developer": cur_dev,
                    "developer_links": cur_dev_links,
                    "extra_links": extra,
                    "date_added": cur_date,
                    "source_file": str(path.relative_to(ROOT)),
                    "source_line": lineno,
                }
            )

    return projects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "projects.json"))
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    all_projects = []
    for edition, path in SOURCES.items():
        all_projects.extend(parse_file(edition, path))

    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(all_projects),
        "editions": dict(Counter(p["edition"] for p in all_projects)),
        "status_breakdown": dict(Counter(p["status"] for p in all_projects)),
        "category_breakdown": dict(Counter(p["category"] for p in all_projects)),
        "category_labels": CATEGORY_LABELS,
        "projects": all_projects,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ 已写入 {out_path.relative_to(ROOT)}：{out['count']} 个产品")

    if args.stats:
        print("\n各版面：")
        for k, v in out["editions"].items():
            print(f"  {k:12s} {v}")
        print("\n状态分布：")
        for k, v in out["status_breakdown"].items():
            print(f"  {k:12s} {v}")
        print("\n品类分布：")
        for k, v in Counter(
            p["category"] for p in all_projects
        ).most_common():
            print(f"  {CATEGORY_LABELS.get(k, k):16s} {v}")
        no_date = sum(1 for p in all_projects if not p["date_added"])
        no_dev = sum(1 for p in all_projects if not p["developer"])
        print(f"\n无日期：{no_date}  无开发者：{no_dev}")


if __name__ == "__main__":
    main()
