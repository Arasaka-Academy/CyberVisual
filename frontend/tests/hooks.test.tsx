import {
  act,
  cleanup,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Freshness } from "../src/shared/components";
import { useConfigManager } from "../src/features/settings/useConfigManager";
import { usePoll } from "../src/shared/hooks";
import { configPayload, jsonResponse } from "./fixtures";

describe("request lifecycle", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
  it("never overlaps reads, waits after completion, and aborts on unmount", async () => {
    let complete: ((value: string) => void) | undefined;
    let signal: AbortSignal | undefined;
    const read = vi.fn((next?: AbortSignal) => {
      signal = next;
      return new Promise<string>((resolve) => {
        complete = resolve;
      });
    });
    const view = renderHook(() => usePoll(read, 1000));
    expect(read).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(read).toHaveBeenCalledTimes(1);
    await act(async () => complete!("ready"));
    expect(view.result.current.data).toBe("ready");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(read).toHaveBeenCalledTimes(2);
    view.unmount();
    expect(signal!.aborted).toBe(true);
  });
  it("pauses reads while disabled and immediately refreshes on resume", async () => {
    const read = vi.fn(async () => "online");
    const view = renderHook(({ visible }) => usePoll(read, 1000, visible), {
      initialProps: { visible: true },
    });
    await act(async () => {});
    view.rerender({ visible: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(read).toHaveBeenCalledTimes(1);
    view.rerender({ visible: true });
    await act(async () => {});
    expect(read).toHaveBeenCalledTimes(2);
  });
  it("keeps previous data when a read fails and recovers independently", async () => {
    const read = vi
      .fn<() => Promise<string>>()
      .mockResolvedValueOnce("first")
      .mockRejectedValueOnce(new Error("read failed"))
      .mockResolvedValue("recovered");
    const view = renderHook(() => usePoll(read, 1000));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(view.result.current.data).toBe("first");
    expect(view.result.current.error).toBe("read failed");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(view.result.current.data).toBe("recovered");
    expect(view.result.current.error).toBe("");
  });
  it("marks five-second-old state as stale", () => {
    render(<Freshness updatedAt={1000} now={7000} />);
    expect(screen.getByText(/数据已过期/)).toBeInTheDocument();
  });
  it("reconciles a timed-out save without repeating the mutation", async () => {
    let reads = 0;
    const mock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT")
        return new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        });
      reads += 1;
      return jsonResponse({
        ...configPayload,
        confidence: reads > 1 ? 0.72 : configPayload.confidence,
      });
    });
    vi.stubGlobal("fetch", mock);
    const view = renderHook(() => useConfigManager(true));
    await act(async () => {});
    act(() => view.result.current.edit({ confidence: 0.72 }));
    let save: Promise<void>;
    act(() => {
      save = view.result.current.save("ai");
      void view.result.current.save("ai");
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
      await save!;
    });
    expect(
      mock.mock.calls.filter(([, init]) => init?.method === "PUT"),
    ).toHaveLength(1);
    expect(view.result.current.notices.ai).toContain("确认配置保存成功");
    expect(view.result.current.applied?.confidence).toBe(0.72);
    expect(view.result.current.dirty).toBe(false);
  });
  it("preserves dirty groups while revalidating the rest of the configuration", async () => {
    let reads = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        reads += 1;
        return jsonResponse({
          ...configPayload,
          confidence: reads > 1 ? 0.6 : 0.35,
        });
      }),
    );
    const view = renderHook(({ visible }) => useConfigManager(visible), {
      initialProps: { visible: true },
    });
    await act(async () => {});
    act(() =>
      view.result.current.edit({ network_camera: { rtsp_port: 9554 } }),
    );
    view.rerender({ visible: false });
    view.rerender({ visible: true });
    await act(async () => {});
    expect(view.result.current.draft?.network_camera?.rtsp_port).toBe(9554);
    expect(view.result.current.draft?.confidence).toBe(0.6);
    expect(view.result.current.applied?.network_camera?.rtsp_port).toBe(8554);
  });
  it("does not let an older configuration read overwrite a completed save", async () => {
    let reads = 0;
    let completeOld: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PUT")
          return jsonResponse({ ...configPayload, confidence: 0.72 });
        reads += 1;
        if (reads === 2)
          return new Promise<Response>((resolve) => {
            completeOld = resolve;
          });
        return jsonResponse({
          ...configPayload,
          confidence: reads > 2 ? 0.72 : 0.35,
        });
      }),
    );
    const view = renderHook(({ visible }) => useConfigManager(visible), {
      initialProps: { visible: true },
    });
    await act(async () => {});
    act(() => view.result.current.edit({ confidence: 0.72 }));
    view.rerender({ visible: false });
    view.rerender({ visible: true });
    await act(async () => {});
    expect(completeOld).toBeDefined();
    await act(async () => {
      await view.result.current.save("ai");
    });
    await act(async () => {
      completeOld!(new Response(JSON.stringify(configPayload)));
    });
    expect(view.result.current.applied?.confidence).toBe(0.72);
    expect(view.result.current.dirtyGroup("ai")).toBe(false);
  });
});
