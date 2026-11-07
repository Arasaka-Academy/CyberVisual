import { useEffect, useState } from "react";
export type Route = "overview" | "monitor" | "nvr" | "events" | "settings";
const ROUTES: Route[] = ["overview", "monitor", "nvr", "events", "settings"];
export function useRoute() {
  const read = (): Route => {
    const value = window.location.hash
      .replace(/^#\/?/, "")
      .split("?")[0] as Route;
    return ROUTES.includes(value) ? value : "overview";
  };
  const [route, setRoute] = useState<Route>(read);
  useEffect(() => {
    if (!window.location.hash)
      window.history.replaceState(null, "", "#/overview");
    const change = () => setRoute(read());
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return route;
}
export function useVisible() {
  const [visible, setVisible] = useState(!document.hidden);
  useEffect(() => {
    const change = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  return visible;
}
export function useNow(enabled: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!enabled) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [enabled]);
  return now;
}
