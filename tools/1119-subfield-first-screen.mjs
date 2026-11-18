/** Text-only browser capture for the J first-screen regression. Requires Node 22+ and Chromium. */
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { access, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { parseArgs } from 'node:util';
import { createHash } from 'node:crypto';

const { values: args } = parseArgs({ options: {
  url: { type: 'string', default: 'http://127.0.0.1:5173/?view=subfield' },
  'sql-file': { type: 'string' }, build: { type: 'string' }, out: { type: 'string' },
  dialect: { type: 'string', default: 'spark' }, chrome: { type: 'string' }, 'probe-p0': { type: 'boolean' }, 'probe-keys': { type: 'string' }, 'probe-layout': { type: 'boolean' }, help: { type: 'boolean' },
} });
if (args.help) {
  console.log('node tools/1119-subfield-first-screen.mjs --url URL --build REF --sql-file FILE [--dialect spark|hive] [--chrome PATH] [--out FILE] [--probe-p0] [--probe-keys A|B] [--probe-layout]');
  process.exit(0);
}
if (!args.build || !args['sql-file'] || !['spark', 'hive'].includes(args.dialect)) throw Error('--build and --sql-file are required; dialect must be spark or hive. See --help.');
const url = new URL(args.url);
if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || !['http:', 'https:'].includes(url.protocol)) throw Error('Use a loopback preview URL to keep submitted SQL local.');
const sql = (await readFile(args['sql-file'], 'utf8')).replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
if (!sql.trim()) throw Error('SQL file is empty.');
const chrome = args.chrome || process.env.CHROME_PATH || (process.platform === 'win32'
  ? join(process.env.ProgramFiles || 'C:/Program Files', 'Google/Chrome/Application/chrome.exe') : '/usr/bin/google-chrome');
await access(chrome);
const profile = await mkdtemp(join(tmpdir(), 'j-first-screen-'));
const child = spawn(chrome, ['--headless=new', '--no-first-run', '--no-default-browser-check', '--no-proxy-server', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore', windowsHide: true });
child.on('error', () => {});
let ws;
const deadline = Date.now() + 22000;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, reason) {
  do { const result = await fn(); if (result) return result; await sleep(70); } while (Date.now() < deadline);
  throw Error(`Timed out: ${reason}`);
}
try {
  const port = await until(async () => (await readFile(join(profile, 'DevToolsActivePort'), 'utf8').catch(() => '')).split(/\r?\n/)[0], 'Chrome startup');
  const tab = (await (await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(3000) })).json()).find(item => item.type === 'page');
  if (!tab) throw Error('No browser target');
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); AbortSignal.timeout(3000).addEventListener('abort', () => reject(Error('CDP connection timeout'))); });
  let seq = 0;
  const pending = new Map(), requests = new Map();
  ws.addEventListener('message', event => {
    const { id, result, error, method, params } = JSON.parse(event.data);
    if (id && pending.has(id)) {
      const { complete, reject, timer } = pending.get(id); pending.delete(id); clearTimeout(timer);
      if (error) reject(Error(error.message)); else complete(result);
    } else if (method === 'Network.requestWillBeSent' && params.request.method === 'POST' && new URL(params.request.url).pathname === '/api/sql/subfield-lineage') {
      requests.set(params.requestId, { cdpId: params.requestId, postData: params.request.postData });
    } else if (params && requests.has(params.requestId)) {
      const record = requests.get(params.requestId);
      if (method === 'Network.responseReceived') { record.status = params.response.status; record.headers = Object.fromEntries(Object.entries(params.response.headers).map(([k,v]) => [k.toLowerCase(),v])); }
      if (method === 'Network.loadingFinished') record.done = true;
      if (method === 'Network.loadingFailed') { record.done = true; record.error = params.errorText; }
    }
  });
  const send = (method, params = {}) => new Promise((complete, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { pending.delete(id); reject(Error(`CDP timeout: ${method}`)); }, 6000);
    pending.set(id, { complete, reject, timer }); ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => {
    const evaluated = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (evaluated.exceptionDetails) throw Error(evaluated.exceptionDetails.exception?.description || evaluated.exceptionDetails.text);
    return evaluated.result.value;
  };
  await send('Network.enable', { maxPostDataSize: 1000000 });
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: url.href });
  const click = async (pattern, required = true) => {
    const found = await evaluate(`(() => { const b = [...document.querySelectorAll('.subfield-main button')].find(e => ${pattern}.test(e.innerText.trim()) && e.getClientRects().length && !e.disabled); if (!b) return false; b.click(); return true; })()`);
    if (!found && required) throw Error(`Button not found: ${pattern}`);
  };
  await until(() => evaluate(`!!document.querySelector('.subfield-main #analysis')`), 'J workspace');
  await click('/^编辑 SQL(?: 原文)?$/');
  const writeEditor = async (value) => {
    const editorExpression = `globalThis.__SQL_LINEAGE_MONACO__?.editor?.getEditors?.().find(e => e.getDomNode()?.closest('.subfield-main') && e.getRawOptions().ariaLabel === 'SQL 原文')`;
    await until(() => evaluate(`!!(${editorExpression})`), 'mounted J Monaco editor');
    await evaluate(`(() => { const e = (${editorExpression}); e.executeEdits('j-first-screen', [{ range: e.getModel().getFullModelRange(), text: ${JSON.stringify(value)}, forceMoveMarkers: true }]); })()`);
    await until(() => evaluate(`document.querySelector('.subfield-main .editor-foot')?.innerText.includes('pageMode=ready')`), 'React SQL draft');
  };
  await writeEditor(sql);
  await evaluate(`(() => { const s = document.querySelector('#analysis select'); if (s && s.value !== ${JSON.stringify(args.dialect)}) { s.value = ${JSON.stringify(args.dialect)}; s.dispatchEvent(new Event('change', { bubbles: true })); } })()`);
  await click('/^分析 SQL$/');
  const request = await until(async () => { const failure = await evaluate(`document.querySelector('.subfield-main #error')?.innerText`); if (failure) throw Error(`Browser analysis failed: ${failure}`); return [...requests.values()].find(r => r.done); }, 'successful analysis network operation');
  if (request.error || request.status !== 200) throw Error(`Analysis transport failed: ${request.error || request.status}`);
  const posted = JSON.parse(request.postData || (await send('Network.getRequestPostData', { requestId: request.cdpId })).postData);
  if (posted.sql?.replace(/\r\n/g, '\n').trimEnd() !== sql.trimEnd() || posted.dialect !== args.dialect) throw Error('Browser submitted different SQL or dialect from the fixture.');
  const body = await send('Network.getResponseBody', { requestId: request.cdpId });
  const response = JSON.parse(body.base64Encoded ? Buffer.from(body.body,'base64').toString('utf8') : body.body);
  await until(() => evaluate(`!document.querySelector('#repository-sql-editor') && !!document.querySelector('.j-task-summary, .subfield-main .reports')`), 'analysis result rendered with editor closed');
  const snapshot = await evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve((${measure.toString()})()))))`);
  let rows = format(snapshot, { request, posted, response, sql, url: url.href });
  if (args['probe-p0']) {
    const mode = () => evaluate(`document.querySelector('.canvas-mode [aria-pressed=true]')?.innerText || '未标示'`);
    const count = () => evaluate(`document.querySelectorAll('.subfield-main button.canvas-node').length`);
    await click('/^JSON (排查|分支|依赖)$/', false);
    await until(() => count(), 'graph nodes after opening JSON view');
    await evaluate(`(() => { const node = [...document.querySelectorAll('.subfield-main button.canvas-node')].find(e => e.innerText.includes('hit')) || document.querySelector('.subfield-main button.canvas-node'); node.click(); })()`);
    let lines = ['', '[P0] 历史缺陷复测（以下操作在默认首屏截取后执行）'];
    const widths = [];
    for (const width of [1440,1280,1024]) {
      await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      const area = await evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => {
        const body = document.querySelector('.subfield-detail-body');
        const h = body?.querySelector('h3');
        const details = [...(body?.querySelectorAll(':scope > details') || [])];
        resolve(h && details.length ? {display: getComputedStyle(body).display, heading: Math.round(h.getBoundingClientRect().width), blocks: details.map(e => Math.round(e.getBoundingClientRect().width))} : null);
      })))`);
      widths.push(area);
      lines.push(`P0-1 | ${width}x900 | ${area ? `display ${area.display} | 标题 ${area.heading}px | 证据条目 ${area.blocks.join(',')}px` : '未找到有内容的标题和证据条目'}`);
    }
    lines.push(`P0-1 | ${widths.some(x => x && Math.min(x.heading,...x.blocks) < 120) ? '复现证据窄列' : widths.every(Boolean) ? '未复现证据窄列' : '证据不全'}`);
    const originalMode = await mode(), originalNodes = await count();
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    const latest = new Set(requests.keys());
    await click('/^分析 SQL$/');
    const replay = await until(() => [...requests.values()].find(r => !latest.has(r.cdpId) && r.done), 'second analysis response');
    await until(() => evaluate(`!document.querySelector('.subfield-main [role=status].running') && !!document.querySelector('.j-task-summary, .subfield-main .reports')`), 'second analysis rendered');
    const replayNodes = await count();
    lines.push(`P0-2 | 重新分析前 ${originalMode} / ${originalNodes} 节点 | HTTP ${replay.status} | 重新分析后 ${await mode()} / ${replayNodes} 节点 | ${replay.status !== 200 ? '复测请求未成功' : replayNodes ? '未复现成功空图' : '复现成功空图'}`);
    rows += lines.join('\n') + '\n';
  }
  if (args['probe-keys']) {
    const useA = args['probe-keys'] === 'A';
    if (!useA && args['probe-keys'] !== 'B') throw Error('--probe-keys expects A or B');
    const sourceName = useA ? 'lab.media_events' : 'lab.src';
    const columnName = useA ? 'event_payload' : 'j';
    const outputName = useA ? 'media_id' : 'hit';
    const run = async (path, expected) => {
      await evaluate(`(() => {
        const e = document.querySelector('form:has(#j-candidate-path) input');
        if (!e) throw Error('Candidate key form not found');
        if (e.value !== ${JSON.stringify(sourceName)}) {
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, ${JSON.stringify(sourceName)});
          e.dispatchEvent(new Event('input', { bubbles: true }));
        }
      })()`);
      const prior = new Set(requests.keys());
      await evaluate(`(() => {
        const form = document.querySelector('form:has(#j-candidate-path)');
        if (!form) throw Error('Candidate key form not found');
        const set = (e, value) => {
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(e, value);
          e.dispatchEvent(new Event('input', { bubbles: true }));
        };
        const [,column,key] = form.querySelectorAll('input');
        if (column.value !== ${JSON.stringify(columnName)}) set(column,${JSON.stringify(columnName)});
        set(key,${JSON.stringify(path)});
        const range = document.querySelector('.j-advanced-review'); range.open = true;
        const target = [...range.querySelectorAll('input[type=checkbox]')].find(e => e.closest('label').textContent.trim().startsWith(${JSON.stringify(outputName + '（')}));
        if (!target) throw Error('chosen output checkbox not found');
        if (!target.checked) target.click();
      })()`);
      await click('/^检查键$/');
      const review = await until(() => [...requests.values()].find(r => !prior.has(r.cdpId) && r.done), `key review API ${path}`);
      if (review.status !== 200) throw Error(`Key review HTTP ${review.status}: ${path}`);
      const postedReview = JSON.parse(review.postData || (await send('Network.getRequestPostData', { requestId: review.cdpId })).postData);
      const key = path.slice(2);
      if (!postedReview.candidate_keys?.some(c => c.source === sourceName && c.column === columnName && c.keys.includes(key)) || postedReview.protected_outputs?.length !== 1) throw Error(`Unexpected review request: ${path}`);
      const rendered = await until(() => evaluate(`(() => {
        const e = document.querySelector('.j-path-result');
        const chip = e?.querySelector('.j-path-chip');
        if (!chip) return null;
        const s = getComputedStyle(chip);
        return [chip.innerText.trim(), e.innerText.replace(/\\s+/g,' ').trim(), s.color, s.backgroundColor, s.borderTopStyle+' '+s.borderTopColor];
      })()`), `rendered key status ${path}`);
      if (rendered[0] !== expected) throw Error(`Expected ${expected} for ${path}; got ${rendered[1]}`);
      const resource = await send('Network.getResponseBody', { requestId: review.cdpId });
      const payload = JSON.parse(resource.base64Encoded ? Buffer.from(resource.body,'base64').toString('utf8') : resource.body);
      const assessment = payload.review?.candidate_assessment;
      const entry = assessment?.entries?.find(e => e.key === key);
      return `${outputName} | ${path} | HTTP ${review.status} | ${entry?.status || assessment?.status}${assessment?.reason ? ' / '+assessment.reason : ''} | ${rendered.join(' | ')} | ${payload.request_id || `浏览器网络记录 ${review.cdpId}`}`;
    };
    rows += ['','[自定义键] 实际浏览器请求和渲染', ...(useA ? [await run('$.media_id','已看到读取'), await run('$.example_unseen_key','本次未见读取')] : [await run('$.a','暂不能判断')]),''].join('\n');
  }
  if (args['probe-layout']) {
    const settled = expression => evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(${expression}))))`);
    const layout = String.raw`(() => {
      const form = document.querySelector('form:has(#j-candidate-path)');
      const rect = e => { const r = e.getBoundingClientRect(); return [r.x,r.y,r.width,r.height].map(Math.round); };
      const first = form?.querySelectorAll(':scope > label');
      if (!first?.length) throw Error('Candidate form not found');
      return {
        horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        form: rect(form), controls: [...form.querySelectorAll('input,button')].map(rect),
        summary: rect(document.querySelector('.j-task-summary')),
        tree: rect(document.querySelector('.json-tree-pane')),
        detail: rect(document.querySelector('.inspector')),
      };
    })()`;
    rows += '\n[布局] 视口 | 页面横向溢出 px | 表单/输入/摘要/枝干树/详情坐标 x,y,w,h\n';
    for (const width of [1440,768,390]) {
      await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false });
      rows += `${width}x900 | ${JSON.stringify(await settled(layout))}\n`;
    }
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    const resize = async (label, area, editor) => {
      const rule = JSON.stringify(`${area} button.splitter`);
      const read = () => settled(`(() => {
        const button = document.querySelector(${rule});
        const root = document.querySelector(${JSON.stringify(editor)});
        return [button?.getAttribute('aria-label'), Math.round(root?.getBoundingClientRect().width || 0), button?.nextElementSibling?.textContent];
      })()`);
      await until(() => evaluate(`!!document.querySelector(${rule})?.getClientRects().length`), `${label} splitter visible`);
      const before = await read();
      await evaluate(`document.querySelector(${rule}).focus({preventScroll: true})`);
      await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
      await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
      const after = await read();
      if (!before[1] || after[1] <= before[1]) throw Error(`${label} ArrowRight did not grow the SQL editor: ${before[1]} → ${after[1]}`);
      rows += `${label} | ${before[0]} | ArrowRight | ${before[1]}px → ${after[1]}px | ${before[2]} → ${after[2]}\n`;
    };
    await click('/^编辑 SQL(?: 原文)?$/');
    await resize('J', '.j-analysis-area', '#repository-sql-editor');
    await evaluate(`document.querySelector('nav button[aria-label="Workbench"]').click()`);
    await resize('W', '#workspace', '#workspace > .editor');
  }
  if (args.out) await writeFile(args.out, rows, 'utf8'); else process.stdout.write(rows);
} finally {
  ws?.close();
  if (child.exitCode === null && child.pid) { const exited = once(child, 'exit'); child.kill(); await Promise.race([exited, sleep(800)]); }
  await rm(profile, { recursive: true, force: true, maxRetries: 3 }).catch(() => {});
}

function measure() {
  const viewport = { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
  const root = document.querySelector('.subfield-main');
  const compact = text => text.replace(/\s+/g, ' ').trim();
  const parentDetails = e => { const d = e?.closest('details'); return d && d !== e && (e === d.querySelector(':scope > summary') || d.querySelector(':scope > summary')?.contains(e)) ? parentDetails(d.parentElement) : d; };
  const box = (e, raw = e.getBoundingClientRect()) => {
    let {left,top,right,bottom} = raw;
    for (let p = e; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (p.hidden || s.display === 'none' || ['hidden','collapse'].includes(s.visibility) || Number(s.opacity) === 0) return null;
      if (p !== e && p !== document.body && p !== document.documentElement) {
        const r = p.getBoundingClientRect();
        if (s.overflowX !== 'visible') { left = Math.max(left,r.left+p.clientLeft); right = Math.min(right,r.left+p.clientLeft+p.clientWidth); }
        if (s.overflowY !== 'visible') { top = Math.max(top,r.top+p.clientTop); bottom = Math.min(bottom,r.top+p.clientTop+p.clientHeight); }
      }
    }
    for (let d = parentDetails(e); d; d = parentDetails(d.parentElement)) if (!d.open) return null;
    left = Math.max(left,viewport.left); top = Math.max(top,viewport.top); right = Math.min(right,viewport.right); bottom = Math.min(bottom,viewport.bottom);
    return right > left && bottom > top ? {left,top,right,bottom} : null;
  };
  const nav = [...document.querySelectorAll('header, nav')].filter(e => !root.contains(e));
  const inScope = e => root.contains(e) || nav.some(n => n.contains(e));
  const text = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const e = n.parentElement, label = compact(n.nodeValue);
    if (!label || !inScope(e) || e.closest('script, style, option, title')) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    if ([...range.getClientRects()].some(r => box(e,r))) text.push(label);
    if (text.length === 40) break;
  }
  const control = [...document.querySelectorAll('button, input, select, textarea, summary, a[href], [role=button], [role=separator]')].filter(inScope).map(e => {
    let closed = [];
    for (let d = parentDetails(e); d; d = parentDetails(d.parentElement)) if (!d.open) closed.unshift(compact(d.querySelector(':scope > summary')?.textContent || '详情'));
    const type = e.type && e.localName === 'input' ? e.type : e.getAttribute('role') || e.localName;
    return { type, label: compact(e.getAttribute('aria-label') || [...(e.labels || [])].map(l => l.innerText || l.textContent).join(' ') || e.innerText || e.textContent || e.title || e.id), visible: !!box(e), disabled: e.matches(':disabled,[aria-disabled=true]'), closed };
  }).filter(x => x.label || x.type === 'separator');
  const areas = Object.entries({ '工作区': '.workbench.shell', '血缘画布': '.work', '枝干树': '.json-tree-pane', '依赖链': '.json-flow-pane', '详情侧栏': '.inspector', '任务摘要': '.j-task-summary', '检查键': '.j-candidate-form, form:has(#j-candidate-path)', '状态条': '.subfield-status' }).map(([label,sel]) => {
    const e = root.querySelector(sel), b = e && box(e), r = e?.getBoundingClientRect();
    return [label, e ? '渲染' : '未渲染', r && [r.x,r.y,r.width,r.height].map(Math.round).join(','), b && ((b.right-b.left)*(b.bottom-b.top)/(innerWidth*innerHeight)*100).toFixed(1)];
  });
  const palette = [];
  for (const e of root.querySelectorAll('.json-tree-row, .canvas-node.uncertain, .j-path-chip, [data-path-state], [data-status]')) {
    if (!box(e)) continue;
    const s = getComputedStyle(e), mark = getComputedStyle(e, '::before');
    const key = [e.getAttribute('data-path-state') || e.getAttribute('data-status') || e.classList.item(0), s.color, s.backgroundColor, `${s.borderTopStyle} ${s.borderTopColor}`, s.outlineStyle, mark.content].join(' | ');
    if (!palette.some(p => p.startsWith(key + ' |'))) palette.push(`${key} | ${compact(e.innerText || e.textContent)}`);
  }
  const details = [...root.querySelectorAll('details')].map(d => {
    const h = d.querySelector(':scope > summary');
    return [compact(h?.textContent || ''), d.open ? '开' : '关', h && box(h) ? '首屏可见' : '首屏不可见', d.querySelector('ol,ul')?.children.length ?? '未报告'];
  });
  const proof = [...root.querySelectorAll('pre.sql mark, .j-first-evidence mark, .j-evidence mark, [data-evidence-span]')].find(e => box(e));
  const findings = {
    summary: root.querySelector('.j-task-summary'), customKey: root.querySelector('#j-candidate-path'),
    tree: root.querySelector('.json-tree-pane'), proof,
  };
  return { viewport: [innerWidth,innerHeight], windowScroll: [scrollX,scrollY], text, control, areas, palette, details,
    facts: Object.fromEntries(Object.entries(findings).map(([k,v]) => [k, v ? { visible: !!box(v), text: compact(v.innerText || v.textContent).slice(0,300) } : null])),
    proof: proof ? compact(proof.parentElement?.previousElementSibling?.textContent || '') : null,
  };
}

function format(s, {request, posted, response, sql, url}) {
  const sourceId = response.request_id || request.headers?.['x-request-id'];
  const tidy = text => String(text ?? '').replace(/[\r\n]+/g,' ').slice(0,240);
  const sha = createHash('sha256').update(sql).digest('hex');
  const list = (rows, max) => rows.length > max ? [...rows.slice(0,max), `… 另 ${rows.length-max} 条`] : rows;
  return [
    '# 首屏结构化快照（分析后，未手动展开详情或切换视图）', 'snapshot: subfield-first-screen',
    `build: ${args.build}`, `preview: ${url}`, `viewport: ${s.viewport.join('x')} CSS px; window scroll: ${s.windowScroll.join(',')}`,
    `request-id: ${sourceId || `未由服务公开（浏览器网络记录 ${request.cdpId}）`}`, `request: HTTP ${request.status} | ${posted.dialect} | SQL sha256 ${sha}`,
    `request fields: ${Object.keys(posted).sort().join(', ')} | candidate_keys=${'candidate_keys' in posted ? '已提交' : '未提交'} | protected_outputs=${'protected_outputs' in posted ? '已提交' : '未提交'}`,
    `response keys: ${Object.keys(response).sort().join(', ')} | 使用点 ${response.uses?.length ?? '未提供'} | 待确认 ${response.unknowns?.length ?? '未提供'}`,
    '', '[1] 首屏可见文本（DOM 顺序，最多 40 个文本片段）', ...s.text,
    '', '[2] 交互入口（类型 | 文案 | 首屏可见性 | 状态 | 前置）',
    ...list(s.control.sort((a,b) => Number(b.visible)-Number(a.visible)).map(c => `${c.type} | ${tidy(c.label)} | ${c.visible ? '可见' : '不可见'} | ${c.disabled ? '禁用' : '启用'} | ${c.closed.length ? `展开 ${c.closed.join(' / ')}` : c.visible ? '无' : '在当前滚动区域外或被隐藏'}`), 48),
    ...Object.entries(s.facts).map(([k,v]) => `${k}: ${v ? `${v.visible ? '首屏可见' : '首屏不可见'} ${tidy(v.text)}` : '未渲染'}`),
    `首条 SQL 证据位置: ${s.proof || '首屏未呈现可核对的高亮片段'}`,
    '', '[3] 区域占用（DOM 左上 x,y,宽,高；可见交集 / 整个视口面积；嵌套区域不相加）',
    ...s.areas.map(([label,state,r,area]) => `${label} | ${state} | ${r ?? '—'} | ${area ?? '0.0'}%`),
    '', '[4] 状态样式（实际计算值 | 文案）', ...(s.palette.length ? list(s.palette,15) : ['首屏无匹配的可见分支状态节点']),
    '', '[5] 折叠项（标题 | 状态 | 首屏可见性 | 已渲染列表条目数）', ...list(s.details.map(row => row.map(tidy).join(' | ')),24),
    '',
  ].join('\n');
}
