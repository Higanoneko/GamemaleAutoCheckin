import {getExtensionApi} from './lib/browser-api.mjs';

const extensionApi = getExtensionApi(globalThis);

document.getElementById('open').addEventListener('click', () => {
  extensionApi.tabs.create({url: extensionApi.runtime.getURL('options.html')});
});
