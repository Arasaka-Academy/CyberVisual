import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { CyberUIProvider, useCyberUI } from "../components/cyberui/provider";
import { schemes, type Scheme, type ThemeMode } from "../components/cyberui/tokens";
import { Dialog } from "../components/cyberui/dialog";
import { ThemeSwatch } from "../components/cyberui/theme-swatch";
import { SegmentedControl } from "../components/cyberui/segmented-control";
import { Button } from "../components/cyberui/button";

const storageKey = "cybervisual.appearance.v1";
const defaultAppearance = { scheme: "neon" as Scheme, mode: "dark" as ThemeMode };
const themeNames: Record<Scheme, string> = {
  neon: "霓虹", mono: "黑白", graphite: "石墨", synthwave: "合成波",
  bloodline: "赤红", terminal: "终端", amber: "琥珀",
};
type Appearance = typeof defaultAppearance;
const AppearanceContext = createContext<{
  appearance: Appearance;
  update: (patch: Partial<Appearance>) => void;
} | null>(null);

function readAppearance(): Appearance {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (saved && typeof saved === "object" && "scheme" in saved && "mode" in saved &&
      typeof saved.scheme === "string" && Object.prototype.hasOwnProperty.call(schemes, saved.scheme) &&
      typeof saved.mode === "string" && ["dark", "light", "system"].includes(saved.mode)) {
      return { scheme: saved.scheme as Scheme, mode: saved.mode as ThemeMode };
    }
  } catch {}
  return defaultAppearance;
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearance] = useState(readAppearance);
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(appearance)); } catch {}
  }, [appearance]);
  const context = useMemo(() => ({
    appearance,
    update: (patch: Partial<Appearance>) => setAppearance((current) => ({ ...current, ...patch })),
  }), [appearance]);
  return (
    <AppearanceContext.Provider value={context}>
      <CyberUIProvider scheme={appearance.scheme} mode={appearance.mode} locale="zh-CN" className="cybervisual-root">
        <DocumentAppearance />
        {children}
      </CyberUIProvider>
    </AppearanceContext.Provider>
  );
}

function DocumentAppearance() {
  const { scheme, mode } = useCyberUI();
  useEffect(() => {
    document.documentElement.style.colorScheme = mode;
    document.documentElement.style.backgroundColor = schemes[scheme][mode].bg;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", schemes[scheme][mode].bg);
  }, [scheme, mode]);
  return null;
}

export function AppearanceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const context = useContext(AppearanceContext)!;
  const { mode: resolvedMode } = useCyberUI();
  return (
    <Dialog title="外观设置" isOpen={open} onOpenChange={onOpenChange} className="appearance-dialog">
      <p className="muted">七套信号配色，同一套精确结构。外观只保存在当前浏览器，不修改设备配置。</p>
      <fieldset className="appearance-palettes">
        <legend>主题配色</legend>
        <div className="theme-grid">
          {(Object.keys(schemes) as Scheme[]).map((scheme) => (
            <div key={scheme}>
              <ThemeSwatch scheme={scheme} mode={resolvedMode} selected={context.appearance.scheme === scheme}
                onSelect={() => context.update({ scheme })} />
              <span className="theme-name">{themeNames[scheme]}</span>
            </div>
          ))}
        </div>
      </fieldset>
      <SegmentedControl label="显示模式" value={context.appearance.mode}
        options={[{ id: "dark", label: "深色" }, { id: "light", label: "浅色" }, { id: "system", label: "跟随系统" }]}
        onChange={(mode) => context.update({ mode: mode as ThemeMode })} />
      <div className="appearance-footer"><span className="muted">CYBERUI / {context.appearance.scheme.toUpperCase()}</span>
        <Button onPress={() => onOpenChange(false)}>完成</Button>
      </div>
    </Dialog>
  );
}
