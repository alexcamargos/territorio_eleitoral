import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const debuggingPort = 9222;

// Launch chrome with swiftshader software WebGL
const chromeProcess = spawn(chromePath, [
  '--headless=new',
  '--remote-debugging-port=' + debuggingPort,
  '--use-gl=angle',
  '--use-angle=swiftshader',
  '--enable-webgl',
  '--ignore-gpu-blocklist',
  '--window-size=1440,900',
  'about:blank'
]);

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getWsUrl() {
  for (let i = 0; i < 20; i++) {
    try {
      const data = await new Promise((resolve, reject) => {
        http.get(`http://127.0.0.1:${debuggingPort}/json/version`, (res) => {
          let body = '';
          res.on('data', chunk => body += chunk);
          res.on('end', () => resolve(JSON.parse(body)));
        }).on('error', reject);
      });
      if (data.webSocketDebuggerUrl) return data.webSocketDebuggerUrl;
    } catch {
      await wait(500);
    }
  }
  throw new Error('Chrome did not start debugger');
}

async function run() {
  try {
    const wsUrl = await getWsUrl();
    const ws = new WebSocket(wsUrl);
    await new Promise(resolve => ws.onopen = resolve);

    let id = 1;
    const callbacks = new Map();
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && callbacks.has(msg.id)) {
        callbacks.get(msg.id)(msg);
        callbacks.delete(msg.id);
      }
    };

    function send(method, params = {}) {
      return new Promise((resolve, reject) => {
        const curId = id++;
        callbacks.set(curId, (msg) => {
          if (msg.error) reject(msg.error);
          else resolve(msg.result);
        });
        ws.send(JSON.stringify({ id: curId, method, params }));
      });
    }

    // Create new target for test
    const { targetId } = await send('Target.createTarget', { url: 'http://localhost:5173/' });
    const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });

    function sendSession(method, params = {}) {
      return new Promise((resolve, reject) => {
        const curId = id++;
        callbacks.set(curId, (msg) => {
          if (msg.error) reject(msg.error);
          else resolve(msg.result);
        });
        ws.send(JSON.stringify({ id: curId, sessionId, method, params }));
      });
    }

    await sendSession('Page.enable');
    await sendSession('Runtime.enable');
    await sendSession('Log.enable');

    const consoleLogs = [];
    ws.addEventListener('message', (event) => {
      const msg = JSON.parse(event.data);
      if (msg.method === 'Runtime.consoleAPICalled') {
        const text = msg.params.args.map(a => a.value ?? a.description).join(' ');
        consoleLogs.push(`[${msg.params.type}] ${text}`);
      }
      if (msg.method === 'Runtime.exceptionThrown') {
        consoleLogs.push(`[EXCEPTION] ${JSON.stringify(msg.params.exceptionDetails)}`);
      }
    });

    console.log('Navigating to http://localhost:5173 ...');
    await sendSession('Page.navigate', { url: 'http://localhost:5173/' });

    // Wait 6 seconds for MapLibre to load and state badges to render
    await wait(6000);

    // Evaluate state badges and MapLibre layers in DOM
    const evalRes = await sendSession('Runtime.evaluate', {
      expression: `
        (() => {
          const map = window.__map;
          const layers = map ? map.getStyle().layers.map(l => ({
            id: l.id,
            type: l.type,
            visibility: map.getLayoutProperty(l.id, 'visibility') ?? 'visible',
            sourceLayer: l['source-layer']
          })) : [];

          const badges = Array.from(document.querySelectorAll('.state-badge')).map(el => ({
            text: el.innerText.trim(),
            className: el.className,
            parentClass: el.parentElement?.className
          }));
          const titles = Array.from(document.querySelectorAll('h1, h2, h3, .topbar, .mode-toggle')).map(el => el.innerText.trim());
          const canvas = document.querySelector('canvas.maplibregl-canvas');
          const point = map ? map.project([-44.5, -18.5]) : null;
          const mgFeatures = (map && point) ? map.queryRenderedFeatures(point).map(f => ({
            layer: f.layer.id,
            type: f.layer.type,
            sourceLayer: f.sourceLayer,
            id: f.id
          })) : [];

          return {
            hasMap: !!map,
            layers,
            mgFeatures,
            badgesCount: badges.length,
            badgesSample: badges.slice(0, 5),
            hasCanvas: !!canvas,
            canvasSize: canvas ? { width: canvas.width, height: canvas.height } : null,
            titles: titles.slice(0, 7),
            consoleErrors: window.__errors || []
          };
        })()
      `,
      returnByValue: true
    });

    console.log('DOM Evaluation Result:\n', JSON.stringify(evalRes.result.value, null, 2));
    console.log('\nConsole Logs:\n', consoleLogs.join('\n'));

    // Capture screenshot
    const screenshot = await sendSession('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync('C:\\WorkspaceHub\\SourceHub\\territorio_eleitoral\\screenshot_validated.png', Buffer.from(screenshot.data, 'base64'));
    console.log('Screenshot saved to screenshot_validated.png');

    ws.close();
  } finally {
    chromeProcess.kill('SIGKILL');
  }
}

run().catch(err => {
  console.error('Test script error:', err);
  chromeProcess.kill('SIGKILL');
  process.exit(1);
});
