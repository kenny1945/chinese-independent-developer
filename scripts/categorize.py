#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于关键词的产品品类分类（纯规则，无需联网/API）。

用法：
    from categorize import categorize, CATEGORY_LABELS
    cat = categorize(name, description, url, edition)

设计：按 RULES 顺序匹配「产品名 + 介绍 + 链接」文本，第一个命中的品类胜出；
都不命中则归为 other。游戏版面直接归 game。品类粒度以「用户会怎么找」为准。
"""
from __future__ import annotations

# 品类 code -> 中文标签（站点筛选用）
CATEGORY_LABELS = {
    "browser_ext": "浏览器插件",
    "ai": "AI / 大模型",
    "dev_tools": "开发者工具",
    "productivity": "效率工具",
    "design": "设计 / 创意",
    "media": "内容创作 / 媒体",
    "reading": "阅读 / 资讯",
    "marketing": "电商 / 营销增长",
    "education": "教育 / 学习",
    "finance": "金融 / 理财",
    "social": "社交 / 社区",
    "game": "游戏 / 娱乐",
    "life": "生活 / 健康",
    "toolbox": "工具箱 / 导航",
    "other": "其他",
}

# (品类, [关键词])，顺序即优先级——越具体越靠前
RULES = [
    ("browser_ext", [
        "chrome.google.com/webstore", "microsoftedge.microsoft.com", "addons.mozilla",
        "浏览器插件", "浏览器扩展", "chrome 插件", "chrome插件", "油猴", "tampermonkey",
    ]),
    ("ai", [
        "ai", "gpt", "大模型", "llm", "人工智能", "机器学习", "深度学习", "prompt",
        "提示词", "agent", "智能体", "chatbot", "对话机器人", "文生图", "文生视频",
        "aigc", "stable diffusion", "midjourney", "语音识别", "ocr", "智能",
        "claude", "deepseek", "语义", "向量", "rag", "知识库问答",
    ]),
    ("dev_tools", [
        "开发者", "开发工具", "代码", "编程", "程序员", " api", "api ", "sdk",
        "命令行", "cli", "终端", "数据库", "部署", "调试", "运维", "devops",
        "framework", "框架", "开源库", "组件库", "正则", "json", "抓包", "爬虫",
        "docker", "kubernetes", "服务器", "监控", "日志", "webhook",
    ]),
    ("productivity", [
        "效率", "笔记", "待办", "todo", "任务管理", "日历", "日程", "时间管理",
        "专注", "番茄", "知识管理", "文档", "表格", "思维导图", "协作", "剪贴板",
        "看板", "kanban", "提醒", "备忘", "白板", "流程图", "工作流",
    ]),
    ("design", [
        "设计", "ui ", " ui", "配色", "字体", "图标", "icon", "原型", "logo",
        "海报", "模板", "素材", "vi ", "界面设计", "排版",
    ]),
    ("media", [
        "视频", "音频", "音乐", "播客", "podcast", "图片", "照片", "写作",
        "剪辑", "字幕", "配音", "短视频", "封面", "壁纸", "gif", "录屏",
        "直播", "转录", "文章生成", "小红书文案", "配图",
    ]),
    ("reading", [
        "阅读", "rss", "新闻", "资讯", "小说", "读书", "书单", "文献", "论文",
        "电子书", "epub", "翻译", "词典",
    ]),
    ("marketing", [
        "电商", "营销", "增长", "seo", "geo", "推广", "广告", "私域", "获客",
        "运营", "变现", "出海", "跨境", "选品", "店铺", "带货", "投放",
        "落地页", "建站", "独立站", "shopify",
    ]),
    ("education", [
        "学习", "教育", "单词", "背单词", "考试", "课程", "刷题", "记忆",
        "英语", "口语", "错题", "学生", "教师", "题库", "培训",
    ]),
    ("finance", [
        "记账", "理财", "股票", "基金", "投资", "财务", "发票", "报销",
        "汇率", "加密货币", "比特币", "钱包", "账单", "预算", "薪资", "税",
    ]),
    ("social", [
        "社交", "社区", "聊天", "交友", "匿名", "论坛", "群聊", "约", "陌生人",
        "情侣", "恋爱", "树洞", "私信",
    ]),
    ("game", [
        "游戏", "game", "像素", "解谜", "休闲游戏", "独立游戏", "roguelike",
        "棋牌", "剧本杀", "桌游",
    ]),
    ("life", [
        "健康", "健身", "运动", "睡眠", "减肥", "饮食", "菜谱", "食谱", "天气",
        "旅行", "地图", "打卡", "习惯", "冥想", "医疗", "宠物", "情绪", "心理",
        "月经", "母婴", "菜单", "外卖", "记录生活",
    ]),
    ("toolbox", [
        "导航", "工具集", "工具箱", "合集", "大全", "聚合", "网址", "资源站",
        "一站式", "全家桶",
    ]),
]


def categorize(name: str, description: str, url: str = "", edition: str = "") -> str:
    if edition == "game":
        return "game"
    text = f" {name} {description} {url} ".lower()
    for cat, keywords in RULES:
        for kw in keywords:
            if kw in text:
                return cat
    return "other"


if __name__ == "__main__":
    # 简单自测
    samples = [
        ("AI故事书生成器", "AI 生成故事书", "", "main"),
        ("Doc2Md", "将 PDF、Word 转换成 Markdown", "", "main"),
        ("记账 App", "简单好用的记账工具", "", "main"),
        ("某浏览器扩展", "chrome 插件去广告", "", "main"),
        ("未知产品", "一个很酷的东西", "", "main"),
    ]
    for n, d, u, e in samples:
        print(f"{categorize(n, d, u, e):12s} <- {n} / {d}")
