import test from 'node:test';
import assert from 'node:assert/strict';
import {getExtensionApi, readForumCookies} from '../lib/browser-api.mjs';

test('prefer Firefox browser namespace over callback-style chrome namespace', async () => {
  const cookies = [{name: 'TVj0_2132_auth', value: 'placeholder', path: '/'}];
  const calls = [];
  const browser = {
    permissions: {request: async (options) => {calls.push(['permission', options]); return true;}},
    cookies: {getAll: async (options) => {calls.push(['cookies', options]); return cookies;}},
  };
  const chrome = {cookies: {getAll: () => {throw new Error('callback API must not be used');}}};
  const reading = readForumCookies(getExtensionApi({browser, chrome}));
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], ['permission', {origins: ['https://www.gamemale.com/*']}]);
  assert.equal(await reading, cookies);
  assert.deepEqual(calls[1], ['cookies', {url: 'https://www.gamemale.com/'}]);
});

test('Chrome MV3 fallback and missing extension environment', () => {
  const chrome = {runtime: {}};
  assert.equal(getExtensionApi({chrome}), chrome);
  assert.throws(() => getExtensionApi({}), /浏览器扩展/);
});

test('denied forum access stops before reading cookies', async () => {
  const api = {
    permissions: {request: async () => false},
    cookies: {getAll: () => {throw new Error('must not read cookies');}},
  };
  await assert.rejects(readForumCookies(api), /论坛 Cookie 访问权限/);
});
