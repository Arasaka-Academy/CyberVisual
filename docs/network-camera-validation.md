# 网络摄像头本地验收记录

日期：2026-11-07。实现分支：`codex/network-camera`。

## 本次通过的检查

| 检查 | 环境与结果 |
| --- | --- |
| 后端全量 | Linux Docker，88 passed，包含 76 项常规测试与 12 项协议互通测试 |
| 双路视频 | 独立 onvif-zeep 获取 raw／annotated URI，FFmpeg 对 TCP、UDP 均实际解码 RGB 帧；通过确定性边框像素区域确认标注区别 |
| 共享编码 | 同一路两个并发 RTSP 会话仅一条编码管线；一个客户端先断开，另一个继续完成解码 |
| 重连／认证 | 断开后重连成功；RTSP 缺失／错误账号被拒绝；HTTP Digest 快照成功且重复凭据头被拒绝；WSSE 过期／重放被拒绝 |
| Device／Media1 | 独立 onvif-zeep 0.2.12／Zeep 4.3.3 查询服务、双 Profile、共同物理源、编码参数及快照 |
| Media2 | Zeep strict 模式加载官方 Media2 WSDL／XSD 的离线快照，读取双 Profile、编码器、取流与快照 URI |
| WS-Discovery | 通过实际 UDP 3702 组播 Probe 得到稳定 UUID 与正确 XAddr，单播 Resolve 成功，停止后端口可重新绑定 |
| AI 事件 | 出现／持续存在不重复／2 秒消失；两个独立订阅；续订、取消、状态同步；有界队列溢出与到期清理 |
| 故障与恢复 | 摄像头 read 失败与检测器加载失败均上报离线，恢复后上报在线，不误发消失；检测失败期间 raw RTSP 仍可实际解码 |
| 模拟 PTZ | 独立客户端验证绝对／相对／连续移动、显式停止、0.1 秒和默认 2 秒超时、边界限位、固定归位、预置位设置／调用／删除 |
| 配置与生命周期 | 旧配置默认关闭；无秘密配置回传；持久 UUID；热重配后 PTZ 能力和 Profile 正确，旧订阅失效，视频可重连；各用例退出时采集／推理／RTSP 线程结束、端口释放 |
| 前端 | Vitest 4 passed；TypeScript／Vite 生产构建通过；生成的 dist 已更新 |
| 浏览器 DOM | 实际 Linux 服务与 MJPEG；1280、375、320 CSS 像素宽度下无页面横向溢出；服务状态可见，账号／编码器／事件／模拟 PTZ／双路地址均可读取 |
| 基线静态检查 | 后端运行时代码通过 Python 3.6 语法解析；部署脚本 bash 语法、JSON 配置、dist 引用、官方 schema 校验和通过 |

协议测试使用 Debian bookworm、GStreamer 1.22、`x264enc`、FFmpeg 5.1，
输入为 320×240 synthetic 和显式 mock。浏览器预览使用 640×480 synthetic。
浏览器截图调用超时，本记录仅将 DOM、尺寸和实际预览加载列为浏览器证据。

## 待设备条件具备后验收

- Jetson Nano / JetPack 4.6 / Python 3.6 的真实运行和依赖安装。
- `nvv4l2h264enc` 实际硬件编码、双路帧率、功耗／温度和持续运行。
- 物理摄像头拔插、设备重启、systemd 在目标系统上的恢复。
- 真实 AI 模型效果与机械 PTZ 动作。真实电机驱动属于后续单独验收范围。
- 商业 NVR／ONVIF Device Manager 的互通与正式 ONVIF Profile 认证。

已加入 GitHub Actions 工作流；本记录不代表远端 CI 已运行。
复现命令、支持矩阵与 CyberOS 接入契约见 [network-camera.md](network-camera.md)。
