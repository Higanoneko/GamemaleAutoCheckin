import {load, dump, JSON_SCHEMA} from '../vendor/js-yaml.mjs';

export const CONFIG_NAME = 'GameMale_Config.yaml';
export const SITE_URL = 'https://www.gamemale.com/';

/** @typedef {{name: string, value: string, path?: string}} BrowserCookie */
/** @typedef {Record<string, any>} Account */
/** @typedef {{accounts: Account[], [key: string]: any}} Configuration */

/** @param {BrowserCookie[]} cookies @returns {{line: string, count: number, hasAuth: boolean}} */
export function serializeCookies(cookies) {
  // getAll({url}) already limits domain/path/Secure cookies to the forum homepage.
  // Preserve all cookies, including HttpOnly auth and Cloudflare clearance.
  const ordered = [...cookies].sort((a, b) =>
    (b.path?.length ?? 0) - (a.path?.length ?? 0) || a.name.localeCompare(b.name));
  return {
    line: ordered.map(({name, value}) => `${name}=${value}`).join('; '),
    count: ordered.length,
    hasAuth: ordered.some(({name, value}) => /(?:^|_)auth$/.test(name) && Boolean(value)),
  };
}

/** @param {Account} input @returns {Account} */
export function buildAccount(input) {
  if (typeof input.cookie !== 'string' || !input.cookie.trim()) {
    throw new Error('请先读取已登录论坛的 Cookie。');
  }
  return {
    username: '', password: '', questionid: '0', answer: '',
    notify_enabled: true, auto_exchange: false, auto_accept_tasks: true,
    auto_complete_tasks: true, captcha_max_retries: 3, captcha_precheck: true,
    asset_history_enabled: true, online_time_minutes: 0,
    online_refresh_interval_seconds: 900, task_exclude_ids: [],
    task_exclude_names: [], task_exclude_keywords: [], ...input, cookie: input.cookie.trim(),
  };
}

/** @param {string} text @returns {Configuration} */
export function parseConfig(text) {
  let value;
  try {
    value = load(text, {schema: JSON_SCHEMA});
  } catch {
    // Parser errors contain excerpts of the document, possibly including credentials.
    throw new Error('现有 YAML 格式错误，无法合并；请先在青龙面板修正。');
  }
  if (value == null && !text.trim()) return {accounts: []};
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      !Array.isArray(value.accounts) || value.accounts.some((account) =>
        !account || typeof account !== 'object' || Array.isArray(account))) {
    throw new Error('配置必须是包含 accounts 对象列表的 YAML；不会覆盖现有文件。');
  }
  return value;
}

/** @param {Configuration} config @returns {string} */
export function renderConfig(config) {
  return dump(config, {schema: JSON_SCHEMA, noRefs: true, lineWidth: -1, quotingType: '"', forceQuotes: true});
}

/** @param {Account} account @returns {string} */
export function renderAccountFragment(account) {
  return renderConfig({accounts: [account]}).split('\n').slice(1).join('\n');
}

/** @param {Configuration} config @param {Account} patch @param {number|null} index @returns {Configuration} */
export function mergeAccount(config, patch, index) {
  if (index !== null && (!Number.isInteger(index) || index < 0 || index >= config.accounts.length)) {
    throw new Error('目标账户已改变，请重新读取配置。');
  }
  const accounts = config.accounts.map((account, position) => {
    if (position !== index) return {...account};
    const updated = {...account, ...patch};
    if (Object.hasOwn(account, 'auto_exchange_enabled') && Object.hasOwn(patch, 'auto_exchange')) {
      updated.auto_exchange_enabled = patch.auto_exchange;
    }
    return updated;
  });
  if (index === null) accounts.push(buildAccount(patch));
  return {...config, accounts};
}

/** @param {any} value @param {boolean} fallback @returns {boolean} */
export function configBool(value, fallback) {
  if (value == null) return fallback;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  const normalized = String(value).trim().toLowerCase();
  if (['1', 'true', 'yes', 'y', 'on', '启用', '开启'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'n', 'off', '禁用', '关闭'].includes(normalized)) return false;
  return fallback;
}
