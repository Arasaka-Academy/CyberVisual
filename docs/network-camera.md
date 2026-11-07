# CyberVisual 网络摄像头：ONVIF + RTSP

每个 CyberVisual 进程管理一个物理摄像头，未来由 CyberOS 作为客户端管理。
首版提供两路共享编码的 H.264、AI 状态事件、WS-Discovery 和模拟云台。
ONVIF 管理与取流服务跟随现有服务启动、退出和恢复。旧配置自动补齐默认值，新增功能默认关闭。

## 1. 启用与连接

Jetson 基线为 JetPack 4.6 / L4T R32、Python 3.6、GStreamer 1.14。
运行 `scripts/install_jetson.sh` 补齐系统依赖；虚拟环境必须保留
`--system-site-packages`，以便导入 GI、OpenCV 和 JetPack 的编码器。

默认 systemd 单元读取可选的 `/etc/cybervisual/camera.env`。用
`sudo install -d -m 700 /etc/cybervisual` 创建目录，再用 `sudoedit` 创建该文件：

```ini
CYBERVISUAL_NETWORK_CAMERA=1
CYBERVISUAL_ONVIF_USERNAME=camera
CYBERVISUAL_ONVIF_PASSWORD=replace-with-a-unique-password
CYBERVISUAL_ADVERTISE_HOST=192.168.1.50
CYBERVISUAL_ENCODER=auto
CYBERVISUAL_PTZ_DRIVER=disabled
```

将地址和密码替换成实际部署值，然后执行：

```bash
sudo chmod 600 /etc/cybervisual/camera.env
sudo systemctl daemon-reload
sudo systemctl restart cybervisual
sudo journalctl -u cybervisual -f
```

凭据仅从进程环境读取，不写入 JSON 配置、配置 API 或连接地址。改密后需重启服务。
UUID 保存在 `/var/lib/cybervisual/device-id`，预置位保存在同目录的
`ptz-presets.json`；开发环境默认使用工作目录下的 `.cybervisual/`。
通过 `CYBERVISUAL_STATE_DIR` 指定其他持久目录，迁移设备时保留该目录。

| 用途 | 默认端口／地址 | 认证 |
| --- | --- | --- |
| ONVIF Device | TCP 8000，`/onvif/device_service` | WS-Security UsernameToken Digest；也接受 HTTP Digest |
| Media v1 | `/onvif/media_service` | 同上 |
| Media v2 | `/onvif/media2_service` | 同上 |
| Events | `/onvif/events_service` | 同上 |
| PTZ | `/onvif/ptz_service`，仅驱动启用时公布 | 同上 |
| 原始 H.264 | TCP 8554，`rtsp://192.168.1.50:8554/raw` | RTSP Digest |
| 标注 H.264 | TCP 8554，`rtsp://192.168.1.50:8554/annotated` | RTSP Digest |
| ONVIF 快照 | `/onvif/snapshot/raw`、`/onvif/snapshot/annotated` | HTTP Digest |
| WS-Discovery | UDP 3702，组播 `239.255.255.250` | 局域网发现 |

RTSP 同时支持 RTP/UDP 和 RTP over RTSP/TCP。UDP 传输还需要允许会话协商的
RTP/RTCP 动态 UDP 端口；跨网段或有防火墙时可优先选择 TCP。
HTTP 端口由 `CYBERVISUAL_PORT` 指定，RTSP 端口由 `CYBERVISUAL_RTSP_PORT`
或本地 JSON 配置指定。

`GetSystemDateAndTime` 允许未认证查询，供客户端校准 UsernameToken 的时间差。
其余 SOAP 请求需要认证，时间偏差容许 ±300 秒，重复 UsernameToken 会被拒绝。
快照 Digest 使用有时限的 nonce 和递增计数，拒绝重放。

这些认证覆盖新增协议接口。现有面板、`/stream.mjpg`、REST 配置／快照接口沿用
原有访问方式，部署时应放在受信任管理网内；本轮未增加整个面板的账号系统。

## 2. 配置与运行状态

`backend/config.example.json` 的新增部分如下，全部字段均为非秘密值：

```json
{
  "network_camera": {
    "enabled": false,
    "advertise_host": "",
    "discovery_interface": "",
    "discovery_enabled": true,
    "rtsp_port": 8554,
    "encoder": "auto",
    "raw_fps": 30,
    "annotated_fps": 15,
    "raw_bitrate_kbps": 2000,
    "annotated_bitrate_kbps": 1000,
    "ptz_driver": "disabled"
  }
}
```

`encoder` 为 `auto`、`jetson` 或 `software`。`auto` 优先选择
`nvvidconv + nvv4l2h264enc`，不可用时选 `x264enc`；指定 `jetson` 时，硬件
编码器不可用会明确报错，不静默切换。`software` 用于 Linux 开发与互通测试。
默认分辨率沿用采集配置，H.264 模式要求宽高为偶数；若摄像头不遵守请求尺寸，
RTSP 与 ONVIF 快照会缩放至配置尺寸。原始路上限 30 FPS，标注路上限 15 FPS，均不会
超过 `camera_fps`，标注路实际随推理完成速度更新。

每路媒体由一个共享 GStreamer factory 编码，首个客户端连接时建立管线。
多个客户端共享该路编码结果，原始与标注各自使用一条编码管线。
单槽原始帧缓冲和单槽标注帧缓冲限制积压；慢客户端丢弃旧帧，推理故障不阻塞采集。
ONVIF 快照只返回有效且最近 5 秒内的画面，无新画面时返回 503。
原有 MJPEG 预览和本地快照仍可显示故障占位图。

`advertise_host` 留空时按路由选择局域网 IPv4；多网卡部署可显式设置。
`discovery_interface` 用于指定加入组播的本机 IPv4，不能填网卡名称。
公布地址与组播接口可以分别指定；未单独指定接口时使用公布地址加入组播。
环境覆盖还支持 `CYBERVISUAL_DISCOVERY_INTERFACE`、
`CYBERVISUAL_DISCOVERY_ENABLED` 和 `CYBERVISUAL_PTZ_DRIVER`。

`PUT /api/config` 对 `network_camera` 进行嵌套合并与校验；协议、分辨率或
采集 FPS 改变时重建协议服务，已有客户端需要重连，PullPoint 需要重新订阅。
编码设置由本地配置维护，ONVIF 的写操作返回明确 Fault。

`GET /api/status` 的 `network_camera` 提供：

- `state`：`disabled`、`starting`、`running`、`degraded`、`error`、`stopped`。
- `credentials_configured`、持久 `device_uuid`、无凭据的 `onvif_url`。
- 实际 `encoder`；各 `profiles` 的 token、取流／快照地址、媒体管线 active、
  已推送帧数与最近错误。没有客户端时管线处于 idle，帧数为累计值。
- `discovery` 的运行或故障状态；`events` 的 online、person/vehicle 状态、订阅数与故障原因。
- `ptz` 的驱动、是否模拟、位置与移动状态，以及 `state`（disabled／running／unavailable）和 `last_error`。
  驱动未就绪时状态与健康接口继续响应，退出流程仍释放视频与事件资源。

缺少账号或 GI／编码器时，新增协议输出报告错误，现有面板继续运行。
WS-Discovery 无法加入接口时状态为 `degraded`，仍可手动填写 ONVIF 地址。

## 3. CyberOS 接入契约

1. 通过 WS-Discovery Probe／Resolve 或手动 Device XAddr 定位设备，用稳定 UUID
   作为设备身份。不要把 IP 地址作为持久身份。
2. 查询设备时间，使用同一设备账号建立 WSSE Digest 请求，再通过
   `GetServices` 获取各服务 XAddr。按返回能力决定是否显示云台控制。
3. Media v1 `GetProfiles` 返回固定 token `raw` 和 `annotated`。
   Media v2 使用 `GetProfiles(Type=["All"])` 取得完整配置；不传 Type 仅返回基本身份。
   两路的物理视频源均为 `camera0`，启用云台后共用 `ptz0`。
4. 对所需 Profile 调用 `GetStreamUri`，再用 Digest 认证连接 RTSP。
   地址不包含账号密码；客户端自行安全提供凭据。Media v1 可请求
   `Stream=RTP-Unicast`、`Transport.Protocol=RTSP`；Media v2 为
   `Protocol=RTSP` 或 `RtspUnicast`。最终 TCP／UDP 由 RTSP SETUP 协商。
5. 调用 `GetSnapshotUri` 并使用 HTTP Digest 请求对应图像。
6. 通过 `GetEventProperties` 识别下面的自定义主题，创建 PullPoint 并使用返回的
   SubscriptionReference.Address 拉取、续订、同步、取消。不要把这些操作发到 Device 服务。
7. 重连后重新获取能力与当前状态。短暂断流可能在同一 RTSP 会话内恢复；客户端仍应
   设置读超时并在无帧时重建会话。协议服务重启或设备重启后，重新创建订阅。

通道身份与地址：

| Profile token | Source token | Source configuration | Encoder configuration | 用途 |
| --- | --- | --- | --- | --- |
| `raw` | `camera0` | `raw-source` | `raw-encoder` | 原始图像与本地 AI 处理 |
| `annotated` | `camera0` | `annotated-source` | `annotated-encoder` | 检测标注预览 |

Profile token 和设备 UUID 跨重启稳定，订阅 token 为临时随机值。
本轮没有修改 CyberOS，也未宣称通过 ONVIF Profile 正式认证。

## 4. AI 状态事件

主题命名空间为 `urn:cybervisual:onvif:topics:1`，前缀示例为 `cv`。
`GetEventProperties` 公布完整主题树、消息字段和可用 topic dialect。

| 主题 | Category | State 含义 |
| --- | --- | --- |
| `cv:Analytics/PersonPresence` | `person` | true 人出现；false 人消失 |
| `cv:Analytics/VehiclePresence` | `vehicle` | true 车辆出现；false 车辆消失 |
| `cv:Device/AnalyticsOnline` | `analytics` | true 推理可用；false 视频／推理故障 |

车辆合并 `car`、`truck`、`bus`、`motorcycle`、`bicycle`。使用当前检测置信度和
`class_allowlist`，不绕过类别过滤。首次检出发送 true，持续存在不重复发送。
正常推理期间，距最近检出满 2 秒且当前未检出时发送 false。
视频／推理错误仅报告 AnalyticsOnline=false，不把故障当成目标消失；恢复后
重新给予 2 秒观察窗口。真实视频源在 `auto` 模式自动回落到 Mock 检测器时，
事件源保持 offline，禁止产生模拟告警和自动抓拍。显式 mock 或 synthetic 可用于测试。

通知消息示例：

```xml
<wsnt:NotificationMessage
    xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
    xmlns:tt="http://www.onvif.org/ver10/schema"
    xmlns:cv="urn:cybervisual:onvif:topics:1">
  <wsnt:Topic Dialect="http://docs.oasis-open.org/wsn/t-1/TopicExpression/Concrete">cv:Analytics/PersonPresence</wsnt:Topic>
  <wsnt:Message>
    <tt:Message UtcTime="2026-11-07T00:00:00.000000Z" PropertyOperation="Changed">
      <tt:Source><tt:SimpleItem Name="VideoSourceToken" Value="camera0"/></tt:Source>
      <tt:Data>
        <tt:SimpleItem Name="Category" Value="person"/>
        <tt:SimpleItem Name="State" Value="true"/>
      </tt:Data>
    </tt:Message>
  </wsnt:Message>
</wsnt:NotificationMessage>
```

每个新订阅先收到 `PropertyOperation=Initialized` 的当前状态；
`SetSynchronizationPoint` 清空该订阅积压并重新发送当前状态。
支持 Concrete／ONVIF ConcreteSet 的精确主题过滤和 `|` 联合，不支持内容条件、
通配符、历史查询、Push Notify 或 Seek。默认最多 16 个订阅，每订阅队列最多 256 条。
慢订阅溢出时丢弃积压并发送当前状态初始化；客户端不能将其视为完整历史事件日志。
到期订阅在事件发布、订阅访问和状态查询时清理。

默认订阅时长 60 秒，允许 1–3600 秒；`PullMessages` 的 Timeout 为 0–30 秒，
MessageLimit 为 1–64。客户端应在到期前续订，结束时取消；重启后旧订阅失效。
Zeep 对 TopicExpressionType 的混合文本解析有限制，读取主题时可检查接收的原始 XML；
Category 与 State 位于可正常读取的消息载荷中。

## 5. PTZ 适配与验收

生产默认 `ptz_driver=disabled`：GetServices／GetCapabilities／Profile 均不公布
PTZ 能力，调用 PTZ 返回 ActionNotSupported。显式配置 `simulated` 启用模拟云台，
状态清楚标记为 simulated；`pd42s1` 接入真实 RS485 驱动，需机械参数、实物使能反馈
配置和手动确认中心后才能移动，详见 [PD42S1 配置与协议依据](pd42s1.md)。

驱动接口位于 `backend/cybervisual/network_camera/ptz.py`，包括：

```python
class PTZDriver(object):
    def capabilities(self): pass
    def status(self): pass
    def absolute_move(self, pan, tilt): pass
    def relative_move(self, pan, tilt): pass
    def continuous_move(self, pan, tilt, timeout): pass
    def stop(self): pass
```

pan／tilt 位置、相对位移与连续速度均采用 ONVIF 标准化 `[-1, 1]`；真实适配器
负责映射机械角度、校准、限位、命令确认与物理停止看门狗。驱动未就绪时抛出
`PTZUnavailable`，ONVIF 返回 ServiceNotAvailable（503）；无效参数使用 `PTZError`。
归位与最多 32 个预置位由控制器统一处理，固定归位位置为 `(0, 0)`。
预置位持久化，模拟当前角度在重启后归零。

支持绝对、相对、连续移动与停止；连续移动默认 2 秒后停止，允许 0.1–2 秒。
超出输入范围返回 Fault；相对／连续移动到达限位时截断至边界。
没有 zoom 轴，不支持位置移动的自定义 Speed、修改固定归位、写 PTZ 配置或巡航。
真实驱动实现后必须独立验证机械方向、速度、校准和异常停止。

## 6. ONVIF 操作支持矩阵

所有未列为支持的操作返回 SOAP Fault，不接受静默写入或虚假成功。

| 服务 | 支持的操作 | 约束 |
| --- | --- | --- |
| Device | GetDeviceInformation、GetSystemDateAndTime、GetServices、GetServiceCapabilities、GetCapabilities、GetScopes、GetHostname | 时间只读；范围固定；不支持设置账号、网络、时钟、重启或固件 |
| Media v1 | GetServiceCapabilities、GetProfiles、GetProfile、GetVideoSources、GetVideoSourceConfigurations、GetVideoSourceConfiguration、GetVideoEncoderConfigurations、GetVideoEncoderConfiguration、GetCompatibleVideoSourceConfigurations、GetCompatibleVideoEncoderConfigurations、GetStreamUri、GetSnapshotUri | 固定双 Profile；编码配置只读；H.264 unicast |
| Media v2 | GetServiceCapabilities、GetProfiles、GetVideoSourceConfigurations、GetVideoEncoderConfigurations、GetStreamUri、GetSnapshotUri | Token／Type 查询；编码配置只读；无音频 |
| Events | GetServiceCapabilities、GetEventProperties、CreatePullPointSubscription | 精确 topic 过滤；订阅数量／生命周期受限 |
| PullPoint 地址 | PullMessages、SetSynchronizationPoint、Renew、Unsubscribe | Renew／Unsubscribe 使用 WS-Notification 命名空间 |
| PTZ | GetServiceCapabilities、GetNodes、GetNode、GetConfigurations、GetConfiguration、GetCompatibleConfigurations、GetConfigurationOptions、GetStatus、AbsoluteMove、RelativeMove、ContinuousMove、Stop、GotoHomePosition、GetPresets、SetPreset、GotoPreset、RemovePreset | 仅启用驱动时；PD42S1 运动前必须标定，连续租约最长 2 秒 |
| WS-Discovery | Hello、Bye、Probe／ProbeMatches、Resolve／ResolveMatches | IPv4 UDP 3702；固定 scope；RFC3986 scope 匹配 |

## 7. 可复现验证

常规回归：

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

真实 Linux GStreamer 软件编码环境，使用独立 `onvif-zeep`／Zeep 和 FFmpeg：

```bash
docker build -t cybervisual-camera-test -f backend/tests/integration/Dockerfile .
docker run --rm -e RUN_CAMERA_INTEROP=1 -v "$PWD:/workspace" cybervisual-camera-test
```

测试镜像允许用 `--build-arg BASE_IMAGE=...` 与 `--build-arg PIP_INDEX_URL=...`
选择可访问的公开镜像；运行测试不需要外网，Media2 官方 schema 使用保留许可证的本地快照。
测试覆盖双路实际解码、TCP／UDP、重连、同一路多客户端共享管线、Digest 快照、
Device／Media1／Media2 查询、事件订阅管理、模拟 PTZ、UDP Discovery 和退出资源释放。
原始／标注区别通过同源图像的确定性像素区域校验。CI 同时检查后端与前端构建。

在其他机器手动检查时，先使用 ONVIF 客户端添加 Device 地址和设备账号，再选择
raw／annotated Profile。可用 VLC 的网络串流界面填写 RTSP 地址并在提示时输入账号。
用 FFmpeg 命令行验证时请妥善处理凭据，避免将实际密码写进共享日志或文档。

### 本轮互通证据与设备边界

本次逐项结果见 [本地验收记录](network-camera-validation.md)。

Linux Debian bookworm、GStreamer 1.22、`x264enc`、FFmpeg 5.1、
onvif-zeep 0.2.12／Zeep 4.3.3，使用 320×240 synthetic 与显式 mock 验证协议行为。
这是软件编码与模拟输入的互通证据，不代表 Jetson 实测帧率、实际模型精度或电机动作。
未记录 ONVIF Device Manager、商业 NVR 或正式 ONVIF Profile 认证通过结果。

Jetson 设备验收仍需逐项记录：

1. `gst-inspect-1.0 nvv4l2h264enc` 与 `nvvidconv` 可用，运行状态的 encoder
   确认为 `nvv4l2h264enc`；只看到插件存在不足以证明实际编码成功。
2. 独立客户端同时解码两路视频并记录实际分辨率、帧率、延迟、CPU／GPU、温度。
3. 多客户端持续运行、断开／重连、摄像头拔插／模型故障、systemd 重启和设备重启恢复。
4. 重启后 UUID／Profile token／预置位稳定，原始视频不会被慢推理拖住。
5. 当前 PTZ 验收到模拟驱动；真实电机驱动确定后单独进行物理验收。


## 设备控制台与管理 API

控制台包含 `/#/overview`、`/#/monitor`、`/#/nvr`、`/#/events`、`/#/settings` 五个工作区。
桌面使用侧栏，窄屏使用五项底部导航。浏览器预览仍为标注 MJPEG；原始与标注 H.264
通过 NVR 接入页提供给外部客户端。录制与回放由外部 NVR／CyberOS 实现。

### 云台接口

`GET /api/ptz` 返回 `enabled`、`driver`、`state`、`simulated`、`position`、
`capabilities`、`presets`、`last_error`。禁用或驱动故障仍返回可读的 HTTP 200 状态；
`position` 不可用时为 `null`。标准化 pan／tilt 范围均为 `[-1, 1]`，没有机械角度或缩放轴。

`POST /api/ptz/command` 仅接受 JSON 对象。`action` 与字段如下：

| action | 参数 | 行为 |
| --- | --- | --- |
| `absolute_move` | `pan`, `tilt` | 绝对定位 |
| `relative_move` | `pan`, `tilt` | 相对步进，驱动实施限位 |
| `continuous_move` | `pan`, `tilt` | 速度向量；固定 2 秒超时，不接受客户端延长 |
| `stop` | 无 | 停止动作 |
| `home` | 无 | 回到 `(0, 0)` |
| `set_preset` | `name`，可选 `token` | 新增或覆盖当前位置，最多 32 个 |
| `goto_preset` | `token` | 调用预置位 |
| `remove_preset` | `token` | 删除预置位 |

成功返回更新后的完整云台状态；非法参数返回 HTTP 400 `{ "error": "..." }`，
禁用、驱动未就绪或持久化失败返回 HTTP 503。REST 与 ONVIF 复用同一控制器和持久化预置位。
页面按住方向时每 500ms 续动，松开、失焦、隐藏或离页会停止续动并请求停止；
断网无法确认停止时，驱动仍按最后一条已接收指令的 2 秒期限停止。重新连接不会自动恢复动作。

这些接口沿用现有管理 API 的可信管理网络访问范围，不接收或返回 ONVIF 设备账号。
协议账号、密码仍通过部署环境配置，不写入页面配置、地址或复制出的接入信息。

### 近期事件接口

`GET /api/events/recent` 返回：

```json
{
  "capacity": 200,
  "started_at": 1794000000.0,
  "status": {"online": true, "presence": {"person": true, "vehicle": false}, "last_error": null, "subscribers": 0},
  "events": [{"id": "stable-id", "topic": "Analytics/PersonPresence", "source": "camera0", "category": "person", "state": true, "frame_ts": 1794000001.0, "initialized": false}]
}
```

`frame_ts` 为 UTC Unix 秒，记录按产生顺序返回，页面按时间倒序显示，每页 20 条。
最近 200 条记录保存在进程内存，独立于浏览器和 ONVIF 订阅；超过上限淘汰最旧记录，重启后清空。
只有实际状态变化进入历史；订阅初始化、同步和清理不会制造新出现事件或清空历史。
`online=false` 表示分析源离线，`presence` 仅为最近已知状态，界面显示为未知，不据此判断消失。

### 配置和运行状态

NVR 页面只保存协议非敏感字段；系统设置分别保存采集、检测、快照和驱动字段。
草稿与已生效配置分离，切页保留草稿，写入超时会重新读取配置确认，不自动重复写入。
协议配置或驱动变化会重启协议输出并使既有订阅失效，客户端需要重新连接。
页面分别报告服务运行、发现和每路视频发布状态，不能据此推断外部 NVR 正在接收或录像。

可见页面每秒更新全局状态；监看页更新检测与云台，事件页每 2 秒读取近期记录。
读取请求不重叠；隐藏页面暂停轮询与 MJPEG。超过 5 秒未成功更新的数据标记过期，失败可单独重试。
普通局域网 HTTP 下若剪贴板不可用，复制操作会选中地址并提示手动复制。
