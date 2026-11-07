import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/app/App";
import { installFetch } from "./fixtures";

const storageKey = "cybervisual.appearance.v1";
const schemes = ["neon", "mono", "graphite", "synthwave", "bloodline", "terminal", "amber"];

function root() {
  return document.querySelector("[data-cyberui]");
}

describe("CyberUI appearance", () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.replaceState(null, "", "/#/overview");
    installFetch();
    vi.stubGlobal("scrollTo", vi.fn());
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });
  it("defaults to official Neon Dark and Simplified Chinese", async () => {
    render(<App />);
    await screen.findByText("设备运行中");
    expect(root()).toHaveAttribute("data-scheme", "neon");
    expect(root()).toHaveAttribute("data-mode", "dark");
    expect(root()).toHaveAttribute("lang", "zh-CN");
  });
  it.each(schemes.flatMap((scheme) => ["dark", "light"].map((mode) => ({ scheme, mode }))))(
    "restores $scheme / $mode without modifying device configuration",
    async ({ scheme, mode }) => {
      localStorage.setItem(storageKey, JSON.stringify({ scheme, mode }));
      render(<App />);
      await screen.findByText("设备运行中");
      expect(root()).toHaveAttribute("data-scheme", scheme);
      expect(root()).toHaveAttribute("data-mode", mode);
      expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
    },
  );
  it.each([
    "not json",
    '{"scheme":"invalid","mode":"light"}',
    '{"scheme":"neon","mode":"invalid"}',
    '{"scheme":"amber","mode":["dark"]}',
    '{"scheme":"amber","mode":["light"]}',
    '{"scheme":"amber","mode":["system"]}',
  ])(
    "recovers from invalid saved appearance: %s",
    async (saved) => {
      localStorage.setItem(storageKey, saved);
      render(<App />);
      await screen.findByText("设备运行中");
      expect(root()).toHaveAttribute("data-scheme", "neon");
      expect(root()).toHaveAttribute("data-mode", "dark");
    },
  );
  it("works when browser storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    render(<App />);
    await screen.findByText("设备运行中");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "外观设置" }));
    await user.click(await screen.findByRole("button", { name: "amber" }));
    expect(root()).toHaveAttribute("data-scheme", "amber");
  });
  it("switches themes without remounting the preview or issuing movement commands", async () => {
    window.history.replaceState(null, "", "/#/monitor");
    render(<App />);
    const preview = await screen.findByRole("img");
    fireEvent.load(preview);
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "外观设置" });
    await user.click(trigger);
    await user.click(await screen.findByRole("button", { name: "amber" }));
    await user.click(screen.getByRole("radio", { name: "浅色" }));
    expect(root()).toHaveAttribute("data-mode", "light");
    expect(document.querySelector("[data-cyberui-portal]")).toHaveAttribute("data-scheme", "amber");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("img")).toBe(preview);
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(JSON.parse(localStorage.getItem(storageKey)!)).toEqual({ scheme: "amber", mode: "light" });
    expect(vi.mocked(fetch).mock.calls.some(([url, init]) => init?.method === "PUT" || String(url) === "/api/ptz/command")).toBe(false);
  });
  it("preserves unsaved settings while changing appearance", async () => {
    window.history.replaceState(null, "", "/#/settings");
    render(<App />);
    fireEvent.change(await screen.findByLabelText("置信度阈值"), { target: { value: ".73" } });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "外观设置" }));
    await user.click(await screen.findByRole("button", { name: "terminal" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByLabelText("置信度阈值")).toHaveValue(.73);
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });
});
