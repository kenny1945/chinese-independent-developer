# 数据流水线

把 README 里的产品清单变成结构化数据 + 可搜索站点，共三步。

## 1. 解析：README → 结构化 JSON

```bash
python3 scripts/parse_readme.py --stats
```

解析主 README 和 3 个子版面，输出 [`data/projects.json`](projects.json)：
每个产品包含名称、链接、一句话介绍、状态（已上线/开发中/已关闭）、
版面、开发者及其主页链接、添加日期、源文件行号。

## 2. 存活检测：标记失效链接

```bash
python3 scripts/check_links.py --workers 30 --report data/dead_links.md
```

并发检测所有产品链接，输出 [`data/link_status.json`](link_status.json)
（每个 URL 的 alive/dead/unknown）和人工可读的失效清单
[`data/dead_links.md`](dead_links.md)。

判定保守：401/403/405/429 等「拦截爬虫/限流」算存活，
只有 404/410/DNS 失败/拒绝连接才判失效，避免误杀。

自动化：[`.github/workflows/check_links.yml`](../.github/workflows/check_links.yml)
每周一自动跑一次，把结果提交回仓库并写入任务摘要。

## 3. 站点：可搜索 / 可筛选目录

根目录 [`index.html`](../index.html) 是纯静态单页，读取上面两个 JSON，
支持：关键词搜索（产品名/介绍/开发者）、按版面和状态筛选、
排序、以及基于存活检测的「隐藏失效链接」开关。

本地预览：

```bash
python3 -m http.server 8000
```

然后打开 http://localhost:8000 。部署时在仓库
Settings → Pages 选择 `main` 分支根目录即可上线。
