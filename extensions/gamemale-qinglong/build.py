"""Build browser-specific archives from shared, explicitly allowed files."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Dict
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SOURCE_DIR = Path(__file__).resolve().parent
RUNTIME_FILES = (
    'popup.html', 'popup.js', 'options.html', 'options.mjs', 'style.css',
    'lib/config.mjs', 'lib/qinglong.mjs', 'lib/browser-api.mjs',
    'vendor/js-yaml.mjs', 'vendor/js-yaml.LICENSE', 'vendor/README.md',
    'README.md', 'PRIVACY.md',
)


def build_manifest(manifest: Dict[str, Any], browser: str) -> Dict[str, Any]:
    """Return a separate manifest without mutating shared Chromium configuration."""
    if browser not in ('chrome', 'firefox'):
        raise ValueError('Unsupported browser')
    result = deepcopy(manifest)
    if browser == 'firefox':
        result['browser_specific_settings'] = {
            'gecko': {
                'id': 'gamemale-qinglong@gamemaleautocheckin',
                'strict_min_version': '140.0',
                'data_collection_permissions': {
                    'required': ['authenticationInfo', 'websiteContent'],
                },
            },
            'gecko_android': {'strict_min_version': '142.0'},
        }
    return result


def build_archive(source: Path, output: Path, browser: str) -> Path:
    """Package known source files, with a root manifest and stable ZIP metadata."""
    manifest = build_manifest(json.loads((source / 'manifest.json').read_text(encoding='utf-8')), browser)
    files = {name: (source / name).read_bytes() for name in RUNTIME_FILES}
    files['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='Build GameMale Qinglong extension packages')
    parser.add_argument('--browser', choices=('chrome', 'firefox', 'all'), default='all')
    parser.add_argument('--output-dir', type=Path, default=SOURCE_DIR.parents[1] / 'dist')
    args = parser.parse_args()
    browsers = ('chrome', 'firefox') if args.browser == 'all' else (args.browser,)
    for browser in browsers:
        filename = 'gamemale-qinglong.zip' if browser == 'chrome' else 'gamemale-qinglong-firefox.zip'
        path = build_archive(SOURCE_DIR, args.output_dir / filename, browser)
        print(f'{browser}: {path.resolve()}')


if __name__ == '__main__':
    main()
