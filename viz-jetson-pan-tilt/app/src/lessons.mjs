export const lessons = [
  {
    id: 'assembly', number: '01', nav: '认识整机', title: '一台云台，\n各司其职。',
    intro: '一块运算板、两个转动轴、一只摄像头。先看看它们怎样组成一个完整系统。',
    detail: '底座里的电机负责左右转，侧面的电机负责抬头与低头。Jetson Nano 放在旁边，发送运动指令并接收相机图像。',
    insight: '拖动装配进度，看看每个零件装在哪里。',
    caption: '从零件到整机', concept: '结构与分工',
  },
  {
    id: 'pan', number: '02', nav: '水平转动', title: '让镜头\n左右看。',
    intro: '水平电机的机身留在底座里。它的输出轴带动整个上层结构一起转。',
    detail: '注意侧面的俯仰电机：它也会跟着水平轴转动，相机的俯仰角保持不变。',
    insight: '试着停在 +45°，观察上座和侧面电机。',
    caption: '水平轴 · 整个上层随动', concept: '一个轴，带动上层',
  },
  {
    id: 'tilt', number: '03', nav: '俯仰转动', title: '抬头，\n或者低头。',
    intro: '侧面电机带动相机托架，让镜头绕横向轴改变朝向。',
    detail: '这一刻，上座和电机机身保持不动，转动的是输出轴、托架与相机。图中的短线表示镜头朝向。',
    insight: '向正方向拖动，看镜头抬起来。',
    caption: '俯仰轴 · 相机绕横轴转动', concept: '只改变仰角',
  },
  {
    id: 'uart', number: '04', nav: 'UART 控制', title: '先发指令，\n再转动。',
    intro: 'Nano 给出目标角度，一体驱动器接收指令，再驱动对应的步进电机。',
    detail: '两台电机各有自己的控制对象。图中的两条 UART 路径表示逻辑控制关系，运动过程经过放慢，方便观察。',
    insight: '发送一次，让两个轴共同改变镜头朝向。',
    caption: 'UART · 从上位机到一体驱动器', concept: '目标 → 驱动 → 运动',
  },
  {
    id: 'capture', number: '05', nav: '图像回传', title: '镜头负责看，\nNano 负责算。',
    intro: 'IMX477 把光线转换为图像，图像沿 CSI 链路回到 Jetson Nano。',
    detail: '运动指令走 UART，图像数据走 CSI。下面的虚拟取景由同一份云台姿态生成，你可以采集一帧观察这条链路。',
    insight: '从感光、采集到回传，跟着图像走一遍。',
    caption: 'CSI · 从 IMX477 回到 Nano', concept: '感光 → 采集 → 回传',
  },
  {
    id: 'sandbox', number: '06', nav: '自己搭建', title: '现在，\n自己搭一遍。',
    intro: '把设备放上工作台，再连接相应接口。准备好后，运行你的视觉云台。',
    detail: '这里连接的是逻辑接口；Nano 默认已有独立供电。电机驱动需要接入电机电源。',
    caption: '自由实验 · 组装与连接', concept: '搭建你的系统',
  },
];

export const partDetails = {
  nano: { title: 'Jetson Nano', role: '上位机', text: '负责运行图像与控制逻辑，通过 UART 发送目标，并通过 CSI 接收图像。开发板采用 100 × 80 mm 参考包络。' },
  yaw: { title: '水平步进电机', role: '水平轴', text: '42 mm 电机的机身固定在底座中。输出轴带动上层转动；背部控制板表示内置串口驱动器。' },
  tilt: { title: '俯仰步进电机', role: '俯仰轴', text: '机身固定在上座上，随水平轴一起转。它的输出轴单独带动相机托架抬头、低头。' },
  camera: { title: 'IMX477 HQ', role: '视觉端', text: '38 × 38 mm 相机 PCB 通过四点紧固安装在托架上。镜头、传感器和 CSI 接口一起随两轴改变姿态。' },
  upper: { title: '上座与连接臂', role: '运动支架', text: '支架从水平轴连接到侧面的俯仰电机。带肋立柱承载上层结构，几何沿用仓库中的打印件。' },
  base: { title: '底座', role: '固定支撑', text: '底座固定水平电机，转动时保持静止。上方结构通过电机输出轴与它连接。' },
  power: { title: '电机电源', role: '驱动供电', text: '通过两个逻辑支路给电机驱动供电。电压、电流和真实接法应按实际一体驱动器资料确认。' },
};

export const phaseLabels = {
  idle: '等待操作', sending: '正在发送指令', moving: '两个轴正在运动', complete: '演示完成',
  exposing: 'IMX477 正在采集', transferring: '图像沿 CSI 回传', running: '实验运行中', stopped: '已停止',
};

export const themes = {
  paper: { name: '纸白', background: '#f0f0e9', floor: '#dfe1d8', grid: '#bfc6bc', label: '#4d5c53' },
  graphite: { name: '石墨', background: '#222b29', floor: '#34413b', grid: '#526457', label: '#d1d9d1' },
  blueprint: { name: '蓝图', background: '#122d40', floor: '#1d4156', grid: '#40758d', label: '#c7e1ed' },
};
