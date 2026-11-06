import assert from 'node:assert/strict';
import { existsSync, readdirSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { requiredConnections, portById } from '../src/simulation.mjs';

const app = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const evidence = resolve(process.env.LESSON_EVIDENCE_DIR ?? resolve(app, '../evidence'));
await mkdir(evidence, { recursive: true });
const base = process.env.LESSON_URL ?? 'http://127.0.0.1:5420/';
function browserExecutable() {
  if (process.env.LESSON_BROWSER_PATH) return process.env.LESSON_BROWSER_PATH;
  if (existsSync(chromium.executablePath())) return chromium.executablePath();
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH ?? resolve(homedir(), process.platform === 'darwin' ? 'Library/Caches/ms-playwright' : '.cache/ms-playwright');
  if (existsSync(cache)) for (const folder of readdirSync(cache).filter(n => /^chromium-\d+$/.test(n)).sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]))) {
    for (const path of ['chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium', 'chrome-linux/chrome', 'chrome-linux64/chrome', 'chrome-win/chrome.exe']) {
      const file = resolve(cache, folder, path); if (existsSync(file)) return file;
    }
  }
  throw new Error('Chromium is not installed. Run npx playwright install chromium, or set LESSON_BROWSER_PATH.');
}
const report = { generated: new Date().toISOString(), base, checks: [], measurements: {}, screenshots: [], consoleErrors: [] };
const browser = await chromium.launch({ executablePath: browserExecutable(), headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
const state = page => page.evaluate(() => window.__lesson.getState());
const waitPhase = (page, phase) => page.waitForFunction(phase => window.__lesson?.getState().phase === phase, phase, { timeout: 15000 });
async function check(name, run) { await run(); report.checks.push(name); console.log(`PASS ${name}`); }
function recordErrors(page) {
  page.on('pageerror', error => report.consoleErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') report.consoleErrors.push(message.text()); });
}
async function ready(page, url = base) {
  await page.goto(url, { waitUntil: 'load' });
  await page.bringToFront();
  await page.waitForFunction(() => window.__lesson?.telemetry.ready && window.__lesson.telemetry.fps > 0, null, { timeout: 20000 });
  await page.waitForTimeout(400);
}
async function shot(page, name) {
  await page.evaluate(() => scrollTo(0, 0)); await page.waitForTimeout(250);
  await page.screenshot({ path: resolve(evidence, `${name}.png`), fullPage: true });
  report.screenshots.push(`${name}.png`);
}
async function choose(page, lesson) {
  await page.locator(`[data-lesson="${lesson}"]`).click();
  await page.waitForFunction(id => window.__lesson.getState().lesson === id, lesson);
}
async function connect(page, from, to) {
  await page.getByRole('button', { name: `连接 ${portById[from].label}`, exact: true }).click();
  await page.getByRole('button', { name: `连接 ${portById[to].label}`, exact: true }).click();
}
async function checkFraming(page, key) {
  await page.waitForTimeout(1500);
  const telemetry = await page.evaluate(() => window.__lesson.telemetry);
  const b = telemetry.subjectBounds;
  assert.ok(b && b.left >= .015 && b.right <= .985 && b.top >= .035 && b.bottom <= .96, `${key} subject is clipped: ${JSON.stringify(b)}`);
  assert.ok(telemetry.camera.target[1] > .06, `${key} view target failed to settle`);
  report.measurements[key] = telemetry;
}
function rgb(color) {
  if (color.startsWith('#')) return color.slice(1).match(/../g).map(value => parseInt(value, 16));
  return color.match(/[\d.]+/g).slice(0, 3).map(Number);
}
function contrast(foreground, background) {
  const luminance = color => {
    const values = rgb(color).map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
    return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
  };
  const a = luminance(foreground), b = luminance(background);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}
async function checkTheme(page, theme) {
  const colors = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const color = selector => getComputedStyle(document.querySelector(selector)).color;
    return {
      background: root.backgroundColor,
      expectedBackground: root.getPropertyValue('--page').trim(),
      title: color('.intro h1'), heading: color('.lesson-copy h2'),
      quiet: color('.lesson-panel-top'), muted: color('.intro p'),
      backgrounds: ['--page', '--surface', '--fill', '--stage'].map(key => root.getPropertyValue(key).trim()),
    };
  });
  assert.deepEqual(rgb(colors.background), rgb(colors.expectedBackground), `${theme} page background must follow its theme`);
  const ratios = {
    title: contrast(colors.title, colors.background),
    heading: contrast(colors.heading, colors.backgrounds[1]),
    quiet: Math.min(...colors.backgrounds.map(background => contrast(colors.quiet, background))),
    muted: Math.min(...colors.backgrounds.map(background => contrast(colors.muted, background))),
  };
  for (const [role, ratio] of Object.entries(ratios)) assert.ok(ratio >= 4.5, `${theme} ${role} text contrast is ${ratio.toFixed(2)}, expected at least 4.5`);
  report.measurements[`theme-${theme}`] = { colors, contrast: ratios };
}

let failure;
try {
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await context.newPage(); recordErrors(page);
  await ready(page);
  await check('1920 overview renders and frames the complete gimbal', async () => { await checkFraming(page, 'desktop1920'); await shot(page, 'desktop-overview'); });
  await check('assembly slider physically disassembles and returns to the seated pose', async () => {
    const range = page.getByRole('slider', { name: '装配进度' });
    await range.focus(); await range.press('Home'); assert.equal((await state(page)).assembly, 0);
    await shot(page, 'assembly-tray');
    await range.press('End'); assert.equal((await state(page)).assembly, 1);
  });
  await check('pan and tilt ranges respond to keyboard and reset on chapter changes', async () => {
    await choose(page, 'pan');
    const pan = page.getByRole('slider', { name: '水平角度' });
    await pan.focus(); await pan.press('End'); assert.equal((await state(page)).pan, 90);
    await shot(page, 'pan-positive');
    await pan.press('Home'); assert.equal((await state(page)).pan, -90);
    await shot(page, 'pan-negative');
    await page.getByRole('button', { name: '复位当前课程' }).click();
    assert.equal((await state(page)).pan, 0);
    await choose(page, 'tilt');
    const tilt = page.getByRole('slider', { name: '俯仰角度' });
    await tilt.focus(); await tilt.press('End'); assert.equal((await state(page)).tilt, 35);
    assert.equal((await state(page)).pan, 0);
    await shot(page, 'tilt-positive');
    await tilt.press('Home'); assert.equal((await state(page)).tilt, -35);
    await shot(page, 'tilt-negative');
  });
  await check('UART delivers the command, then moves both axes to the target', async () => {
    await choose(page, 'uart'); await page.getByRole('button', { name: '发送双轴目标' }).click();
    assert.equal((await state(page)).pan, 0);
    await waitPhase(page, 'complete');
    const s = await state(page); assert.equal(s.pan, 30); assert.equal(s.tilt, 15);
    const t = await page.evaluate(() => window.__lesson.telemetry);
    assert.ok(t.connectorGap < .000001); assert.equal(Object.keys(t.anchors).length, 10);
    await shot(page, 'uart-command');
  });
  await check('selectable part details close with Escape and dialogs restore focus', async () => {
    await page.getByRole('button', { name: '思考与控制 Jetson Nano' }).click();
    await page.getByRole('complementary', { name: '零件说明' }).waitFor();
    await page.keyboard.press('Escape'); assert.equal((await state(page)).selected, null);
    const trigger = page.getByRole('button', { name: '模型与接口说明' });
    await trigger.click(); await page.getByRole('dialog').waitFor(); await page.keyboard.press('Escape');
    assert.ok(await trigger.evaluate(el => el === document.activeElement));
  });
  let neutralImage;
  await check('capture produces an actual rendered frame and paired pose metadata', async () => {
    await choose(page, 'capture'); await page.getByRole('button', { name: '采集一帧', exact: true }).click();
    await waitPhase(page, 'complete'); await page.locator('.snapshot img').waitFor();
    neutralImage = await page.locator('.snapshot img').getAttribute('src');
    assert.ok(neutralImage.length > 10000); assert.equal((await state(page)).frame.pan, 0);
    await page.getByRole('button', { name: '再采集一帧' }).waitFor();
    await shot(page, 'camera-capture');
  });
  await check('sandbox blocks missing parts, missing power and mismatched interfaces', async () => {
    await choose(page, 'sandbox'); await page.getByRole('button', { name: '运行实验' }).click();
    assert.equal((await state(page)).sandbox.running, false);
    await page.getByRole('alert').waitFor();
    await page.getByRole('button', { name: '放入Jetson Nano', exact: true }).dragTo(page.locator('.scene-stage'), { targetPosition: { x: 80, y: 80 } });
    assert.ok((await state(page)).sandbox.placed.includes('nano'));
    for (const name of ['水平电机', '上座支架', '俯仰电机', 'IMX477 相机']) await page.getByRole('button', { name: `放入${name}`, exact: true }).click();
    for (const [from, to] of requiredConnections.slice(0, 3)) await connect(page, to, from);
    assert.deepEqual((await state(page)).sandbox.connections, requiredConnections.slice(0, 3).map(([from, to]) => ({ from, to })));
    await page.getByRole('button', { name: '运行实验' }).click();
    assert.ok((await state(page)).sandbox.errors.some(e => e.includes('电源')));
    await page.getByRole('button', { name: '放入电机电源', exact: true }).click();
    for (const [from, to] of requiredConnections.slice(3)) await connect(page, from, to);
    await connect(page, 'nano.uart-pan', 'camera.csi');
    await page.getByRole('button', { name: '运行实验' }).click();
    assert.equal((await state(page)).sandbox.running, false);
    assert.ok((await state(page)).sandbox.errors.some(e => e.includes('不匹配')));
    await shot(page, 'sandbox-validation');
    await page.getByRole('button', { name: '移除连接 Nano · 水平 UART 到 相机 · CSI 输出', exact: true }).click();
    await connect(page, 'nano.uart-pan', 'yaw.uart'); await connect(page, 'camera.csi', 'nano.csi');
  });
  await check('valid sandbox runs, changes virtual imagery, and Stop freezes the complete state', async () => {
    await page.getByRole('button', { name: '运行实验' }).click();
    await page.waitForFunction(() => window.__lesson.getState().sandbox.running && Math.abs(window.__lesson.getState().pan) > 10);
    await page.locator('.snapshot img').waitFor();
    assert.notEqual(await page.locator('.snapshot img').getAttribute('src'), neutralImage);
    await page.waitForTimeout(2200);
    await page.getByRole('button', { name: '停止', exact: true }).click();
    const stopped = await state(page); await page.waitForTimeout(650);
    const after = await state(page);
    assert.deepEqual([after.pan, after.tilt, after.elapsed, after.frame.id], [stopped.pan, stopped.tilt, stopped.elapsed, stopped.frame.id]);
    await shot(page, 'sandbox-complete');
  });
  await check('sandbox reset clears placed parts, wiring, pending endpoints and captured images', async () => {
    await page.getByRole('button', { name: '连接 Nano · 水平 UART', exact: true }).click();
    await page.locator('.pending-wire').waitFor();
    await page.getByRole('button', { name: '复位当前课程' }).click();
    const reset = await state(page);
    assert.deepEqual([reset.pan, reset.tilt, reset.frame, reset.sandbox.placed, reset.sandbox.connections, reset.sandbox.pendingPort], [0, 0, null, [], [], null]);
    assert.equal(await page.locator('.pending-wire').count(), 0);
    assert.equal(await page.locator('.snapshot img').count(), 0);
  });
  await check('continuous chapter changes cancel in-flight operations and keyboard navigation works', async () => {
    await choose(page, 'uart'); await page.getByRole('button', { name: '发送双轴目标' }).click();
    await choose(page, 'tilt'); await page.waitForTimeout(900);
    assert.equal((await state(page)).pan, 0); assert.equal((await state(page)).phase, 'idle');
    await page.locator('[data-lesson=tilt]').focus(); await page.keyboard.press('1');
    assert.equal((await state(page)).lesson, 'assembly');
  });
  await check('all three themes persist, recolor the page, and retain readable text contrast', async () => {
    for (const theme of ['graphite', 'blueprint', 'paper']) {
      await page.getByRole('button', { name: /^切换主题/ }).click();
      assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), theme);
      await checkTheme(page, theme);
      await shot(page, `theme-${theme}`);
    }
    await page.getByRole('button', { name: /^切换主题/ }).click(); await page.reload();
    assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'graphite');
    await page.getByRole('button', { name: /^切换主题/ }).click(); await page.getByRole('button', { name: /^切换主题/ }).click();
  });
  await check('1280 by 720 remains readable and completely frames the gimbal', async () => {
    await page.setViewportSize({ width: 1280, height: 720 }); await choose(page, 'assembly');
    await checkFraming(page, 'desktop1280'); await shot(page, 'desktop-1280');
    for (const theme of ['graphite', 'blueprint', 'paper']) {
      await page.getByRole('button', { name: /^切换主题/ }).click();
      await checkTheme(page, theme);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (theme !== 'paper') await shot(page, `desktop-1280-${theme}`);
    }
  });
  await context.close();

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const phone = await mobile.newPage(); recordErrors(phone); await ready(phone);
  await check('390 px touch layout has no body overflow, with model and lesson visible', async () => {
    assert.deepEqual(await phone.evaluate(() => [innerWidth, document.documentElement.scrollWidth]), [390, 390]);
    await checkFraming(phone, 'mobile390'); await shot(phone, 'mobile-overview');
    const assembly = phone.getByRole('slider', { name: '装配进度' });
    await assembly.focus(); await assembly.press('Home');
    await checkFraming(phone, 'mobileAssemblyTray390'); await shot(phone, 'mobile-assembly-tray');
    await assembly.press('End');
    await choose(phone, 'pan'); const slider = phone.getByRole('slider', { name: '水平角度' });
    await slider.scrollIntoViewIfNeeded(); const box = await slider.boundingBox();
    await slider.tap({ position: { x: box.width * .75, y: box.height / 2 } });
    assert.ok((await state(phone)).pan > 20);
    await choose(phone, 'capture'); await phone.getByRole('button', { name: '采集一帧', exact: true }).tap();
    await waitPhase(phone, 'complete'); await phone.locator('.snapshot img').waitFor(); await shot(phone, 'mobile-capture');
    await choose(phone, 'sandbox'); await checkFraming(phone, 'mobileSandboxTray390');
    await phone.getByRole('button', { name: '放入电机电源', exact: true }).tap();
    assert.ok((await state(phone)).sandbox.placed.includes('power'));
    for (const theme of ['graphite', 'blueprint', 'paper']) {
      await phone.getByRole('button', { name: /^切换主题/ }).tap();
      assert.equal(await phone.evaluate(() => document.documentElement.dataset.theme), theme);
      await checkTheme(phone, theme);
      assert.deepEqual(await phone.evaluate(() => [innerWidth, document.documentElement.scrollWidth]), [390, 390]);
      if (theme !== 'paper') await shot(phone, `mobile-sandbox-${theme}`);
    }
    await shot(phone, 'mobile-sandbox');
  });
  await mobile.close();

  const reduced = await browser.newContext({ viewport: { width: 1280, height: 720 }, reducedMotion: 'reduce' });
  const quiet = await reduced.newPage(); recordErrors(quiet); await ready(quiet);
  await check('reduced motion preserves teaching results without animated travel', async () => {
    await choose(quiet, 'uart'); await quiet.getByRole('button', { name: '发送双轴目标' }).click();
    assert.equal((await state(quiet)).phase, 'complete'); assert.equal((await state(quiet)).pan, 30);
    await choose(quiet, 'capture'); await quiet.getByRole('button', { name: '采集一帧', exact: true }).click();
    assert.equal((await state(quiet)).phase, 'complete'); await quiet.locator('.snapshot img').waitFor();
  });
  await reduced.close();

  const offline = await browser.newContext({ viewport: { width: 1280, height: 850 } });
  const local = await offline.newPage(); recordErrors(local);
  const external = [];
  await offline.route(/^https?:/, route => { external.push(route.request().url()); return route.abort(); });
  await check('standalone HTML loads from file with all network requests blocked', async () => {
    await ready(local, pathToFileURL(resolve(app, 'dist/lesson.html')).href);
    await choose(local, 'capture'); await local.getByRole('button', { name: '采集一帧', exact: true }).click();
    await waitPhase(local, 'complete'); await local.locator('.snapshot img').waitFor();
    assert.deepEqual(external, []); await shot(local, 'standalone-offline');
  });
  await offline.close();
  assert.deepEqual(report.consoleErrors, []);
} catch (error) { failure = error; report.failure = error.stack; console.error(error); }
finally { await writeFile(resolve(evidence, 'browser-report.json'), JSON.stringify(report, null, 2) + '\n'); await browser.close(); }
if (failure) process.exitCode = 1;
else console.log(`${report.checks.length} browser acceptance checks passed; ${report.screenshots.length} screenshots saved.`);
