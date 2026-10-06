import test from 'node:test';
import assert from 'node:assert/strict';
import {buildAccount, parseConfig, renderConfig, renderAccountFragment, mergeAccount,
  serializeCookies, configBool} from '../lib/config.mjs';

test('complete cookies retain HttpOnly auth and clearance without mutating input', () => {
  const cookies = [
    {name: 'cf_clearance', value: 'placeholder', path: '/'},
    {name: 'TVj0_2132_auth', value: 'placeholder', path: '/', httpOnly: true},
    {name: 'extra', value: 'placeholder', path: '/'},
  ];
  const copy = structuredClone(cookies);
  const result = serializeCookies(cookies);
  assert.equal(result.hasAuth, true);
  assert.equal(result.count, 3);
  assert.match(result.line, /TVj0_2132_auth=placeholder/);
  assert.match(result.line, /extra=placeholder/);
  assert.deepEqual(cookies, copy);
  for (const list of [[], [{name: 'TVj0_2132_saltkey', value: 'placeholder'}],
    [{name: 'cf_clearance', value: 'placeholder'}], [{name: 'TVj0_2132_auth', value: ''}]]) {
    assert.equal(serializeCookies(list).hasAuth, false);
  }
});

test('YAML round trip escapes credentials and preserves string/numeric/boolean types', () => {
  const account = buildAccount({cookie: ' auth=placeholder; extra="quoted"; path=\\test ',
    username: 'true', password: ' # : " \\ \n 密码 ', questionid: '0', answer: '0123'});
  assert.equal(account.cookie, 'auth=placeholder; extra="quoted"; path=\\test');
  const serialized = renderConfig({accounts: [account]});
  assert.deepEqual(parseConfig(serialized), {accounts: [account]});
  assert.equal(account.auto_exchange, false);
  assert.equal(typeof account.online_time_minutes, 'number');
  assert.equal(typeof account.questionid, 'string');
  assert.throws(() => buildAccount({cookie: ''}), /Cookie/);
});

test('account fragment appends to an existing accounts list with correct indentation', () => {
  const account = buildAccount({cookie: 'auth=placeholder', username: '账户2'});
  const fragment = renderAccountFragment(account);
  assert.ok(!fragment.includes('accounts:'));
  const combined = 'accounts:\n  - cookie: "auth=placeholder1"\n' + fragment;
  assert.equal(parseConfig(combined).accounts.length, 2);
  assert.deepEqual(parseConfig(combined).accounts[1], account);
});

test('merging updates only selected account, retaining global and unexposed settings', () => {
  const config = parseConfig(`cloudflare:\n  solver: "capsolver"\n  api_key: "placeholder"\naccounts:\n  - cookie: "auth=placeholder1"\n    username: "账户1"\n    password: "placeholder"\n    online_time_minutes: 90\n    task_exclude_ids: ["25"]\n    auto_exchange_enabled: true\n  - cookie: "auth=placeholder2"\n    username: "账户2"\n`);
  const copy = structuredClone(config);
  const merged = mergeAccount(config, {cookie: 'auth=updated', auto_exchange: false}, 0);
  assert.deepEqual(config, copy);
  assert.deepEqual(merged.cloudflare, config.cloudflare);
  assert.deepEqual(merged.accounts[1], config.accounts[1]);
  assert.equal(merged.accounts[0].password, 'placeholder');
  assert.equal(merged.accounts[0].online_time_minutes, 90);
  assert.deepEqual(merged.accounts[0].task_exclude_ids, ['25']);
  assert.equal(merged.accounts[0].auto_exchange_enabled, false);
  assert.deepEqual(parseConfig(renderConfig(merged)), merged);
});

test('append is explicit; a repeated username does not silently replace an account', () => {
  const config = {accounts: [{cookie: 'auth=placeholder', username: '账户1'}]};
  const merged = mergeAccount(config, {cookie: 'auth=updated', username: '账户1'}, null);
  assert.equal(merged.accounts.length, 2);
  assert.deepEqual(merged.accounts[0], config.accounts[0]);
  assert.equal(merged.accounts[1].auto_exchange, false);
  for (const index of [-1, 1, 0.5, NaN]) assert.throws(() => mergeAccount(config, {}, index));
});

test('invalid config fails closed and never includes credentials in parser errors', () => {
  for (const text of ['[]', 'accounts: wrong', 'accounts: [false]', 'accounts: [null]',
    'password: placeholder', 'accounts: [\npassword: SECRET_PLACEHOLDER',
    'accounts: []\naccounts: []']) {
    assert.throws(() => parseConfig(text), (error) => !error.message.includes('SECRET_PLACEHOLDER'));
  }
  assert.deepEqual(parseConfig(''), {accounts: []});
});

test('existing boolean aliases accept the same common text values as the script', () => {
  for (const value of [false, 'false', '0', 'off', '关闭', 0]) assert.equal(configBool(value, true), false);
  for (const value of [true, 'true', '1', 'on', '开启', 1]) assert.equal(configBool(value, false), true);
  assert.equal(configBool(undefined, true), true);
});
