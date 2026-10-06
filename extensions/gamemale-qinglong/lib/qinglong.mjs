import {CONFIG_NAME} from './config.mjs';

/** @typedef {{base: string, originPattern: string}} PanelAddress */
/** @typedef {{base: string, token: string}} Connection */
/** @typedef {{exists: boolean, content: string}} ConfigSnapshot */

/** @param {string} raw @returns {PanelAddress} */
export function normalizePanelUrl(raw) {
  let url;
  try { url = new URL(raw.trim()); } catch { throw new Error('请输入完整青龙地址，例如 https://ql.example.com。'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('青龙地址只支持 HTTP/HTTPS，不能包含登录信息、查询参数或片段。');
  }
  const path = url.pathname.replace(/\/+$/, '').replace(/\/(?:open|api)$/, '');
  return {base: `${url.origin}${path}/open`, originPattern: `${url.origin}/*`};
}

export class QinglongError extends Error {
  /** @param {number} code @param {string} message */
  constructor(code, message) { super(message); this.code = code; }
}

/** @param {number} code @returns {string} */
function failureMessage(code) {
  if (code === 401) return '青龙认证失败或令牌过期，请核对 Client ID / Client Secret 后重新读取。';
  if (code === 403) return '青龙拒绝访问，请到 设置 → 系统设置 → 应用设置，授予应用配置文件权限。';
  return `青龙请求失败（${code}），请检查面板地址、反向代理路径和面板版本。`;
}

/** @param {typeof fetch} fetcher @param {string} url @param {RequestInit} options @returns {Promise<any>} */
async function request(fetcher, url, options = {}) {
  let response;
  try {
    response = await fetcher(url, {
      ...options, credentials: 'omit', redirect: 'error', cache: 'no-store',
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    // Never surface fetch errors, URLs or server messages: auth URL includes the secret.
    throw new QinglongError(0, '无法连接青龙或请求超时，请检查地址、网络、证书和扩展访问权限。');
  }
  if (!response.ok) throw new QinglongError(response.status, failureMessage(response.status));
  let body;
  try { body = await response.json(); }
  catch { throw new QinglongError(0, '青龙返回了非 JSON 内容，请检查地址是否指向面板而非登录页。'); }
  if (!body || body.code !== 200) {
    const code = typeof body?.code === 'number' ? body.code : 0;
    throw new QinglongError(code, failureMessage(code));
  }
  return body.data;
}

/** @param {typeof fetch} fetcher @param {string} base @param {string} clientId @param {string} clientSecret @returns {Promise<Connection>} */
export async function authenticate(fetcher, base, clientId, clientSecret) {
  if (!clientId.trim() || !clientSecret.trim()) throw new Error('请填写 Client ID 和 Client Secret。');
  const query = new URLSearchParams({client_id: clientId.trim(), client_secret: clientSecret.trim()});
  const data = await request(fetcher, `${base}/auth/token?${query}`);
  if (typeof data?.token !== 'string' || !data.token) throw new Error('青龙未返回有效令牌，请检查应用凭据。');
  return {base, token: data.token};
}

/** @param {Connection} connection @returns {Record<string, string>} */
function headers(connection) { return {Authorization: `Bearer ${connection.token}`}; }

/** @param {typeof fetch} fetcher @param {Connection} connection @returns {Promise<ConfigSnapshot>} */
export async function readConfig(fetcher, connection) {
  const files = await request(fetcher, `${connection.base}/configs/files`, {headers: headers(connection)});
  if (!Array.isArray(files) || files.some((file) =>
    typeof file !== 'string' && (!file || typeof file.value !== 'string'))) {
    throw new Error('无法识别青龙配置文件列表，不会创建或覆盖文件。');
  }
  const exists = files.some((file) => (typeof file === 'string' ? file : file.value) === CONFIG_NAME);
  if (!exists) return {exists: false, content: ''};
  let content;
  try {
    content = await request(fetcher, `${connection.base}/configs/detail?${new URLSearchParams({path: CONFIG_NAME})}`, {
      headers: headers(connection),
    });
  } catch (error) {
    if (!(error instanceof QinglongError) || ![404, 410].includes(error.code)) throw error;
    content = await request(fetcher, `${connection.base}/configs/${encodeURIComponent(CONFIG_NAME)}`, {
      headers: headers(connection),
    });
  }
  if (typeof content !== 'string') throw new Error('无法识别青龙返回的配置内容，不会覆盖文件。');
  return {exists: true, content};
}

/** @param {ConfigSnapshot} first @param {ConfigSnapshot} second @returns {boolean} */
export function sameSnapshot(first, second) {
  return first.exists === second.exists && first.content === second.content;
}

/** @param {typeof fetch} fetcher @param {Connection} connection @param {ConfigSnapshot} original @param {string} content @returns {Promise<void>} */
export async function saveConfig(fetcher, connection, original, content) {
  const latest = await readConfig(fetcher, connection);
  if (!sameSnapshot(original, latest)) throw new Error('配置已被其他操作修改，请重新读取并生成预览后再写入。');
  // A timed-out POST can already have reached the panel. Do not retry writes.
  try {
    await request(fetcher, `${connection.base}/configs/save`, {
      method: 'POST', headers: {...headers(connection), 'Content-Type': 'application/json'},
      body: JSON.stringify({name: CONFIG_NAME, content}),
    });
  } catch (error) {
    if (error instanceof QinglongError && error.code !== 0) throw error;
    throw new Error('写入结果未确认，请先到青龙配置文件核对，再重新读取；请勿重复写入。');
  }
  try {
    const saved = await readConfig(fetcher, connection);
    if (!saved.exists || saved.content !== content) throw new Error('mismatch');
  } catch {
    throw new Error('保存请求已发送，但回读未确认，请在青龙配置文件核对后重新读取。');
  }
}
