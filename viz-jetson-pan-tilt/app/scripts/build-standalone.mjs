import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = resolve(dirname(fileURLToPath(import.meta.url)), '../dist');
let html = await readFile(resolve(dist, 'index.html'), 'utf8');
const embedded = {};
for (const file of ['gimbal.glb', 'nano.glb', 'supply.glb', 'reference-assembly.png']) {
  const bytes = await readFile(resolve(dist, 'assets', file));
  embedded[file] = `data:${file.endsWith('.png') ? 'image/png' : 'model/gltf-binary'};base64,${bytes.toString('base64')}`;
}
const script = html.match(/<script\b[^>]*src="([^"]+)"[^>]*><\/script>/);
const css = html.match(/<link\b[^>]*href="([^"]+\.css)"[^>]*>/);
if (!script || !css) throw new Error('Expected a single local entry script and stylesheet in the Vite build.');
const javascript = await readFile(resolve(dist, script[1]), 'utf8');
const styles = await readFile(resolve(dist, css[1]), 'utf8');
html = html.replace(css[0], () => `<style>${styles.replace(/<\/style/gi, '<\\/style')}</style>`);
html = html.replace(script[0], () => `<script>window.__LESSON_ASSETS__=${JSON.stringify(embedded)};</script><script type="module">${javascript.replace(/<\/script/gi, '<\\/script')}</script>`);
const favicon = await readFile(resolve(dist, 'favicon.svg'));
html = html.replace('href="./favicon.svg"', `href="data:image/svg+xml;base64,${favicon.toString('base64')}"`);
await writeFile(resolve(dist, 'lesson.html'), html);
console.log(`Standalone lesson: ${(Buffer.byteLength(html) / 1024 / 1024).toFixed(2)} MB, models and code embedded; no server required.`);
