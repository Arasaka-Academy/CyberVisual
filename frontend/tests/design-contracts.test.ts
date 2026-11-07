import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";
import manifest from "../cyberui.lock.json";
import { contrast, createTheme, schemes, type Scheme } from "../src/components/cyberui/tokens";

const root = process.cwd() + "/";

describe("pinned CyberUI design contracts", () => {
  it("pins the approved upstream revision and official registry distribution", () => {
    expect(manifest.commit).toBe("e31c0355b2b5189c9af1e6e26150f28a44287659");
    expect(manifest.repository).toBe("Arasaka-Academy/CyberUI");
    expect(manifest.items).not.toContain("chart");
  });
  it.each(Object.entries(manifest.files))("retains the exact upstream source for %s", (file, metadata) => {
    const bytes = readFileSync(root + file);
    const hash = createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
    expect(hash).toBe(metadata.gitBlob);
  });
  it("retains the pinned official ORBIT screenshot independently of application baselines", () => {
    const bytes = readFileSync(root + manifest.orbitReference.screenshot);
    const hash = createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
    expect(hash).toBe(manifest.orbitReference.gitBlob);
  });
  it.each((Object.keys(schemes) as Scheme[]).flatMap((scheme) => (["dark", "light"] as const).map((mode) => ({ scheme, mode }))))(
    "maintains AA text contrast in $scheme / $mode",
    ({ scheme, mode }) => {
      const theme = createTheme(scheme, mode);
      for (const foreground of [theme.ink, theme.muted, theme.accentText, theme.success, theme.warning, theme.danger, theme.info]) {
        for (const background of [theme.bg, theme.soft]) {
          expect(contrast(foreground, background)).toBeGreaterThanOrEqual(4.5);
        }
      }
      expect(contrast(theme.onAccent, theme.accent)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme.onAccent2, theme.accent2)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(theme.onInk, theme.ink)).toBeGreaterThanOrEqual(4.5);
    },
  );
  it("does not reintroduce a parallel hard-coded application palette", () => {
    const css = readdirSync(root + "src", { recursive: true })
      .filter((file) => String(file).endsWith(".css") && !String(file).startsWith("components/"))
      .map((file) => readFileSync(root + "src/" + file, "utf8")).join("\n");
    expect(css).not.toMatch(/#[\da-f]{3,8}\b/i);
    expect(css).not.toMatch(/var\(--(?:background|surface|accent|radius|muted|text|line)\b/);
  });
});
