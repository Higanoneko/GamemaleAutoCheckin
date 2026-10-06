import {SITE_URL} from './config.mjs';

/** @param {{browser?: any, chrome?: any}} environment @returns {any} */
export function getExtensionApi(environment) {
  // Firefox exposes promise-returning APIs under browser; older Chrome uses chrome.
  const api = environment.browser ?? environment.chrome;
  if (!api) throw new Error('请通过浏览器扩展打开配置助手。');
  return api;
}

/** @param {any} api @returns {Promise<import('./config.mjs').BrowserCookie[]>} */
export async function readForumCookies(api) {
  // Firefox MV3 host access can be revoked independently of the cookies permission.
  // Request synchronously from the click handler, before the first await.
  const allowed = await api.permissions.request({origins: [`${new URL(SITE_URL).origin}/*`]});
  if (!allowed) throw new Error('未授予论坛 Cookie 访问权限，请允许扩展访问 GameMale 后重新读取。');
  return api.cookies.getAll({url: SITE_URL});
}
