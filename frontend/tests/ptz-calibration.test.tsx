import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import PTZPanel from "../src/features/ptz/PTZPanel";
import type { PTZStatus } from "../src/features/ptz/types";
import { installFetch, jsonResponse, ptzPayload } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it.each([true, false])("requires explicit center confirmation and allows manual reconnect (hardware ready: %s)", async (hardwareReady) => {
  let state: PTZStatus = {
    ...ptzPayload,
    driver: "pd42s1", simulated: false, position: null,
    state: hardwareReady ? "calibration_required" : "unavailable",
    hardware_ready: hardwareReady, calibrated: false, calibration_required: true,
    fault: hardwareReady ? null : "serial_connection_failed",
  };
  const fetchMock = installFetch({
    "/api/ptz": () => jsonResponse(state),
    "/api/ptz/command": () => jsonResponse(state),
    "/api/ptz/calibrate-center": () => {
      state = {
        ...state, state: "running", hardware_ready: true, calibrated: true,
        calibration_required: false, fault: null,
        position: { pan: 0, tilt: 0, moving: false },
      };
      return jsonResponse(state);
    },
  });
  render(<PTZPanel visible now={Date.now()} />);
  const user = userEvent.setup();
  const button = await screen.findByRole("button", { name: hardwareReady ? "标定中心" : "重连并标定中心" });
  expect(screen.getByRole("button", { name: "向上移动" })).toBeDisabled();
  await user.click(button);
  expect(fetchMock.mock.calls.some(([path]) => path === "/api/ptz/calibrate-center")).toBe(false);
  await user.click(screen.getByRole("button", { name: "确认当前位置为中心并启用" }));
  await screen.findByText("已确认中心并启用云台。");
  await waitFor(() => expect(screen.getByRole("button", { name: "向上移动" })).toBeEnabled());
  const writes = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(writes.filter(([path]) => path === "/api/ptz/calibrate-center").map(([, init]) => JSON.parse(String(init?.body)))).toEqual([{ confirm: true }]);
  expect(writes.filter(([path]) => path === "/api/ptz/command").every(([, init]) => JSON.parse(String(init?.body)).action === "stop")).toBe(true);
});
