# 验收记录 · 2026-11-06

已完成本轮浏览器仿真验收。最终检查针对 `npm run build` 生成的生产静态站点，在 5420 端口用 `npm run preview` 提供服务；离线单文件另以 `file://` 打开并阻断所有 HTTP(S) 请求。

环境：本机 macOS、Node.js v26.13.0、Playwright 1.56.1 / Chromium。机器可读报告：[browser-report.json](evidence/browser-report.json)，具体执行时间见报告中的 UTC 时间戳。

## 结果

| 检查 | 结果与证据 |
| --- | --- |
| 状态、运动与实际资产 | **18/18 通过**；其中 3 项加载实际 GLB，检查固定底座、双轴继承、移动接口和 57 个源零件的三角面数 |
| 静态构建 | 通过；同时生成整个 `app/dist/` 站点及约 2.82 MB 的自包含 `lesson.html` |
| 浏览器交互 | **15/15 通过**；五课、搭建实验、键盘、触控、主题、复位、减少动态效果与离线入口 |
| 错误路径 | 缺设备、缺电机供电、UART 误接 CSI 均给出具体原因并禁止运行；移除必要连接立即停止 |
| 运行与停止 | 正确连接可运行；不同姿态生成不同虚拟图像；停止后角度、仿真时间和已采集帧不再变化 |
| 完整复位 | 清空设备、线路、待连接接口及已采集帧，角度归零；连续切课会取消未完成指令 |
| 三种主题 | 三个验收宽度均操作切换；根背景与实际标题颜色正确，受检正文/辅助文字的最低对比度分别为纸白 **4.66:1**、石墨 **4.79:1**、蓝图 **5.37:1** |
| 布局与取景 | 1920×1080、1280×720、390×844；无页面横向溢出，云台、板卡与电源完整进入取景；手机拆装和搭建托盘使用更宽视角，移动端上下布局 |
| 控制台 | 页面异常与 error 级控制台消息 **0** |

模型取景测量使用最终渲染相机和各网格边界；本机采样帧率约 60 fps，仅反映本次浏览器环境。线路端点从 GLB 的实际节点取世界坐标；导出层级测试验证其与双轴变换一致，浏览器运行检查验证线路端点保持连接。

## 截图索引

最终自动生成 **23 张验收截图**；[总览联系表](evidence/contact-sheet.png) 汇总这些截图。目录内带 `first` 或 `initial` 的图片为审查草稿，不是最终验收依据。

| 内容 | 截图 |
| --- | --- |
| 认识整机、零件归位 | [整机](evidence/desktop-overview.png)、[装配 0%](evidence/assembly-tray.png) |
| 水平教学范围 | [+90°](evidence/pan-positive.png)、[−90°](evidence/pan-negative.png) |
| 俯仰教学范围 | [+35°](evidence/tilt-positive.png)、[−35°](evidence/tilt-negative.png) |
| UART、CSI 与取景 | [发送目标后](evidence/uart-command.png)、[采集回传后](evidence/camera-capture.png) |
| 搭建与校验 | [接口错误](evidence/sandbox-validation.png)、[正确组装并停止](evidence/sandbox-complete.png) |
| 1920 px 三主题 | [纸白](evidence/theme-paper.png)、[石墨](evidence/theme-graphite.png)、[蓝图](evidence/theme-blueprint.png) |
| 1280×720 三主题 | [纸白](evidence/desktop-1280.png)、[石墨](evidence/desktop-1280-graphite.png)、[蓝图](evidence/desktop-1280-blueprint.png) |
| 390 px 手机 | [整机](evidence/mobile-overview.png)、[拆装托盘](evidence/mobile-assembly-tray.png)、[采集](evidence/mobile-capture.png)、[搭建纸白](evidence/mobile-sandbox.png)、[搭建石墨](evidence/mobile-sandbox-graphite.png)、[搭建蓝图](evidence/mobile-sandbox-blueprint.png) |
| 断网单文件 | [离线取景](evidence/standalone-offline.png) |

已查看联系表及关键原尺寸截图。教学范围内的水平、俯仰极限视图未见明显零件穿插；水平携带整个上层，俯仰只改变转子、托架与相机。相机虚拟图像与曝光姿态使用同一份状态及光轴变换。

## 审查修正与边界

审查记录：[资产](notes/review-1.md)、[界面与取景](notes/review-2.md)、[仿真一致性](notes/review-3.md)。修正了初版曝光、取景收敛、主题继承、离线代码嵌入、信号到达时刻、反向点选接口和复位残留。主题、流向和复位问题均有回归检查。

验收没有访问真实 Jetson、UART、电机或相机；没有验证真实厂商协议、位置反馈、引脚电平、供电、CSI 软件兼容性、实体干涉、公差、线缆弯折半径及负载能力。水平 ±90°、俯仰 ±35°、52° 视场均为教学参数。真实电机型号、驱动器尺寸与接口仍需取得对应资料后核对。
