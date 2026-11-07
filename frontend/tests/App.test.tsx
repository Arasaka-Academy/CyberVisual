import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/app/App";
import {
  configPayload,
  eventPayload,
  installFetch,
  jsonResponse,
  ptzPayload,
  statusPayload,
} from "./fixtures";

function route(value: string) {
  window.history.replaceState(null, "", `/#/${value}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
async function navigate(value: string) {
  await act(async () => route(value));
}
function section(title: string) {
  return within(
    screen.getByRole("heading", { name: title, level: 2 }).closest("section")!,
  );
}
function commands() {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([url]) => String(url) === "/api/ptz/command")
    .map(([, init]) => JSON.parse(String(init?.body)));
}
function puts() {
  return vi
    .mocked(fetch)
    .mock.calls.filter(
      ([url, init]) => String(url) === "/api/config" && init?.method === "PUT",
    )
    .map(([, init]) => JSON.parse(String(init?.body)));
}

describe("device console", () => {
  beforeEach(() => {
    route("overview");
    vi.stubGlobal("scrollTo", vi.fn());
    installFetch();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });
  it("opens overview with five destinations and keeps the video connection closed", async () => {
    render(<App />);
    expect(await screen.findByText("设备运行中")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "主导航" }).querySelectorAll("a"),
    ).toHaveLength(5);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).includes("detections")),
    ).toBe(false);
    expect(screen.getByText("11.4")).toBeInTheDocument();
  });
  it("supports direct NVR links and reports output independently from the external NVR", async () => {
    route("nvr");
    render(<App />);
    expect(
      await screen.findByDisplayValue("rtsp://192.168.1.20:8554/raw"),
    ).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("rtsp://192.168.1.20:8554/annotated"),
    ).toBeInTheDocument();
    expect(screen.getByText("正在发布")).toBeInTheDocument();
    expect(screen.getByText("等待取流")).toBeInTheDocument();
    expect(screen.queryByText("NVR 已连接")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /NVR 接入/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
  it("shows discovery, encoder and source failures even while the protocol service is running", async () => {
    const status = statusPayload();
    status.camera.error = "摄像头连接中断";
    status.network_camera!.discovery = {
      state: "error",
      last_error: "发现接口不可用",
    };
    status.network_camera!.events = {
      ...status.network_camera!.events,
      online: false,
      last_error: "推理进程中断",
    };
    status.network_camera!.profiles[0] = {
      ...status.network_camera!.profiles[0],
      active: false,
      last_error: "H.264 编码器无法启动",
    };
    installFetch({ "/api/status": () => jsonResponse(status) });
    route("nvr");
    render(<App />);
    expect(await screen.findByText("输出故障")).toBeInTheDocument();
    expect(screen.getByText(/发现接口不可用/)).toBeInTheDocument();
    expect(screen.getByText(/H.264 编码器无法启动/)).toBeInTheDocument();
    expect(screen.getByText(/摄像头连接中断/)).toBeInTheDocument();
    expect(screen.getByText(/推理进程中断/)).toBeInTheDocument();
    expect(screen.queryByText("正在发布")).not.toBeInTheDocument();
    expect(screen.getByText("分析离线")).toBeInTheDocument();
  });
  it("reconnects an errored preview, pauses and releases it when leaving", async () => {
    route("monitor");
    render(<App />);
    const image = await screen.findByRole("img");
    const oldSource = image.getAttribute("src");
    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((node) => node.textContent),
    ).toEqual(["实时画面", "云台控制", "当前检测"]);
    fireEvent.error(image);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
    expect(screen.getByRole("img").getAttribute("src")).not.toBe(oldSource);
    fireEvent.click(screen.getByRole("button", { name: "暂停预览" }));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "恢复预览" }));
    expect(screen.getByRole("img")).toBeInTheDocument();
    await navigate("events");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "近期事件" }),
    ).toBeInTheDocument();
  });
  it("retains configuration drafts across pages and only submits the AI group", async () => {
    route("settings");
    render(<App />);
    const field = await screen.findByLabelText("置信度阈值");
    fireEvent.change(field, { target: { value: ".72" } });
    await navigate("overview");
    expect(puts()).toHaveLength(0);
    await navigate("settings");
    expect(screen.getByLabelText("置信度阈值")).toHaveValue(0.72);
    fireEvent.click(
      section("AI 检测").getByRole("button", { name: "保存配置" }),
    );
    expect(await screen.findByText("配置已保存并应用。")).toBeInTheDocument();
    expect(puts()[0]).toEqual({
      confidence: 0.72,
      iou: 0.45,
      class_allowlist: [],
      model_path: configPayload.model_path,
      detector_backend: "mock",
    });
  });
  it("keeps unsaved dimensions separate from applied configuration and supports undo", async () => {
    route("settings");
    render(<App />);
    fireEvent.change(await screen.findByLabelText(/画面宽度/), {
      target: { value: "800" },
    });
    await navigate("overview");
    expect(screen.getByText("640 × 480")).toBeInTheDocument();
    await navigate("settings");
    expect(screen.getByLabelText(/画面宽度/)).toHaveValue(800);
    fireEvent.click(
      section("视频源").getByRole("button", { name: "撤销修改" }),
    );
    expect(screen.getByLabelText(/画面宽度/)).toHaveValue(640);
  });
  it("retains a rejected draft and focuses the error", async () => {
    const original = fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "PUT"
          ? jsonResponse({ error: "配置保存失败" }, 400)
          : original(input, init),
      ),
    );
    route("settings");
    render(<App />);
    fireEvent.change(await screen.findByLabelText("置信度阈值"), {
      target: { value: ".8" },
    });
    fireEvent.click(
      section("AI 检测").getByRole("button", { name: "保存配置" }),
    );
    expect(await screen.findByText("配置保存失败")).toBeInTheDocument();
    expect(screen.getByLabelText("置信度阈值")).toHaveValue(0.8);
    expect(
      section("AI 检测").getByRole("button", { name: "保存配置" }),
    ).toBeEnabled();
  });
  it("saves NVR fields without overwriting the driver or other configuration groups", async () => {
    route("nvr");
    render(<App />);
    fireEvent.change(await screen.findByLabelText("RTSP 端口"), {
      target: { value: "9554" },
    });
    fireEvent.click(
      section("协议配置").getByRole("button", { name: "保存配置" }),
    );
    await screen.findByText("配置已保存，运行结果请查看协议与云台状态。");
    expect(Object.keys(puts()[0])).toEqual(["network_camera"]);
    expect(puts()[0].network_camera.rtsp_port).toBe(9554);
    expect(puts()[0].network_camera).not.toHaveProperty("ptz_driver");
  });
  it("blocks enabling protocols until deployment credentials are configured", async () => {
    const status = statusPayload();
    status.network_camera!.credentials_configured = false;
    installFetch({
      "/api/status": () => jsonResponse(status),
      "/api/config": () =>
        jsonResponse({
          ...configPayload,
          network_camera: { ...configPayload.network_camera!, enabled: false },
        }),
    });
    route("nvr");
    render(<App />);
    expect(
      await screen.findByRole("checkbox", { name: /启用网络摄像头协议/ }),
    ).toBeDisabled();
    expect(screen.getByText("CYBERVISUAL_ONVIF_PASSWORD")).toBeInTheDocument();
  });
  it("offers a selectable address when clipboard access is unavailable", async () => {
    vi.stubGlobal("navigator", { ...navigator, clipboard: undefined });
    route("nvr");
    render(<App />);
    await screen.findByDisplayValue("rtsp://192.168.1.20:8554/raw");
    fireEvent.click(screen.getByRole("button", { name: "复制原始 RTSP 地址" }));
    expect(
      await screen.findByText("地址已选中，请手动复制。"),
    ).toBeInTheDocument();
    const input = screen.getByDisplayValue(
      "rtsp://192.168.1.20:8554/raw",
    ) as HTMLInputElement;
    expect(input).toHaveFocus();
    expect(input.selectionEnd).toBe(input.value.length);
  });
  it("marks presence unknown during analysis outages and supports filtering and pagination", async () => {
    const events = eventPayload();
    events.status.online = false;
    events.events = Array.from({ length: 45 }, (_, index) => ({
      ...events.events[0],
      id: String(index),
      category: index % 2 ? "vehicle" : "person",
      frame_ts: Date.now() / 1000 - index,
    }));
    installFetch({ "/api/events/recent": () => jsonResponse(events) });
    route("events");
    render(<App />);
    expect((await screen.findAllByText("状态未知")).length).toBeGreaterThan(0);
    expect(screen.getByText(/最近已知：存在/)).toBeInTheDocument();
    expect(screen.getByText("第 1 / 3 页")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一页事件" }));
    expect(screen.getByText("第 2 / 3 页")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("事件类别"), {
      target: { value: "person" },
    });
    expect(screen.getByText("第 1 / 2 页")).toBeInTheDocument();
    expect(screen.queryByText("车辆出现")).not.toBeInTheDocument();
  });
  it("moves only while a direction is held and stops on release", async () => {
    route("monitor");
    render(<App />);
    const right = await screen.findByRole("button", { name: "向右移动" });
    await waitFor(() => expect(right).toBeEnabled());
    fireEvent(
      right,
      new MouseEvent("pointerdown", { button: 0, bubbles: true }),
    );
    await waitFor(() => expect(commands()[0]?.action).toBe("continuous_move"));
    fireEvent.pointerUp(right, { pointerId: 1 });
    await waitFor(() =>
      expect(commands()[commands().length - 1]?.action).toBe("stop"),
    );
    expect(commands()[0].pan).toBe(0.3);
  });
  it("queues stop after an in-flight movement when navigating away", async () => {
    let finish: (() => void) | undefined;
    const original = fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        if (
          String(input) === "/api/ptz/command" &&
          String(init?.body).includes("continuous_move")
        )
          return new Promise<Response>((resolve) => {
            finish = () =>
              resolve(
                new Response(JSON.stringify(ptzPayload), { status: 200 }),
              );
          });
        return original(input, init);
      }),
    );
    route("monitor");
    render(<App />);
    const right = await screen.findByRole("button", { name: "向右移动" });
    await waitFor(() => expect(right).toBeEnabled());
    fireEvent.keyDown(right, { key: " " });
    await waitFor(() => expect(finish).toBeDefined());
    await navigate("overview");
    await act(async () => finish!());
    await waitFor(() =>
      expect(commands()[commands().length - 1]?.action).toBe("stop"),
    );
    expect(
      commands().filter((command) => command.action === "continuous_move"),
    ).toHaveLength(1);
  });
  it("stops on window blur and hides the video in background tabs", async () => {
    route("monitor");
    render(<App />);
    const up = await screen.findByRole("button", { name: "向上移动" });
    await waitFor(() => expect(up).toBeEnabled());
    fireEvent.keyDown(up, { key: "Enter" });
    await waitFor(() => expect(commands()[0]?.action).toBe("continuous_move"));
    fireEvent(window, new Event("blur"));
    await waitFor(() =>
      expect(commands()[commands().length - 1]?.action).toBe("stop"),
    );
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    fireEvent(document, new Event("visibilitychange"));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
  it("reports disabled PTZ without offering working movement buttons", async () => {
    installFetch({
      "/api/ptz": () =>
        jsonResponse({
          ...ptzPayload,
          enabled: false,
          state: "disabled",
          simulated: false,
          position: null,
        }),
    });
    route("monitor");
    render(<App />);
    expect(await screen.findByText(/云台尚未启用/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "向右移动" })).toBeDisabled();
    expect(commands()).toHaveLength(0);
  });
  it("reports snapshot storage on the device", async () => {
    route("monitor");
    render(<App />);
    const snapshot = await screen.findByRole("button", { name: "保存快照" });
    await waitFor(() => expect(snapshot).toBeEnabled());
    fireEvent.click(snapshot);
    expect(
      await screen.findByText("快照已保存到设备：/captures/test.jpg"),
    ).toBeInTheDocument();
  });
  it("accepts older status payloads without network or snapshot fields", async () => {
    const legacy = statusPayload() as Partial<ReturnType<typeof statusPayload>>;
    delete legacy.network_camera;
    delete legacy.auto_snapshot;
    installFetch({ "/api/status": () => jsonResponse(legacy) });
    render(<App />);
    expect(await screen.findByText("设备运行中")).toBeInTheDocument();
    expect(screen.getByText("已关闭")).toBeInTheDocument();
  });
});
