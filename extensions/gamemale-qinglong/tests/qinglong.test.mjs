import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePanelUrl, authenticate, readConfig, saveConfig} from '../lib/qinglong.mjs';
import {CONFIG_NAME} from '../lib/config.mjs';

const connection = {base: 'https://ql.example.com/prefix/open', token: 'placeholder'};
/** @param {any} data @param {number} code @returns {Response} */
function response(data, code = 200) { return Response.json({code, data}); }
/** @param {Array<Response|Error>} responses @returns {{calls: any[], fetcher: typeof fetch}} */
function fakeFetch(responses) {
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({url, options});
    assert.ok(responses.length, 'unexpected request');
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return next;
  };
  return {calls, fetcher};
}
/** @returns {Response} */
const list = () => response([{title: CONFIG_NAME, value: CONFIG_NAME}]);

test('panel address supports proxy prefixes and trailing API paths', () => {
  for (const raw of ['https://ql.example.com/prefix/', 'https://ql.example.com/prefix/open/',
    'https://ql.example.com/prefix/api']) {
    assert.deepEqual(normalizePanelUrl(raw), {base: connection.base, originPattern: 'https://ql.example.com/*'});
  }
  assert.deepEqual(normalizePanelUrl('http://127.0.0.1:5700'), {
    base: 'http://127.0.0.1:5700/open', originPattern: 'http://127.0.0.1/*',
  });
  for (const raw of ['ql.example.com', 'file:///tmp/config', 'https://user:pass@ql.example.com',
    'https://ql.example.com/?secret=placeholder', 'https://ql.example.com/#hash']) assert.throws(() => normalizePanelUrl(raw));
});

test('authentication encodes credentials and omits browser sessions and redirects', async () => {
  const fake = fakeFetch([response({token: 'placeholder'})]);
  assert.deepEqual(await authenticate(fake.fetcher, connection.base, 'ID+placeholder', 'SECRET&placeholder'), connection);
  const url = new URL(fake.calls[0].url);
  assert.equal(url.searchParams.get('client_secret'), 'SECRET&placeholder');
  assert.equal(url.searchParams.get('client_id'), 'ID+placeholder');
  assert.equal(fake.calls[0].options.credentials, 'omit');
  assert.equal(fake.calls[0].options.redirect, 'error');
  assert.equal(fake.calls[0].options.cache, 'no-store');
  assert.ok(fake.calls[0].options.signal instanceof AbortSignal);
  await assert.rejects(authenticate(fake.fetcher, connection.base, '', ''), /Client/);
});

test('read uses files and detail, with narrowly limited legacy fallback', async () => {
  const content = 'accounts: []\n';
  const fake = fakeFetch([list(), response(content)]);
  assert.deepEqual(await readConfig(fake.fetcher, connection), {exists: true, content});
  assert.ok(fake.calls[1].url.includes('/configs/detail?path=GameMale_Config.yaml'));
  assert.equal(fake.calls[1].options.headers.Authorization, 'Bearer placeholder');
  const old = fakeFetch([list(), response(null, 404), response(content)]);
  assert.equal((await readConfig(old.fetcher, connection)).content, content);
  assert.ok(old.calls[2].url.endsWith('/configs/GameMale_Config.yaml'));
  const forbidden = fakeFetch([list(), response(null, 403)]);
  await assert.rejects(readConfig(forbidden.fetcher, connection), /配置文件权限/);
  assert.equal(forbidden.calls.length, 2);
});

test('missing file is distinguished from unreadable or unrecognized file', async () => {
  const fake = fakeFetch([response([])]);
  assert.deepEqual(await readConfig(fake.fetcher, connection), {exists: false, content: ''});
  for (const responses of [[response(null, 403)], [response({unknown: true})],
    [response([null])], [list(), response({content: 'unknown format'})]]) {
    const invalid = fakeFetch(responses);
    await assert.rejects(readConfig(invalid.fetcher, connection));
    assert.ok(!invalid.calls.some(({options}) => options.method === 'POST'));
  }
});

test('save checks original, sends exact filename/content and verifies readback', async () => {
  const original = {exists: true, content: 'accounts: []\n'};
  const content = 'accounts:\n  - cookie: "auth=placeholder"\n';
  const fake = fakeFetch([list(), response(original.content), response(undefined), list(), response(content)]);
  await saveConfig(fake.fetcher, connection, original, content);
  assert.equal(fake.calls[2].options.method, 'POST');
  assert.deepEqual(JSON.parse(fake.calls[2].options.body), {name: CONFIG_NAME, content});
  assert.ok(fake.calls[2].url.endsWith('/configs/save'));
});

test('save creates missing file and refuses conflicting edits or newly created files', async () => {
  const content = 'accounts: []\n';
  const created = fakeFetch([response([]), response(undefined), list(), response(content)]);
  await saveConfig(created.fetcher, connection, {exists: false, content: ''}, content);
  for (const original of [{exists: true, content: 'old'}, {exists: false, content: ''}]) {
    const changed = fakeFetch([list(), response('changed')]);
    await assert.rejects(saveConfig(changed.fetcher, connection, original, content), /其他操作修改/);
    assert.equal(changed.calls.length, 2);
  }
});

test('write timeouts are not retried and do not claim success', async () => {
  const fake = fakeFetch([response([]), new Error('secret in URL SECRET_PLACEHOLDER')]);
  await assert.rejects(saveConfig(fake.fetcher, connection, {exists: false, content: ''}, 'accounts: []'), /写入结果未确认/);
  assert.equal(fake.calls.length, 2);
});

test('save readback failures do not claim confirmed success', async () => {
  const fake = fakeFetch([response([]), response(undefined), list(), response('different')]);
  await assert.rejects(saveConfig(fake.fetcher, connection, {exists: false, content: ''}, 'accounts: []'), /回读未确认/);
});

test('auth, permission, non-JSON and network errors redact all external messages', async () => {
  for (const reply of [Response.json({code: 401, message: 'SECRET_PLACEHOLDER'}),
    Response.json({code: 403, message: 'SECRET_PLACEHOLDER'}),
    new Response('SECRET_PLACEHOLDER', {status: 502}), new Response('SECRET_PLACEHOLDER'),
    new Error('SECRET_PLACEHOLDER')]) {
    const fake = fakeFetch([reply]);
    await assert.rejects(authenticate(fake.fetcher, connection.base, 'id', 'SECRET_PLACEHOLDER'),
      (error) => !error.message.includes('SECRET_PLACEHOLDER'));
  }
});
