# 来源与致谢

| 内容 | 来源与用途 |
| --- | --- |
| 装配网格、支架、相机和紧固件 | 本仓库 `models/imx477-hq/figure/scene.json`，基线 `30b5ca7`；保留全部 57 个源零件与原始三角面 |
| 相机尺寸 | [微雪 IMX477 12.3MP Camera](https://www.waveshare.net/wiki/IMX477_12.3MP_Camera)：38 × 38 mm PCB、30 × 30 mm 孔距；现有项目设计记录用于交叉核对 |
| Nano 参考外形 | [NVIDIA Jetson Nano Developer Kit](https://developer.nvidia.com/embedded/jetson-nano-developer-kit)：100 × 80 mm 名义开发板包络；散热器与接口布局为自行建立的示意几何 |
| 一体驱动器与电源 | 自行建立的教学参考外形；电机 SKU 未提供，未复制或声称对应厂商产品模型 |
| 教学与构图参考 | Bartosz Ciechanowski 的 [Gears](https://ciechanow.ski/gears/) 和 [Cameras and Lenses](https://ciechanow.ski/cameras-and-lenses/)；参考局部观察与直接操作的教学方式，未复制文字、代码或图片 |
| 图标 | [Lucide](https://lucide.dev/)，ISC License |
| 界面与三维运行时 | [React](https://react.dev/)、[Three.js](https://threejs.org/)、[React Three Fiber](https://r3f.docs.pmnd.rs/)、[drei](https://drei.docs.pmnd.rs/)，MIT License |
| 构建与验收 | [Vite](https://vite.dev/)，MIT License；[Playwright](https://playwright.dev/)，Apache-2.0 |

新增电子件、标定板纹理与场景均为本工程程序生成。未下载或重新分发第三方模型、照片、音频和字体。原仓库资产的权利归属沿用仓库原有约定；上表不为来源未声明的原资产另行授予许可。

精确依赖版本记录在 `app/package-lock.json`，资产来源哈希与节点锚点记录在 `app/public/assets/catalog.json`，具体尺寸假设记录在 `blender/refs/assets.md`。
