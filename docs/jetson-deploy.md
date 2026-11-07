# Jetson Nano：Tailscale OIDC 自动部署

## 范围与默认状态

这是完整 Web 控制台和后端的发布通道，不是摄像头/云台初始化工具。仓库只交付工作流、准备工具和发布机制；**不会修改实际 tailnet 策略、创建远端账户或执行首次上线**。

- `.github/workflows/network-camera.yml` 的前后端 CI、浏览器回归、已跟踪 dist 一致性检查和 `deployment-tests` 全部成功后，才可能运行部署。
- 仅原仓库 `Arasaka-Academy/CyberVisual` 的 `main` push 和 `workflow_dispatch` 可以部署；PR、fork、其他分支和失败/跳过的 CI 均被拒绝。手动运行不能跳过 CI。
- 仓库变量 `JETSON_DEPLOY_ENABLED` **未设置或不等于字符串 `true` 时关闭**。首次准备结束前不要开启。
- 发布不改后端协议、摄像头源、检测器选择、云台行为或 3D 教学站；不发送 PTZ、标定、快照或配置写入请求。
- 当前服务继续以原有 root 权限运行，以免改变 JetPack/串口权限。拥有 main 发布权限者因此是受信任的设备代码发布者；受限 sudo 不是对恶意应用代码的沙箱。

## 1. 管理员配置 GitHub 和 OIDC 信任

在本仓库创建 **Environment `jetson-production`**，限制可部署分支为 `main`。建议设置 required reviewers、禁止自行审批，并保护 main 和 `.github/workflows/` 的代码审查。不要把下面的信任扩展到整个组织、任意分支或任意工作流。

在 Tailscale 管理台创建 **OpenID Connect federated identity**，按 `deploy/jetson/tailscale-oidc.json` 填写：

| 字段 | 必须匹配 |
| --- | --- |
| Issuer | `https://token.actions.githubusercontent.com` |
| Subject | `repo:Arasaka-Academy/CyberVisual:environment:jetson-production` |
| Custom claim `repository` | `Arasaka-Academy/CyberVisual` |
| Custom claim `workflow_ref` | `Arasaka-Academy/CyberVisual/.github/workflows/network-camera.yml@refs/heads/main` |
| Custom claim `ref` | `refs/heads/main` |
| Custom claim `environment` | `jetson-production` |
| Scope | **仅可写 `auth_keys`** |
| Tags | **仅 `tag:cybervisual-ci`** |

Environment 形式的默认 `sub` **不包含分支和工作流**，因此不能只设置 subject；四个 custom claim 限制必须同时存在。无需更改仓库的 OIDC subject 模板，也不要授予设备管理、ACL、DNS、用户或其他 tailnet 管理 scope。JSON 是配置对照，不是整体覆盖现有身份的 API 请求。

把新身份显示的 **Client ID 和 Audience** 设置为该 GitHub Environment 的变量（不是长期密钥）：

| 变量 | 值 |
| --- | --- |
| `TS_OIDC_CLIENT_ID` | 此 federated identity 的 Client ID |
| `TS_OIDC_AUDIENCE` | 管理台生成的 Audience，精确复制 |
| `JETSON_HOST` | 默认 `nvidia-jetson-nano.civet-beta.ts.net`；可设置为目标 MagicDNS 名称 |
| `JETSON_HTTP_PORT` | 默认 `8000`；必须与设备持久环境中的端口一致 |

`JETSON_DEPLOY_ENABLED` 放在 **Repository variables**，而不是只放在 Environment 中，因为 job 级门禁在获取 Environment 变量之前求值。先保持关闭。

部署 job 只有 `contents: read` 和 `id-token: write`；不使用 Tailscale auth key、OAuth secret 或 SSH 私钥。Tailscale Action 固定为 v4.4.0 的提交 `064b10558093f38325e838ddea35486bdc6b1d5c`，Runner 客户端固定 `1.104.5`，通过 `oauth-client-id`、`audience`、`tags` 接入，使用 Action 的临时节点和结束清理机制。

## 2. 合并最小 tailnet 规则

由现有 tailnet 管理员审查并**合并** `deploy/jetson/tailscale-policy-fragment.json` 中的项目，保留其他标签、管理员 SSH 和现有业务规则。不要用该片段替换整份策略。

- 将目标 Jetson 标记为 `tag:cybervisual-jetson`；确认标签仍指向预期设备，而不只是名称相似的机器。
- 网络授权仅从 `tag:cybervisual-ci` 到目标标签的 **TCP 22**。不开放 Runner 对 HTTP 8000、RTSP 或其他主机的访问；业务验收在 Jetson 本机执行。
- Tailscale SSH 规则为 `accept`，只允许目标 Linux 账户 `cybervisual-deploy`，不允许 `root`，不使用要求人工 reauth 的 `check` 模式。
- 规则是累加的：必须检查现有 `*`、`autogroup:tagged`、宽泛 grants/ACL 或 SSH 规则是否已经授予 CI 更大权限。片段本身无法否定其他规则。用管理台策略预览确认 CI 不能访问目标 8000、其他设备或以 root 登录；同时确认管理员原有访问仍然有效。
- 管理员在 Jetson 本机执行 `sudo tailscale set --ssh`，确认 tailscaled 正常且该版本支持 Tailscale SSH。准备脚本只检查，不自动启用或改策略。

## 3. 设备准备：先检查，后显式应用

在 Jetson 使用管理员自己的可信登录通道放置本仓库的已审核版本。不要通过新 CI 身份完成首次准备。运行：

```bash
bash scripts/bootstrap_jetson_deploy.sh --runtime-env /etc/cybervisual/camera.env
```

默认只读取检查，不创建账户/目录，不安装文件，不启动服务。部分 root-only 环境文件和 Tailscale 偏好需要用管理员 `sudo` 读取，**sudo 不等于 `--apply`**。

检查包括 ARM64、`/etc/nv_tegra_release`、目标 Python >=3.6、venv/ensurepip、JetPack OpenCV 的 GStreamer 支持、GStreamer 工具、运行中的 systemd/tailscaled、Tailscale SSH、git、sudo/visudo。缺失即停止，报告准备步骤；不会升级 JetPack、CUDA、系统 Python，不使用 `install_jetson.sh` 做普通发布。原安装脚本会启服务或尝试构建前端，不能当作本通道的发布命令。

### 全新安装

由管理员准备持久目录、真实模型和可用硬件。`deploy/jetson/camera.env.example` 仅供**全新安装**参考，其中 `model.engine` 是占位路径，不提供模型。按实际模型修改，并在目标 JetPack 上验证模型可用。

持久文件必须已经存在、使用绝对路径，不得位于 `releases/` 或 `current/` 下：

| 环境项 | 用途 |
| --- | --- |
| `CYBERVISUAL_CONFIG` | 原有可写 JSON 配置，包括凭据及硬件参数 |
| `CYBERVISUAL_MODEL_PATH` | 目标机可用的真实 engine/ONNX 模型 |
| `CYBERVISUAL_STATE_DIR` | 原有设备 UUID、预置位和其他设备状态 |
| `CYBERVISUAL_CAPTURE_DIR` | 原有快照目录 |
| `CYBERVISUAL_PORT` | 与 GitHub `JETSON_HTTP_PORT` 相同 |

不要覆盖已经存在的 `camera.env`、配置、设备状态或模型。环境文件应 root 所有、`0600`；配置/状态/模型不得允许部署账户写入。只允许 `CYBERVISUAL_*` 环境项，不支持 shell `export`/执行、重复键、多行续写；不要设置 `PYTHON`、`PYTHONPATH`、`CYBERVISUAL_FRONTEND_DIST`。带空格的凭据用双引号包裹，`$` 按字面量保留，不进行 shell 展开。路径不能含空白或 systemd `%` 展开。

准备完成后再次检查，再显式应用：

```bash
sudo bash scripts/bootstrap_jetson_deploy.sh --runtime-env /etc/cybervisual/camera.env
sudo bash scripts/bootstrap_jetson_deploy.sh --apply --runtime-env /etc/cybervisual/camera.env
```

应用创建并锁定专用系统账户的密码；该账户只有自己的普通 shell/home，不加入 sudo 等附加组。它可以通过受限 Tailscale SSH 登录，**不能通过 sudo 执行任意 shell、systemctl、pip、文件复制或内部 worker**。

固定入口 `/usr/local/sbin/cybervisual-deploy`、辅助程序 `/usr/local/lib/cybervisual-deploy/jetson_deploy.py`、sudoers 和父目录由 root 所有且不可被部署账户修改。sudo 只允许该入口，入口清空环境并验证命令/参数。若已有目录为组可写、账户已存在但身份不符，停止由管理员复核，不偷偷接管。

准备脚本安装版本化 unit、执行 daemon-reload/enable，但**不 start/restart 服务**。全新安装尚无 `current`，必须完成首次成功发布才能运行；在此之前不要以重启设备代替首次验证。重复 `--apply` 可以更新受信任的部署器，保留运行配置；有执行中/待处理事务、配置路径或受管 unit 异常变化时会停止。普通发布包不包含部署器，不能自动升级提权入口或 sudo 规则。

准备过程同时持有提交锁与发布锁，防止普通发布在部署器替换期间创建新事务。捕获到准备异常时，恢复原固定入口、sudo 规则、unit、部署设置、`current` 和版本状态，移除本次尚未完成的迁移基线，然后重新加载 systemd；不会重启现有业务。备份和已创建的受限账号保留，问题解决后可以重试。若报 `preparation_rollback_failed`，说明至少一项恢复失败，必须先由管理员核对 root-only 备份与实际文件，不能直接开启 CI。此恢复机制不等同于断电或强制终止后的恢复验收。

管理员升级部署器时，应使用另行取得并审核的源码；不要在仍承载持久配置/旧 venv 的原工作目录用覆盖式同步或 git 操作替代部署。

### 旧安装迁移：必须显式确认

旧服务存在但没有受管部署设置时，默认拒绝迁移。先核对 `systemctl cat cybervisual.service`、原工作目录、Python/venv、所有 Environment/EnvironmentFile、JSON 配置、模型、UUID/预置位和快照目录。

把原服务的 **全部有效 `CYBERVISUAL_*` 参数**保留在准备使用的环境文件中。把配置/模型/状态/快照映射为**同一个真实原路径**的绝对路径；原模型目录还会作为各版本的 `models` 链接，保留 auto 检测器原有 fallback 访问。不移动、不重新初始化设备身份，不修改配置内容。原 unit 中的 `PYTHONPATH` 和前端 dist 路径由版本化 unit 管理，不写入环境文件。

```bash
sudo bash scripts/bootstrap_jetson_deploy.sh \
  --runtime-env /etc/cybervisual/camera.env \
  --migrate-from /opt/cybervisual \
  --legacy-sha <原安装完整40位Git提交> --confirm-migration
```

检查无误后在同一命令增加 `--apply`。脚本先备份原服务定义、相关环境文件及配置到 `/var/lib/cybervisual-deploy/backups/<时间-标识>/`（root-only），验证原服务真实业务就绪，再复制经确认的旧源码/dist 并链接原 venv，建立可回滚基线。原 venv 不安装依赖、不移动；模型与运行数据保留原路径。发布前的旧服务进程不会被迁移命令重启。

**必须停止人工处理的情况**：不明启动器、drop-in、自定义 ExecStartPre、非 root 服务用户、相对/不明运行数据路径、未保留的硬件环境、脏/不一致的代码或 dist、无法确认的 Git SHA/venv、原业务不可恢复。脚本不猜测迁移，也不自动改 User 或硬件参数。不要用删除旧服务/部署设置的方式绕过检查。若需要退回旧管理方式，管理员可用 root-only 备份恢复原 unit/environment/config，daemon-reload 后再评估是否重启；原代码、venv 和数据没有被删除。

## 4. 首次 main 手动验证，再启用日常自动部署

确认设备已准备、最小策略生效、Environment 信任和变量正确后，将 Repository variable `JETSON_DEPLOY_ENABLED` 设为 `true`，然后在 Actions 对 **main** 手动运行 `Camera protocol and dashboard tests`。命令行等价操作：

```bash
gh workflow run network-camera.yml --ref main
```

该操作真实发布到设备，**仅由管理员在准备完成后执行**。本次代码交付不会代为触发。首次运行仍先完成全部前后端和部署测试，并遵守 Environment 审批。

部署组 `cybervisual-jetson-production` 串行运行且 `cancel-in-progress: false`。取得执行权后查询远端最新 main；如果本次 CI 的完整 SHA 已过期则跳过。获取 payload、进入 tailnet 后，提交前再次查询 main。无法确认最新 main 时失败关闭。并发队列不保证 FIFO，安全性来自每次重新检查，不来自任务顺序。

在 Dashboard job 完成构建、浏览器回归和 dist 一致性检查后，才按本次完整 SHA 生成只读发布包及 SHA256 文件。打包器要求 payload 与该 Git commit 一致，并只选择：

- `backend/cybervisual/**/*.py` 和 `backend/requirements.txt`；
- 已验证且跟踪的 `frontend/dist` 静态文件、字体及其许可证；
- `scripts/run_backend.sh` 和逐文件 SHA256 清单 `release-manifest.json`。

不包含 backend 配置示例、venv、模型、凭据、摄像头画面、快照、设备状态、Git 数据或部署器。部署下载**同一次 workflow run**的不可变 artifact，不重新从分支打包，不在 Nano 构建前端。

## 5. 本地发布事务、验收与自动恢复

Runner 使用 `tailscale ssh cybervisual-deploy@<host> sudo -n /usr/local/sbin/cybervisual-deploy ...`，包通过 stdin 传输，不依赖 scp/SFTP 或 SSH 密钥。远端先校验归档 SHA256、完整 commit、清单和所有文件内容；拒绝路径穿越、绝对路径、重复项、链接、特殊文件、配置/模型等越界内容及超限包。

验证后的请求由 root 写入私有 spool，再通过 **systemd-run --no-block 本地 oneshot 事务**执行；仅等待 systemd 接受任务，不等待整个 oneshot 完成，返回 job ID 后 SSH/Runner 即可断开。事务不依赖 SSH shell/网络连接继续运行。文件锁覆盖准备、切换、验收和恢复，另一事务遇锁失败，不并发改变 current。

```
/opt/cybervisual/releases/<完整SHA>/   每个版本自己的源码、dist、.venv
/opt/cybervisual/current              原子切换的链接
/etc/cybervisual/deploy.json          root-only 部署设置，不随普通发布改变
/var/lib/cybervisual-deploy/jobs/     私有请求与脱敏状态
```

目标 Python 使用每个版本自己的 `venv --system-site-packages`，按 requirements 的 Python markers 安装兼容依赖，保留 JetPack 原生 OpenCV/TensorRT/CUDA。不会升级系统 Python、复用 Runner 环境、在旧 venv 原地安装或自动改模型。依赖安装失败时旧链接和服务完全不动。成功发布同一字节包的同一 SHA 会重新验收，但不重装依赖/重启当前版本；同一 SHA 换包则拒绝。

迁移基线与第一次 CI 发布恰好是同一 SHA 时，只有逐文件清单完全一致才识别为同版本，记录首次包摘要而不改旧 venv；源码或 dist 有任何差异仍然拒绝。

所有准备成功后才切换 `current` 并重启。**从重启开始 180 秒内**必须同时满足：

1. `cybervisual.service` active；
2. 首页与本版本 dist 一致，所引用 JS/CSS 都可读取且内容一致；
3. `/healthz` 和 `/api/status` 正常；
4. `camera.connected == true`、source 为真实 `camera`；
5. `model.loaded == true`，backend 为 `opencv` 或 `tensorrt`，明确拒绝 mock；
6. `last_frame_ts` 在轮询中至少前进两次。

仅 HTTP 200 或 `/healthz.ok` 不代表恢复。温度告警单独记录，不伪装为发布失败或擅自降级。模型缺失时原有 auto 可能选择 mock，但该状态**不能通过发布验收**。

失败自动恢复旧链接（及其独立 venv），重启并以同一业务条件验收旧版本。`rollback: succeeded` 仍然是**本次发布失败**；`rollback: failed` / `error: rollback_failed` 单独标示恢复失败。首次无旧版时停止新服务、移除失败 current，保留诊断。没有任何自动 synthetic/mock 切换或云台动作。

保留最近三个成功版本，并额外保护当前/前一版本与回滚目标；失败版本保留用于管理员诊断。清理失败报告 maintenance warning，不撤销已恢复的业务。不要手动删除 current、受保护基线、旧 venv 或独立数据目录。

## 6. 状态、手动回滚与关闭

在设备管理员 shell 或受限部署账户中：

```bash
sudo /usr/local/sbin/cybervisual-deploy status
sudo /usr/local/sbin/cybervisual-deploy status <job-id或完整commit>
sudo /usr/local/sbin/cybervisual-deploy rollback
sudo /usr/local/sbin/cybervisual-deploy rollback <已成功且仍保留的完整commit>
```

rollback 返回排队 job ID，再用 status 观察，终态为 `succeeded` 或 `failed`。不接受路径、任意 systemd 服务、Python 命令或 shell 参数；内部 `_apply` 只能由 root 管理的 systemd worker 入口执行。未成功/已删除/校验损坏的版本不能作为手动回滚目标。

`status` 的 `http_port` 必须与 GitHub Environment 端口一致，不一致时拒绝发布，避免对另一个本地服务误验收。Runner 超时或网络持续中断时，结果可能为 `unknown / client_timeout_worker_not_cancelled`；**先查询设备状态，不能据此认为已回滚或强制杀 worker**。恢复连接后以完整 commit 查询可以找回丢失的 receipt。

关闭自动部署：删除 Repository variable `JETSON_DEPLOY_ENABLED` 或改为 `false`，不改当前服务。必要时管理员撤销 federated identity/CI grants。已启动的本地事务仍应完成验收或回滚；不要通过取消 Action 代替设备事务恢复。

## 7. 诊断与验证边界

本次实现的命令、计数、隔离方式和未验证事项见 [本地验证记录](jetson-deploy-validation.md)。

Actions Summary 和 `jetson-deployment-<sha>` artifact 只记录目标、提交、前后版本、状态、布尔业务检查、帧推进计数、温度/维护告警和回滚结果，保留 **14 天**。每个 job 只在收尾写一次 Summary。OIDC/传输之前失败也留下阶段失败摘要，前后版本不可知时明确为空。

不上传环境文件、原配置、模型、原始 API 状态、journal、摄像头画面或备份。依赖安装输出不回传，错误只用固定错误码。原备份始终留在设备 root-only 目录；管理员需要详细 journal 时在设备本机按凭据保护要求读取，不能直接作为 Actions artifact 上传。

本地/CI 验证命令：

```bash
python3 -m unittest discover -s scripts/tests -v
bash -n scripts/bootstrap_jetson_deploy.sh scripts/deploy_jetson.sh
shellcheck scripts/bootstrap_jetson_deploy.sh scripts/deploy_jetson.sh
actionlint .github/workflows/network-camera.yml
```

隔离测试覆盖门禁/失败 CI/过期提交、受限身份配置、打包与校验、危险归档、重复发布、文件锁、安装失败不扰旧服务、业务不就绪/恢复失败、首发失败、持久数据保留、脱离上传父进程的 worker、只检查及重复准备。前后端现有测试、独立协议互操作、浏览器矩阵和 dist 检查保持不变。

**模拟系统和本地 HTTP 只能验证部署机制**。真正上线仍需管理员完成：OIDC/Tailscale SSH 实际连通、目标 Python 依赖安装、摄像头持续出帧、真实模型/TensorRT、温度与设备重启、必要的实体云台独立验收。没有这些证据不得声称 Jetson 硬件验收通过。

### 官方依据

- Tailscale 固定 Action：`https://github.com/tailscale/github-action/tree/064b10558093f38325e838ddea35486bdc6b1d5c`
- Workload identity federation：`https://tailscale.com/kb/1581/workload-identity-federation`
- Tailscale SSH：`https://tailscale.com/kb/1193/tailscale-ssh`
- GitHub concurrency：`https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency`
