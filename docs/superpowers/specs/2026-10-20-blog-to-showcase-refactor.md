# Li&Blog 定位重构：拆分文章功能、专注个人展示

> 日期：2026-10-20 ｜ 版本：v0.1（草案，待确认槽位） ｜ 状态：待评审
> 取代：`2026-10-20-miniprogram-knowledge-query.md`（已删除，小程序方向暂停）
> 配套：`design-system/blog/BRAND.md`、`design-system/blog/MASTER.md`、`2026-08-18-learning-journey-blog-design.md`

## 0. 一句话结论

把 Li&Blog 从「博客（文章为主）」重构为「**个人展示站**」：拆走全部文章/学习笔记功能，保留并强化 Hero / 技能 / 项目集 / 时间线 / 关于我 / 资源 / 友情链接，并保留**页脚链接编辑接口**供随时新增链接网址。文章迁入独立的「学习笔记」新项目（默认 `Li&Notes`）。

## 1. 已确认决策（D）

- **D1（方案 A）**：文章功能独立成新项目，Li&Blog 只留个人展示。
- **D2**：保留页脚链接编辑接口，后台可随时新增/编辑/删除链接网址（复用现有「友情链接」CRUD + 页脚入口）。
- **D3**：拆走文章相关：搜索、归档、标签、RSS、阅读时长、相关推荐、Fuse.js、文章编辑器、批量导入。
- **D4**：本次只重构 Li&Blog，**暂不动 Li&About**（主页）；两者关系后续单独议。
- **D5**：沿用硬规则——公开站零交互、单一事实来源（brand/profile/strings/tokens）、备案、纯静态、Hugo 唯一渲染器。

## 2. 目标架构

```text
Li&Blog（个人展示站）          Li&Notes（学习笔记站，新项目）
├── 首页 Hero/技能/项目/历程     ├── 文章列表 + 详情 + 搜索 + 归档 + 标签 + RSS
├── 项目集 projects/            ├── content/posts/*（现有 40+ 篇迁入）
├── 时间线 timeline/            ├── Fuse.js 搜索 / Chroma 代码高亮
├── 关于我 about.md             ├── 后台：文章 CRUD/导入/标签/回收站
├── 资源 resources.md           └── 复用 Li-Design 主题令牌（--liblog-* 或 --linotes-*）
└── 友情链接 friends/（页脚可编辑）
```

- 两站共享 Li-Design 家族品牌内核与令牌方法，但**各自独立仓库、独立部署、独立后台**。
- 新项目默认路径 `~/Desktop/Li&ProJect/Li&Notes`，仓库 `Lzf07123/Li-Notes`（**槽位 A，待确认**）。

## 3. 内容与功能迁移映射

| 现有内容/功能 | Li&Blog（去留） | Li&Notes（去向） |
| --- | --- | --- |
| 首页 Hero（姓名/身份/方向/目标） | ✅ 保留 | — |
| 技能栈（profile.skills） | ✅ 保留 | — |
| 首页「最新文章」区块 | ❌ 移除 | ✅ 新站首页 |
| 项目集 projects/ | ✅ 保留 | — |
| 时间线 timeline/ | ✅ 保留 | — |
| 关于我 about.md | ✅ 保留 | — |
| 资源 resources.md | ✅ 保留（可选） | — |
| 友情链接 friends/ + 页脚链接编辑 | ✅ 保留（强化为页脚链接管理） | — |
| 文章 posts/ | ❌ 移除 | ✅ 迁入 |
| 搜索（Fuse.js + /search/index.json） | ❌ 移除 | ✅ 迁入 |
| 归档 archive.md | ❌ 移除 | ✅ 迁入 |
| 标签 taxonomy tags | ❌ 移除 | ✅ 迁入 |
| RSS / 相关推荐 / 阅读时长 | ❌ 移除 | ✅ 迁入 |
| 后台：文章 CRUD/批量导入/标签管理 | ❌ 移除 | ✅ 迁入 |
| 后台：品牌/文案/首页设置/关于/项目/时间线/友链/媒体/备份/统计 | ✅ 保留 | 按需复制 |
| 访问统计 beacon | ✅ 保留 | ✅ 可复制 |

## 4. Li&Blog 侧改动清单（按区域）

### 4.1 内容层 `content/`

- 删除：`posts/`（迁移后）、`search.md`、`archive.md`。
- 保留：`_index.md`、`about.md`、`resources.md`、`projects/`、`timeline/`、`friends/`。

### 4.2 配置层

- `hugo.toml`：移除 `[taxonomies] tag`、`[related]` 及 `related.indices`、`[outputs] home` 中的 `RSS`、`[outputFormats.Search]`；`pagination` 如无列表页使用则移除。
- `config/homepage.yaml`：删除 `posts` 块（featured/latest_count）；新增/保留 `footer_links` 开关。
- `config/strings.yaml`：删除 `home.latest_title`、`home.browse_posts`、`home.no_results`、`common.search_*`、`common.empty_posts`、`common.empty_archive`、`common.no_tags`、`common.post_nav`、`common.pagination*`、`common.reading_time` 等文章专属文案；保留并补充 `friends.*`（页脚链接文案）。
- `config/profile.yaml` / `brand.yaml`：不变。

### 4.3 主题层 `themes/blog-theme/`

- 模板：删除 `_default/rss.xml`、`_default/single.search.json`、`taxonomy/`、`archive/single.html`、`partials/search-modal.html`、`partials/post-card.html`、`partials/pagination.html`；`_default/single.html` / `_default/list.html` 改为「个人展示」语义（剥掉文章专属：TOC/阅读时长/标签/相关/上一篇下一篇/归档分组）。
- 静态资源：删除 `js/fuse.min.js`、`js/reading-progress.js`；`asset-versions.html` 同步去引用；首页/栏目 CSS 不变（氛围动效保留，文章页动效逻辑随单页模板剥离）。
- `partials/header.html` / `footer.html`：导航与页脚改为展示站口径（移除文章/归档入口，保留首页/项目/历程/关于/资源/友情链接 + 页脚链接列表）。

### 4.4 后台层 `admin/`

- `SECTIONS` 删除 `posts`；保留 projects/timeline/about/resources/friends。
- 删除文章相关路由/函数：文章 CRUD、搜索索引、标签管理、归档、批量导入；`content.py` 中 posts 专用逻辑随迁移。
- 保留：品牌/文案/首页设置、关于/项目/时间线/友链编辑、媒体库、备份恢复、统计、账号设置、审计。
- 友链：复用现有 friends CRUD，页脚展示「友情链接」列表（用户随时新增/编辑/删除网址）。

### 4.5 测试层 `tests/`

- 删除/改写：`test_content.py`、`test_admin_routes.py`、`test_importer.py`、`test_tags` 等中 posts/搜索/归档/标签相关用例；`test_build.py` 中 `search/index.json` 校验改为「不存在」或移除。
- 保留：brand/profile/strings 硬编码与对比度、构建编排、媒体、备份、统计、安全、OIDC 等。

## 5. Li&Notes 新项目骨架（Phase 2，独立工作区）

- 以现有 Li&Blog 全栈为蓝本，反方向裁剪：保留 posts/搜索/归档/标签/RSS + 文章后台；移除项目/时间线/关于/资源/友链/技能（或仅留极简关于页）。
- 主题复用 Li-Design 令牌方法，前缀改用 `--linotes-*`（或保持 `--liblog-*`，**槽位 B，待定**）。
- Hugo 固定版本二进制随仓库提交，构建走同一分段编排；部署独立域名（备案另议）。

## 6. 页脚链接编辑接口（D2 落地）

- 复用现有「友情链接」数据（`content/friends/*.md` + 后台 friends CRUD），在**页脚**渲染为链接列表。
- 后台「友情链接」栏目支持：名称、网址（http/https 白名单）、简介、排序、启停、删除。
- 文案走 `strings.yaml`（`friends.*` / `footer.*`），禁止模板硬编码。

## 7. 里程碑与验收

| 阶段 | 交付 | 验收（可验证证据） |
| --- | --- | --- |
| **P1 Li&Blog 停用文章** | 移除导航/首页文章入口、taxonomy/RSS/search/archive、文章编辑器 | `make check` + `make build` 通过；公开站无文章/搜索/归档/标签入口；`make test` 绿 |
| **P2 Li&Notes 建站** | 新项目骨架 + 文章迁入 + 主题/后台裁剪 | 新站构建通过；40+ 篇文章全部渲染；搜索/归档/标签/RSS 正常 |
| **P3 页脚链接** | 页脚链接列表 + 后台增删改 | 后台新增链接 → 页脚即时展示（构建后）；外链白名单校验 |
| **P4 收尾** | 删除 Li&Blog 残留 posts、更新 MASTER/BRAND/记忆库 | 内容覆盖审计表无缺口；两站各自验证通过 |

## 8. 待拍板槽位

- **槽位 A**：新项目名/路径（默认 `Li&Notes` @ `~/Desktop/Li&ProJect/Li&Notes`，仓库 `Lzf07123/Li-Notes`）。
- **槽位 B**：新项目令牌前缀（默认沿用 `--liblog-*`，避免重复劳动）。
- **槽位 C**：`resources.md` 是否保留（个人展示语境下可留作「资源/链接」，与页脚友链可合并，二选一）。
- **槽位 D**：文章迁移时序——默认「P1 先停用渲染保留文件 → P2 建新站迁入 → P4 删除本站 posts」，全程无内容丢失。

## 9. 变更记录

- 2026-10-20 v0.1：初稿，确立「拆文章、专注展示」方向与 A 方案。
