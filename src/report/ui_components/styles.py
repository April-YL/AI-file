# [阶段一] 集中式 CSS 设计系统 — 从 ui_app.py 抽取
# 不修改 QcIssue / QcReport / pipeline
"""审计底稿复核 Agent — CSS 设计系统。

状态色使用规则：仅用于左侧 4px 细色条 + badge 文字色。
禁止大面积色块填充、禁止整行染色。
"""

from __future__ import annotations

# ---- CSS 变量（不可随意修改） ----
CSS_VARIABLES = """
:root {
    /* 品牌色 — 仅用于装饰细条 */
    --ey-black: #111111;
    --ey-ink: #2e2e38;
    --ey-yellow: #ffe600;
    --ey-yellow-muted: #b8a400;

    /* 状态色 — 仅用于左侧色条 + badge */
    --qc-high: #b42318;
    --qc-high-bg: #fff7f7;
    --qc-warn: #b54708;
    --qc-warn-bg: #fff9ed;
    --qc-review: #175cd3;
    --qc-review-bg: #f3f8ff;
    --qc-pass: #067647;
    --qc-pass-bg: #ecfdf3;

    /* 灰度 */
    --gray-900: #242424;
    --gray-700: #4b5563;
    --gray-500: #667085;
    --gray-300: #b0b7c3;
    --gray-200: #dadde2;
    --gray-100: #f4f4f6;
    --gray-50: #fbfbfb;
    --page-bg: #f7f7f8;

    --radius: 8px;
    --shadow: 0 1px 3px rgba(16,24,40,0.06), 0 1px 2px rgba(16,24,40,0.04);
}
"""

# ---- 全局布局样式 ----
GLOBAL_STYLES = """
.main .block-container {
    padding-top: 0.1rem;
    padding-bottom: 0.45rem;
    max-width: 1280px;
}
html, body, [data-testid="stAppViewContainer"] {
    background: var(--page-bg);
}
section.main > div {
    padding-top: 0;
}
/* 全局字体 */
html, body, [class*="css"] {
    font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
}
/* stat card grid 一致性 */
[data-testid="stVerticalBlock"] [data-testid="stVerticalBlock"] {
    gap: 0.38rem;
}
"""

# ---- Topbar ----
TOPBAR_STYLES = """
.qc-topbar {
    background: #ffffff;
    border-left: 5px solid var(--ey-yellow);
    border-top: 1px solid var(--gray-200);
    border-right: 1px solid var(--gray-200);
    border-bottom: 1px solid var(--gray-200);
    color: var(--ey-ink);
    padding: 7px 14px;
    margin-bottom: 8px;
    border-radius: 6px;
}
.qc-topbar h1 {
    margin: 0;
    font-size: 1rem;
    font-weight: 650;
    letter-spacing: 0;
}
.qc-topbar p {
    margin: 2px 0 0 0;
    color: var(--gray-500);
    font-size: 0.85rem;
}
"""

# ---- 文件/项目标题 ----
FILE_HEADER_STYLES = """
.qc-file-header {
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--ey-yellow);
    border-radius: 6px;
    background: #ffffff;
    padding: 8px 12px;
    margin: 3px 0 8px 0;
}
.qc-file-header h2 {
    margin: 0;
    color: var(--ey-black);
    font-size: 1.02rem;
    font-weight: 700;
}
.qc-file-header p {
    margin: 3px 0 0 0;
    color: var(--gray-500);
    font-size: 0.8rem;
}
"""

# ---- 章节标题 ----
SECTION_TITLE_STYLES = """
.qc-section-title {
    color: var(--ey-black);
    font-size: 0.98rem;
    font-weight: 700;
    margin: 4px 0 2px 0;
}
.qc-section-caption {
    color: var(--gray-500);
    font-size: 0.78rem;
    margin: 0 0 7px 0;
}
"""

# ---- 统计卡片 — 仅左侧 4px 色条，禁止大面积填充 ----
STAT_CARD_STYLES = """
.qc-stat-card {
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--accent, var(--gray-700));
    border-radius: 6px;
    background: #ffffff;
    padding: 8px 10px;
    min-height: 54px;
    box-shadow: var(--shadow);
}
.qc-stat-card-high   { --accent: var(--qc-high); }
.qc-stat-card-warn   { --accent: var(--qc-warn); }
.qc-stat-card-review { --accent: var(--qc-review); }
.qc-stat-card-pass   { --accent: var(--qc-pass); }
.qc-stat-card-info   { --accent: var(--ey-yellow); }
.qc-stat-label {
    color: var(--gray-500);
    font-size: 0.72rem;
    letter-spacing: 0;
}
.qc-stat-value {
    color: var(--ey-black);
    font-size: 1.28rem;
    font-weight: 750;
    line-height: 1.2;
    margin-top: 2px;
}
.qc-stat-note {
    color: var(--gray-500);
    font-size: 0.7rem;
    margin-top: 2px;
}
"""

# ---- Badge（严重性标签） ----
BADGE_STYLES = """
.qc-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0;
    border: 1px solid transparent;
}
.qc-badge-fail {
    color: var(--qc-high);
    background: var(--qc-high-bg);
    border-color: #fecdca;
}
.qc-badge-warn {
    color: var(--qc-warn);
    background: var(--qc-warn-bg);
    border-color: #fed7aa;
}
.qc-badge-review {
    color: var(--qc-review);
    background: var(--qc-review-bg);
    border-color: #b2ddff;
}
.qc-badge-pass {
    color: var(--qc-pass);
    background: var(--qc-pass-bg);
    border-color: #abefc6;
}
"""

# ---- 信息横幅 ----
INFO_BANNER_STYLES = """
.qc-info-banner {
    border-left: 4px solid var(--ey-yellow);
    background: #ffffff;
    border-top: 1px solid var(--gray-200);
    border-right: 1px solid var(--gray-200);
    border-bottom: 1px solid var(--gray-200);
    color: var(--gray-700);
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 0.82rem;
    margin: 6px 0 9px 0;
}
"""

# ---- 下载栏 ----
DOWNLOAD_BAR_STYLES = """
.qc-download-bar {
    display: flex;
    gap: 12px;
    align-items: center;
    padding: 8px 12px;
    background: var(--gray-50);
    border-radius: var(--radius);
    margin-bottom: 9px;
}
"""

# ---- 程序行 ----
PROCEDURE_ROW_STYLES = """
.qc-procedure-row {
    border: 1px solid #e4e4e4;
    border-left: 5px solid var(--ey-yellow);
    border-radius: 6px;
    padding: 8px 10px;
    margin-bottom: 7px;
    background: #ffffff;
}
.qc-procedure-title {
    font-weight: 700;
    color: var(--ey-black);
    margin-bottom: 6px;
}
.qc-procedure-meta {
    color: var(--gray-700);
    font-size: 0.84rem;
}
"""

# ---- 按钮 ----
BUTTON_STYLES = """
div.stButton > button[kind="primary"],
div.stDownloadButton > button[kind="primary"] {
    background: var(--ey-ink);
    color: #ffffff;
    border: 1px solid var(--ey-ink);
    border-radius: 4px;
}
div.stButton > button[kind="primary"]:hover,
div.stDownloadButton > button[kind="primary"]:hover {
    background: #1f1f26;
    border-color: #1f1f26;
    color: #ffffff;
}
div.stButton > button:disabled,
div.stButton > button:disabled:hover {
    background: var(--gray-100) !important;
    color: var(--gray-500) !important;
    border-color: var(--gray-200) !important;
    cursor: not-allowed !important;
    opacity: 1 !important;
}
div[data-testid="stExpander"] {
    border-radius: 6px;
}
"""

RUNNER_PROGRESS_STYLES = """
.qc-runner-status {
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--gray-700);
    background: #ffffff;
    padding: 8px 10px;
    border-radius: 6px;
    margin: 4px 0 8px;
    font-size: 0.84rem;
}
.qc-runner-status-running { border-left-color: var(--ey-yellow); }
.qc-runner-status-finished { border-left-color: var(--qc-pass); }
.qc-runner-status-failed { border-left-color: var(--qc-high); }
.qc-runner-status-meta {
    color: var(--gray-500);
    font-size: 0.74rem;
    margin-top: 3px;
}
.qc-step-chip {
    border: 1px solid var(--gray-200);
    border-left: 3px solid var(--gray-300);
    background: #ffffff;
    border-radius: 5px;
    padding: 5px 6px;
    min-height: 42px;
}
.qc-step-done { border-left-color: var(--qc-pass); }
.qc-step-active { border-left-color: var(--ey-yellow); }
.qc-step-failed { border-left-color: var(--qc-high); }
.qc-step-name {
    font-size: 0.7rem;
    font-weight: 650;
    color: var(--gray-900);
}
.qc-step-status {
    font-size: 0.66rem;
    color: var(--gray-500);
    margin-top: 2px;
}
.qc-runtime-strip {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 6px;
    margin: 5px 0 8px;
}
.qc-runtime-item {
    border: 1px solid var(--gray-200);
    background: #ffffff;
    border-radius: 5px;
    padding: 6px 8px;
}
.qc-runtime-label {
    color: var(--gray-500);
    font-size: 0.68rem;
}
.qc-runtime-value {
    color: var(--gray-900);
    font-size: 0.86rem;
    font-weight: 700;
    margin-top: 2px;
}
"""

# ---- 执行范围标签（Coverage tags） ----
COVERAGE_TAG_STYLES = """
.qc-coverage-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 600;
}
.qc-coverage-executed      { color: var(--qc-pass); background: var(--qc-pass-bg); }
.qc-coverage-insufficient  { color: var(--qc-warn); background: var(--qc-warn-bg); }
.qc-coverage-na            { color: var(--gray-500); background: var(--gray-100); }
.qc-coverage-llm-off       { color: var(--qc-review); background: var(--qc-review-bg); }
.qc-coverage-planned       { color: var(--gray-500); background: var(--gray-50); border: 1px dashed var(--gray-300); }
"""


# ---- Sidebar ----
SIDEBAR_STYLES = """
[data-testid="stSidebar"] {
    background: var(--ey-ink);
}
[data-testid="stSidebar"] .stMarkdown p {
    margin-bottom: 0;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent;
    border: none;
    color: rgba(255,255,255,0.65) !important;
    text-align: left;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 0.84rem;
    font-weight: 400;
    width: 100%;
    border-left: 3px solid transparent;
    transition: background 0.12s, border-color 0.12s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.85) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: rgba(255,255,255,0.08) !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    border-left: 3px solid var(--ey-yellow) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    border-left: 3px solid transparent !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.10) !important;
    margin: 2px 0;
}
.sidebar-brand-text {
    font-size: 0.92rem;
    font-weight: 700;
    color: #fff !important;
    margin-bottom: 2px;
}
.sidebar-subtitle {
    font-size: 0.68rem;
    color: rgba(255,255,255,0.40) !important;
    margin-bottom: 6px;
}
.sidebar-subject-tag {
    display: inline-block;
    font-size: 0.66rem;
    color: rgba(255,255,255,0.82) !important;
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 3px;
    padding: 1px 7px;
    margin-bottom: 8px;
    border-left: 3px solid var(--ey-yellow);
}
.sidebar-section-label {
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(255,255,255,0.25) !important;
    padding: 4px 4px 1px;
}
.sidebar-footer-text {
    font-size: 0.68rem;
    color: rgba(255,255,255,0.25) !important;
    padding: 4px 4px;
}
"""


def get_global_css() -> str:
    """返回完整的全局 CSS（替换旧 ui_app.py 的 _inject_style）。"""
    return (
        "<style>\n"
        + CSS_VARIABLES
        + GLOBAL_STYLES
        + TOPBAR_STYLES
        + FILE_HEADER_STYLES
        + SECTION_TITLE_STYLES
        + STAT_CARD_STYLES
        + BADGE_STYLES
        + INFO_BANNER_STYLES
        + DOWNLOAD_BAR_STYLES
        + PROCEDURE_ROW_STYLES
        + BUTTON_STYLES
        + COVERAGE_TAG_STYLES
        + RUNNER_PROGRESS_STYLES
        + SIDEBAR_STYLES
        + "\n</style>"
    )
