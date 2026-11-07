# Jetson 部署通道：本地验证记录

日期：2026-11-07（Asia/Shanghai）。本记录验证仓库内的部署实现，**不是 GitHub 线上运行结果，也不是 Jetson 首次上线或硬件验收**。

## 验证环境与范围

- 部署机制使用 Python 标准库，复审后在 macOS / Python 3.15 和 Debian Bookworm / Python 3.11 容器各完成 53 项测试，包括原生 `visudo` 解析。两端均将 `ResourceWarning` 视为错误；Python 3.6 兼容性由现有 AST 回归检查，不代表已在 JetPack 的 Python 上运行。
- Linux 后端测试启用 `RUN_CAMERA_INTEROP=1`，覆盖现有独立 ONVIF/FFmpeg/GStreamer 互操作及 PTY/pyserial；没有连接实体摄像头或电机。
- 前端使用 Node `22.22.0`。提交前在基准提交 `909f3a7d59427b2fc5eed7c379022c3694eef4d1` 加当前变更的隔离副本重新验证单元测试、生产构建和完整浏览器回归。发现遗留静态包与 28 张窄屏 settings 截图含过期的 PD42S1 协议提示后，先保留原文件副本，再按当前源码重建 dist、校正截图；重建后的 dist 与既有跟踪资产一致，未改前端业务源码。
- 所有脚本测试使用临时目录、模拟 systemd/依赖安装及本地 HTTP fixture；断线测试实际终止上传父进程，再确认独立 worker 完成事务。没有运行真实 bootstrap `--apply` 或目标发布入口。

## 实测结果

| 检查 | 结果 |
| --- | --- |
| `python3 -W error::ResourceWarning -m unittest discover -s scripts/tests -q` | macOS 53 项通过 |
| Linux 部署回归（同上命令） | 53 项通过 |
| 后端 `pytest tests -o addopts= -q -p no:cacheprovider` | 174 项通过，含独立协议互操作 |
| 前端 `npm test` | 5 个文件、126 项通过 |
| 前端 `npm run build` | TypeScript / Vite 生产构建通过 |
| 隔离副本 `git diff --exit-code -- dist` | 通过，构建与已跟踪设备资产一致 |
| `npm run test:e2e`（不设 `CYBERVISUAL_CAPTURE_ONLY`） | 提交前完整 236 项通过，包含实际截图基线对比、布局/交互、axe 与原生 200% 缩放检查 |
| `actionlint .github/workflows/network-camera.yml` | 通过 |
| `shellcheck` 两个新 Bash 入口 | 通过 |
| `bash -n` 新入口和现有 install/run 脚本 | 通过 |
| `git diff --check` | 通过 |
| 目标 Python 兼容性 | 三个辅助程序通过 Python 3.6 语法解析；尚未在目标 Python/JetPack 执行安装 |
| 固定 Tailscale `1.104.5` amd64 包 | 官方 stable 下载端点返回 HTTP 200，仅检查可用性，未接入 tailnet |

28 张 settings 基线只同步当前源码中的云台说明，已核对差异区域为该段文案，并在更新后重新运行完整浏览器套件；不能将更新截图后的通过结果单独视为 ORBIT 官方设计合规或实体云台验收。

## 部署需求对照

| 需求 | 实现和证据 |
| --- | --- |
| main / 原仓库 / 开关 / 全部 CI 门禁 | job 条件、二次授权函数、门禁单测及工作流静态检查 |
| 手动运行不能绕过 CI | 同一 workflow 的 `workflow_dispatch`，deploy needs 三个检查 job |
| 过期任务不回退新 main | job 获得并发执行权后检查 main，传输前再次检查；查询失败关闭 |
| OIDC 最小信任 | subject + repository/workflow_ref/ref/environment 精确 claim；模板仅 `auth_keys` / CI 标签 |
| 最小网络/SSH | 策略片段只授权 CI 标签到目标 TCP 22，SSH `accept` 仅部署账户；不自动改现有策略 |
| 准备默认只检查、显式且可重复应用 | 沙箱检查文件快照无变化，连续两次 apply 的设置/unit 一致，不调用 start/restart |
| 迁移保护 | 未明确确认、未知 launcher/drop-in/用户/硬件覆盖、路径/源码/venv 不一致即停止；root-only 备份和旧版基线 |
| 包与提交绑定 | 完整 SHA、归档摘要、逐文件清单；打包器拒绝工作树未验证内容 |
| 归档安全 | 路径穿越、绝对路径、链接、特殊项、重复项、越界配置/模型和校验损坏测试 |
| 每版独立 venv | 只在新版本目录安装，目标 Python markers / system-site-packages；依赖失败不重启旧服务 |
| 幂等和并发 | 同 SHA 同内容不重复安装/重启，同 SHA 不同内容拒绝；本地文件锁防止并发切换 |
| SSH/Runner 断开继续执行 | systemd-run 固定 worker；实际独立子进程在上传父进程被 kill 后完成 |
| 固定业务验收 | 首页/JS/CSS 内容一致、API、真实 camera/model 标记、帧推进至少两次；慢响应不能拖延成功判定期限 |
| 自动恢复 | 摄像头不就绪回滚、恢复结果检查、回滚失败单独报告、首次失败停止新服务 |
| 持久数据不被覆盖 | 配置、环境、模型、UUID、PTZ 预置位、快照在成功和回滚后内容不变 |
| 保留三个成功版本 | 保留最近三版，保护 current/previous；清理失败不撤销已健康版本 |
| 温度与诊断 | 温度独立于业务失败报告，状态只导出白名单；工作流中断明确 unknown，不声称 worker 已取消 |
| 旧版本同 SHA 首次 CI 发布 | 逐文件完全一致才识别为同版，保留旧 venv；不同内容拒绝 |

## 代码复审与修复

本轮审查覆盖工作流、OIDC/SSH 策略、固定提权入口、发布器、准备/迁移工具、业务验收及其测试。先增加或强化回归并确认失败，再修复以下问题：

| 优先级 | 已复现问题 | 修复与回归 |
| --- | --- | --- |
| P1 | `systemd-run` 默认等待 oneshot 启动完成；长时间依赖安装/验收会触发调用方 30 秒超时，后台任务却可能仍在执行，导致发布误报失败 | 显式使用 `--no-block`，仅等待 systemd 接受事务；回归要求该参数，而不只是禁止 `--wait` |
| P1 | 首次准备、部署器升级或旧版本迁移在写设置时失败，会遗留新 unit/提权入口/`current`，后续重试被误判为未知安装或保留半升级状态 | 对受管文件、链接及版本状态建立恢复事务；分别注入首次安装、升级及迁移失败，验证恢复后可重试且旧文件不变 |
| P2 | 准备器只持执行锁，普通发布仍能通过提交锁创建请求并在替换部署器时启动 worker | 准备期间同时持有提交锁与执行锁；安装回调使用独立文件描述符验证提交锁确实排他 |
| P2 | 原 HTTP 验收只在读取响应正文时检查总期限；持续缓慢发送响应头或 chunk 头可不断延长单次请求 | 在底层每次 socket 读取前重算剩余总时间，覆盖状态行、响应头、chunk 元数据和正文；真实本地 HTTP fixture 验证慢头不会突破验收期限 |
| P2（测试） | 归档夹具写入当前 gzip 时间戳，同一内容跨秒生成不同摘要，Linux 偶发把重复发布误判为不同包 | 与生产打包器一致固定 `mtime=0`；重复发布测试显式相隔 60 秒构造归档，确认不重装、不重启 |

新增 6 项回归，并强化原有 systemd 启动及重复发布两项测试。准备失败的自动恢复只覆盖捕获到的异常，不代表断电/强制终止恢复已获硬件验收；受限账号和 root-only 备份会保留，不随恢复删除。

## 打包校验样本

使用干净基准提交作为校验输入，而不是为未提交的工作区内容伪造版本：

```text
commit:         909f3a7d59427b2fc5eed7c379022c3694eef4d1
payload files:  43 (plus release-manifest.json)
archive bytes:  278472
archive SHA256: f35bae0d9ea83656c0213557a55d3b82877e3a4beef7356d2506015b5684fb4f
```

发布清单仅包含后端源码/requirements、前端 dist/字体许可及启动脚本。实际 Actions 包使用该次 CI 的 `GITHUB_SHA`，不是以上样本 SHA；打包校验通过不等于已传输到设备。

## 环境限制与现有警告

- 初版验证时全新 Dockerfile 重建未完成：本机 Docker credential helper 无法交互读取钥匙串；改用独立空 Docker 配置后，Docker Hub 连接超时。没有改动用户的 Docker 配置或钥匙串。本轮继续使用现有 Debian 协议测试镜像及只读源码挂载，在临时容器补齐仓库声明的 `pyserial==3.5`、git/sudo；apt HTTP 下载停滞后仅在临时容器使用 HTTPS 源，容器结束即删除。
- 前端现有依赖的 `npm ci` 报告 6 项 audit 问题（3 moderate、3 high），生产构建有超过 500 kB chunk 提示。本次未做无关依赖升级或代码分包重构；构建和测试退出码均为成功。
- 没有配置 GitHub Environment/Repository variables、创建 federated identity、合并 tailnet 策略、登录 Jetson 或触发真实部署。实际 GitHub CI/OIDC 接入和 ARM64/JetPack 依赖安装仍须管理员首次发布验证。
- 实体摄像头持续出帧、真实 TensorRT 模型、温度、重启恢复及实体云台均未验收。请按 [部署指南](jetson-deploy.md) 完成一次性准备后，再从 main 手动开启首次验证。
