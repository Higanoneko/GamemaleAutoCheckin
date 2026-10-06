import {CONFIG_NAME, SITE_URL, serializeCookies, buildAccount, parseConfig, renderConfig,
  renderAccountFragment, mergeAccount, configBool} from './lib/config.mjs';
import {normalizePanelUrl, authenticate, readConfig, saveConfig} from './lib/qinglong.mjs';

/** @param {string} id @returns {any} */
const element = (id) => document.getElementById(id);
/** @type {string} */
let cookie = '';
/** @type {import('./lib/qinglong.mjs').Connection|null} */
let connection = null;
/** @type {import('./lib/qinglong.mjs').ConfigSnapshot|null} */
let original = null;
/** @type {import('./lib/config.mjs').Configuration|null} */
let existing = null;
/** @type {string} */
let fragment = '';
/** @type {string|null} */
let pending = null;
let busy = false;

/** @param {string} message @param {boolean} error @returns {void} */
function status(message, error = false) {
  element('status').textContent = message;
  element('status').dataset.error = String(error);
}

/** @returns {void} */
function invalidate() {
  pending = null;
  fragment = '';
  element('preview').value = '';
  element('preview-label').textContent = '配置输入已改变，请重新生成预览。';
  updateButtons();
}

/** @returns {void} */
function disconnect() {
  connection = null; original = null; existing = null;
  element('target').replaceChildren(new Option('新增账户', 'new'));
  invalidate();
}

/** @returns {void} */
function updateButtons() {
  for (const id of ['read-cookie', 'quick-copy', 'quick-fragment', 'generate', 'connect', 'clear']) element(id).disabled = busy;
  element('copy-full').disabled = busy || !element('preview').value;
  element('copy-fragment').disabled = busy || !fragment;
  element('target').disabled = busy || !existing;
  element('merge').disabled = busy || !existing || !cookie;
  element('save').disabled = busy || pending === null;
  for (const id of ['username', 'password', 'questionid', 'answer', 'notify', 'exchange', 'accept', 'complete',
    'panel-url', 'client-id', 'client-secret']) element(id).disabled = busy;
}

/** @param {() => Promise<void>} action @returns {Promise<void>} */
async function run(action) {
  if (busy) return;
  busy = true; updateButtons();
  try { await action(); }
  catch (error) { status(error instanceof Error ? error.message : '操作失败，请重试。', true); }
  finally { busy = false; updateButtons(); }
}

/** @returns {import('./lib/config.mjs').Account} */
function accountPatch() {
  if (!cookie) throw new Error('请先在浏览器登录论坛，再读取 Cookie。');
  const patch = {
    cookie, notify_enabled: element('notify').checked, auto_exchange: element('exchange').checked,
    auto_accept_tasks: element('accept').checked, auto_complete_tasks: element('complete').checked,
  };
  for (const key of ['username', 'password', 'questionid', 'answer']) {
    // Do not trim passwords or answers, or replace existing ones with blank form inputs.
    const value = key === 'username' ? element(key).value.trim() : element(key).value;
    if (value) patch[key] = value;
  }
  return patch;
}

/** @returns {Promise<void>} */
async function collectCookie() {
  cookie = ''; invalidate();
  const result = serializeCookies(await chrome.cookies.getAll({url: SITE_URL}));
  if (!result.hasAuth) {
    element('cookie-status').textContent = '未发现非空 auth Cookie，请在此浏览器登录论坛后重新读取。';
    throw new Error('未发现登录 auth Cookie。仅有 saltkey 或 cf_clearance 不代表已登录。');
  }
  cookie = result.line;
  element('cookie-status').textContent = `已读取 ${result.count} 项 Cookie（包含登录标识）。请运行脚本 --check 验证实际登录。`;
  status('Cookie 已读取，可以生成或复制配置。');
}

/** @param {string} content @param {string} accountFragment @param {string} label @returns {void} */
function preview(content, accountFragment, label) {
  pending = null; fragment = accountFragment;
  element('preview').value = content;
  element('preview-label').textContent = label;
}

/** @returns {void} */
function generate() {
  const account = buildAccount(accountPatch());
  preview(renderConfig({accounts: [account]}), renderAccountFragment(account),
    `单账户完整配置：首次使用可整体粘贴进 ${CONFIG_NAME}。已有配置请选择账户片段或 API 合并。`);
  status('配置已生成。');
}

/** @param {string} text @param {string} message @returns {Promise<void>} */
async function copy(text, message) {
  if (!text) throw new Error('请先生成配置。');
  try { await navigator.clipboard.writeText(text); }
  catch { throw new Error('剪贴板写入失败，请选中预览内容手动复制。'); }
  status(message);
}

element('read-cookie').addEventListener('click', () => run(collectCookie));
element('quick-copy').addEventListener('click', () => run(async () => {
  await collectCookie(); generate();
  await copy(element('preview').value, `完整 YAML 已复制，请粘贴到青龙配置文件 ${CONFIG_NAME}。`);
}));
element('quick-fragment').addEventListener('click', () => run(async () => {
  await collectCookie(); generate();
  await copy(fragment, '账户片段已复制，请粘贴到已有 accounts: 列表下。');
}));
element('generate').addEventListener('click', () => run(async () => generate()));
element('copy-full').addEventListener('click', () => run(() => copy(element('preview').value, '完整配置已复制。')));
element('copy-fragment').addEventListener('click', () => run(() => copy(fragment, '账户片段已复制，请粘贴到已有 accounts: 列表下。')));

element('connect').addEventListener('click', () => run(async () => {
  disconnect();
  const {base, originPattern} = normalizePanelUrl(element('panel-url').value);
  if (!element('client-id').value.trim() || !element('client-secret').value.trim()) {
    throw new Error('请填写 Client ID 和 Client Secret。');
  }
  // Invoke request before any asynchronous work to preserve the browser user gesture.
  const allowed = await chrome.permissions.request({origins: [originPattern]});
  if (!allowed) throw new Error('未授予面板访问权限；仍可使用复制配置功能。');
  status('正在认证并读取青龙配置…');
  const authenticated = await authenticate(fetch, base, element('client-id').value, element('client-secret').value);
  const snapshot = await readConfig(fetch, authenticated);
  const config = parseConfig(snapshot.content);
  connection = authenticated; original = snapshot; existing = config;
  element('target').replaceChildren(new Option('新增账户', 'new'), ...config.accounts.map((account, index) =>
    new Option(`更新账户 ${index + 1} · ${account.username || '未填写用户名'}`, String(index))));
  status(snapshot.exists ? `已读取 ${CONFIG_NAME}，共 ${config.accounts.length} 个账户。选择目标后生成合并预览。`
    : `${CONFIG_NAME} 尚不存在，写入时将自动创建。`);
}));

element('target').addEventListener('change', () => {
  invalidate();
  const index = element('target').value;
  const account = index === 'new' ? buildAccount({cookie: 'placeholder'}) : existing.accounts[Number(index)];
  element('username').value = account.username || '';
  element('password').value = ''; element('answer').value = ''; element('questionid').value = '';
  element('notify').checked = configBool(account.notify_enabled, true);
  element('exchange').checked = configBool(account.auto_exchange ?? account.auto_exchange_enabled, true);
  element('accept').checked = configBool(account.auto_accept_tasks, true);
  element('complete').checked = configBool(account.auto_complete_tasks, true);
});

element('merge').addEventListener('click', () => run(async () => {
  if (!existing) throw new Error('请先连接并读取配置。');
  const index = element('target').value === 'new' ? null : Number(element('target').value);
  const patch = accountPatch();
  const merged = mergeAccount(existing, patch, index);
  const account = merged.accounts[index ?? merged.accounts.length - 1];
  const content = renderConfig(merged);
  preview(content, renderAccountFragment(account),
    `${index === null ? '新增账户' : `更新账户 ${index + 1}`}，写入后共 ${merged.accounts.length} 个账户。检查预览后点击“将预览写入青龙”。注释不保留。`);
  pending = content;
  status('合并预览已生成，可以写入青龙。');
}));

element('save').addEventListener('click', () => run(async () => {
  if (!connection || !original || pending === null) throw new Error('请先生成合并预览。');
  const content = pending;
  pending = null;
  status('正在写入并回读核对配置…');
  try { await saveConfig(fetch, connection, original, content); }
  catch (error) { disconnect(); throw error; }
  original = {exists: true, content}; existing = parseConfig(content);
  // Require a fresh read before adding/updating another account; dropdown must not go stale.
  connection = null; existing = null;
  status(`已写入并回读确认 ${CONFIG_NAME}。请回青龙运行 --check-config 和 --check；继续编辑请重新读取配置。`);
}));

for (const id of ['username', 'password', 'questionid', 'answer', 'notify', 'exchange', 'accept', 'complete']) {
  element(id).addEventListener('input', invalidate);
}
for (const id of ['panel-url', 'client-id', 'client-secret']) element(id).addEventListener('input', disconnect);
element('clear').addEventListener('click', () => {
  cookie = ''; disconnect();
  for (const id of ['username', 'password', 'answer', 'panel-url', 'client-id', 'client-secret', 'questionid']) element(id).value = '';
  element('exchange').checked = false;
  for (const id of ['notify', 'accept', 'complete']) element(id).checked = true;
  element('cookie-status').textContent = '尚未读取 Cookie。';
  status('当前页面凭据与预览已清空。剪贴板内容可手动覆盖。');
});
