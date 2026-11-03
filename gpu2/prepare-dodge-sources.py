#!/usr/bin/env python3
"""Restore the exported GPU2 trees at their original bases without touching existing inputs."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
# Auxiliary pins come from Data A Live's turnip.yml at DAL_COMMIT; the three
# exported diffs already include its adaptations and UniXNU's prerequisite patches.
DAL_COMMIT = '6ee446d370d6f9b847f1d85ad539ab721a2e9ae8'
SOURCES = {
    'metal2vulkan': ('https://github.com/steelbrain/metal2vulkan.git',
                     '720ef1ce9ae2a2068999a8675717418b9416283e', 'metal2vulkan-720ef1c-dada.patch'),
    'nativemetal': ('https://github.com/UniXNU/NativeMetal.git',
                    'c6d29caad6d880cc8204ebe3bc34d77479a3255d', 'nativemetal-dada.patch'),
    'mesa': ('https://chromium.googlesource.com/external/gitlab.freedesktop.org/mesa/mesa',
             '85fda3b36405bcaea8bffc64aa4f2651dc90770d', 'mesa-85fda3b-dada.patch'),
    'nativeadreno': ('https://github.com/UniXNU/NativeAdreno.git',
                     'b686b9054f57d393c80195b82568a09f8ca106a2', None),
    'adrenopm4': ('https://github.com/UniXNU/AdrenoPM4.git',
                  '445f8fe6d115738352b9d78dc70af6d61aa7f62f', None),
    'NativeMobileDisplay': ('https://github.com/UniXNU/NativeMobileDisplay.git',
                            '8666a9950c9699b368931d18cac92c0fdb2ce9c0', None),
    'unixnu': ('https://github.com/UniXNU/UniXNU.git',
               '1a01c2afa197d975d04da892325c56b6b14aaecb', None),
    'data-a-live': ('https://github.com/ShueiTsuki/data-a-live.git', DAL_COMMIT, None),
}


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def git(directory, *arguments, capture=False):
    result = subprocess.run(['git', '-C', str(directory), *arguments], check=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def file_tree(directory):
    # Include new files from the exported patches; git diff alone misses them.
    names = git(directory, 'ls-files', '--cached', '--others', '--exclude-standard', '-z', capture=True)
    result = hashlib.sha256()
    count = 0
    for raw_name in sorted(set(names.split(b'\0')) - {b''}):
        path = directory / os.fsdecode(raw_name)
        if path.is_symlink():
            value = b'link\0' + os.fsencode(os.readlink(path))
        elif path.is_file():
            value = b'file\0' + sha256(path).encode('ascii')
        elif path.is_dir():
            # The pinned parent contains unpopulated submodules, which are not
            # build inputs here; their gitlink IDs remain covered by HEAD.
            continue
        else:
            value = b'missing'
        result.update(raw_name + b'\0' + value + b'\0')
        count += 1
    return dict(files=count, sha256=result.hexdigest())


def expected(name):
    repository, commit, patch = SOURCES[name]
    return dict(repository=repository, commit=commit, patch=patch,
                patch_sha256=hashlib.sha256((ROOT / 'patches' / patch).read_text(
                    encoding='utf-8').encode('utf-8')).hexdigest() if patch else None)


def verify_source(source_root, name, record):
    directory = source_root / name
    assert record['input'] == expected(name), 'Source recipe changed: ' + name
    actual_commit = git(directory, 'rev-parse', 'HEAD', capture=True).decode().strip()
    assert actual_commit == SOURCES[name][1], 'Wrong source commit: ' + name
    actual_tree = file_tree(directory)
    assert actual_tree == record['tree'], 'Source content changed: ' + name
    print('GPU_SOURCE_VERIFIED', name, actual_commit, actual_tree['sha256'], flush=True)


def prepare_source(source_root, name):
    destination = source_root / name
    receipt = source_root / ('.' + name + '.json')
    if destination.exists() or receipt.exists():
        assert destination.is_dir() and receipt.is_file(), 'Incomplete input; preserve and inspect: ' + name
        record = json.loads(receipt.read_text(encoding='utf-8'))
        verify_source(source_root, name, record)
        return name, record
    repository, commit, patch = SOURCES[name]
    # Fetch and validate in a fresh directory. A failed fetch never replaces a
    # verified source tree, and no checkout resets someone else's working files.
    with tempfile.TemporaryDirectory(prefix='.' + name + '-fetch-', dir=source_root) as temporary:
        directory = Path(temporary) / 'tree'
        directory.mkdir()
        git(directory, 'init', '-q')
        git(directory, 'config', 'core.autocrlf', 'false')
        print('GPU_SOURCE_FETCH', name, commit, flush=True)
        git(directory, 'fetch', '--depth=1', repository, commit)
        git(directory, 'checkout', '--detach', 'FETCH_HEAD')
        actual_commit = git(directory, 'rev-parse', 'HEAD', capture=True).decode().strip()
        assert actual_commit == commit, 'Fetch returned a different commit: ' + name
        if patch:
            # Windows preserves CRLF in the exported patch files. Git apply needs
            # LF context to match the pinned checkout, as it will on the CI host.
            patch_path = Path(temporary) / 'export.patch'
            patch_path.write_bytes((ROOT / 'patches' / patch).read_text(encoding='utf-8').encode('utf-8'))
            git(directory, 'apply', '--check', '--whitespace=nowarn', str(patch_path))
            git(directory, 'apply', '--whitespace=nowarn', str(patch_path))
        record = dict(input=expected(name), tree=file_tree(directory))
        directory.rename(destination)
        with receipt.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write('\n')
        print('GPU_SOURCE_READY', name, commit, record['tree']['sha256'], flush=True)
        return name, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT / 'src')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--jobs', type=int, choices=range(1, 5), default=3)
    options = parser.parse_args()
    source_root = options.source_root.resolve()
    if options.verify_only:
        lock = json.loads((source_root / 'dodge-sources.json').read_text(encoding='utf-8'))
        assert set(lock['sources']) == set(SOURCES), 'Incomplete source manifest'
        for name in SOURCES:
            verify_source(source_root, name, lock['sources'][name])
        print('GPU_SOURCES_VERIFIED', len(SOURCES), flush=True)
        return
    source_root.mkdir(parents=True, exist_ok=True)
    results = {}
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=options.jobs) as pool:
        tasks = {pool.submit(prepare_source, source_root, name): name for name in SOURCES}
        for task in concurrent.futures.as_completed(tasks):
            try:
                name, record = task.result()
                results[name] = record
            except Exception as error:
                name = tasks[task]
                failures.append(name)
                print('GPU_SOURCE_FAILED', name, str(error), flush=True)
    if failures:
        raise SystemExit('Source preparation failed: ' + ', '.join(sorted(failures)))
    lock = dict(format=1, auxiliary_recipe=dict(repository=SOURCES['data-a-live'][0],
                commit=DAL_COMMIT, path='.github/workflows/turnip.yml'), sources=results)
    lock_path = source_root / 'dodge-sources.json'
    if lock_path.exists():
        assert json.loads(lock_path.read_text(encoding='utf-8')) == lock, 'Existing source manifest differs'
    else:
        with lock_path.open('x', encoding='utf-8') as stream:
            json.dump(lock, stream, indent=2, sort_keys=True)
            stream.write('\n')
    print('GPU_SOURCES_READY', len(results), sha256(lock_path), flush=True)


if __name__ == '__main__':
    main()
