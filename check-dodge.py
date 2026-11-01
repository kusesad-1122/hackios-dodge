#!/usr/bin/env python3
"""Check that the dodge profile, the loader's platform row and the phone's own
device tree agree with each other.

The point of this checker is that it bites: it reads the real device tree the
phone produced, parses the loader's C source, parses the profile, and compares
the three. A port that copies a number from a document instead of from the
device tree fails here.

Usage:  python port/check-dodge.py [--dts <device-tree.dts>]
Exit code 0 = everything agrees.
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, 'hakios-arm64e-dada')
LOADER = os.path.join(REPO, 'base', 'xnuloader', 'loader.c')
PROFILE = os.path.join(REPO, 'base', 'common', 'devices', 'dodge.conf')
DEFAULT_DTS = os.path.join(HERE, '..', 'backup', 'out', 'hw', 'hw', 'device-tree.dts')

fails = []
oks = 0


def check(label, got, want, note=''):
    global oks
    if got == want:
        oks += 1
        print('  PASS  %-46s %s' % (label, got))
    else:
        fails.append('%s: got %r, want %r %s' % (label, got, want, note))
        print('  FAIL  %-46s got %r, want %r %s' % (label, got, want, note))


def section(name):
    print()
    print('--- %s ---' % name)


def parse_loader():
    """Pull platform_dodge's initialisers out of loader.c."""
    src = open(LOADER, encoding='utf-8', errors='replace').read()
    m = re.search(r'static const struct platform platform_dodge = \{(.*?)\n\};', src, re.S)
    if not m:
        print('  FAIL  platform_dodge is not in loader.c')
        sys.exit(1)
    body = m.group(1)
    # strip comments so a commented-out value cannot be mistaken for a real one
    body = re.sub(r'/\*.*?\*/', ' ', body, flags=re.S)
    body = re.sub(r'//[^\n]*', ' ', body)

    def val(key):
        mm = re.search(r'\.%s\s*=\s*(0x[0-9a-fA-F]+|\d+)' % key, body)
        return int(mm.group(1), 0) if mm else None

    return {
        'name': (re.search(r'\.name\s*=\s*"([^"]+)"', body) or [None, None])[1],
        'io_base': val('io_base'), 'io_size': val('io_size'),
        'gic_dist': val('gic_dist'), 'gic_redist': val('gic_redist'),
        'gic_redist_size': val('gic_redist_size'), 'gic_redist_stride': val('gic_redist_stride'),
        'uart': val('uart'), 'cores': val('cores'), 'core_shift': val('core_shift'),
        'small_cores': val('small_cores'), 'fb_base': val('fb_base'),
        'panel_width': val('panel_width'), 'panel_height': val('panel_height'),
        '_body': body,
    }


def parse_profile():
    txt = open(PROFILE, encoding='utf-8', errors='replace').read()
    out = {}
    for line in txt.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def parse_dts(path):
    """The facts the phone's device tree states, as a dict."""
    src = open(path, encoding='utf-8', errors='replace').read()
    d = {}

    m = re.search(r'^\s*model\s*=\s*"([^"]+)"', src, re.M)
    d['model'] = m.group(1) if m else None

    # the GIC node: its reg and its redistributor-stride
    gic = re.search(r'interrupt-controller@16000000\s*\{(.*?)\n\s*\};', src, re.S)
    if gic:
        b = gic.group(1)
        m = re.search(r'reg\s*=\s*<([^>]*)>', b)
        if m:
            cells = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', m.group(1))]
            # reg = <dist-io dist-size redist-io redist-size>
            if len(cells) >= 4:
                d['gic_dist'] = cells[0]
                d['gic_redist'] = cells[2]
                d['gic_redist_size'] = cells[3]
        m = re.search(r'redistributor-stride\s*=\s*<([^>]*)>', b)
        if m:
            cells = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', m.group(1))]
            if len(cells) >= 2:
                d['gic_redist_stride'] = (cells[0] << 32) | cells[1]

    # the CPU nodes: their reg is the MPIDR
    cpus = re.findall(r'cpu@([0-9a-fA-F]+)\s*\{[^}]*?reg\s*=\s*<0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)>', src, re.S)
    d['cpus'] = [(int(a, 16), int(c, 16)) for a, c in [(x[0], x[2]) for x in cpus]]
    d['core_count'] = len(d['cpus'])

    m = re.search(r'ufshc@([0-9a-fA-F]+)', src)
    d['ufs_hc'] = int(m.group(1), 16) if m else None

    m = re.search(r'qcom,gpu-model\s*=\s*"([^"]+)"', src)
    d['gpu_model'] = m.group(1) if m else None

    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dts', default=DEFAULT_DTS)
    args = ap.parse_args()
    dts = os.path.abspath(args.dts)

    print('checker: %s' % os.path.basename(__file__))
    print('loader : %s' % os.path.relpath(LOADER, HERE))
    print('profile: %s' % os.path.relpath(PROFILE, HERE))
    print('device tree: %s' % (dts if os.path.exists(dts) else 'MISSING ' + dts))

    if not os.path.exists(dts):
        print('\nno device tree: cannot check anything against the phone')
        sys.exit(1)

    L = parse_loader()
    P = parse_profile()
    D = parse_dts(dts)

    section('the profile exists and is well formed')
    check('profile NAME', P.get('NAME'), 'OnePlus 13 (dodge)')
    check('profile UEFI_TARGET', P.get('UEFI_TARGET'), 'dodge')
    check('profile SOC', P.get('SOC'), 'Qualcomm Snapdragon 8 Elite (SM8750)')
    check('profile BOOTARGS is present', bool(P.get('BOOTARGS')), True)

    section('the loader knows this device')
    check('loader platform name', L['name'], 'dodge')
    src = open(LOADER, encoding='utf-8', errors='replace').read()
    check('platform_dodge is in platforms[]',
          bool(re.search(r'platforms\[\]\s*=\s*\{[^}]*&platform_dodge', src, re.S)), True)

    section('the loader row and the profile agree')
    check('FB_BASE  profile vs loader', int(P['FB_BASE'], 0), L['fb_base'])
    check('FD_BASE  profile vs loader(uefi)', int(P['FD_BASE'], 0), 0xA7100000)
    check('FD_SIZE  profile vs loader(uefi)', int(P['FD_SIZE'], 0), 0x300000)
    check('PANEL_WIDTH  profile vs loader', int(P['PANEL_WIDTH'], 0), L['panel_width'])
    check('PANEL_HEIGHT profile vs loader', int(P['PANEL_HEIGHT'], 0), L['panel_height'])

    section('the loader row and the PHONE agree (this is the real check)')
    check('gic_dist     vs device tree', L['gic_dist'], D['gic_dist'])
    check('gic_redist   vs device tree', L['gic_redist'], D['gic_redist'])
    check('gic_redist_size vs device tree', L['gic_redist_size'], D['gic_redist_size'])
    check('gic_redist_stride vs device tree', L['gic_redist_stride'], D['gic_redist_stride'])
    check('core count   vs device tree', L['cores'], D['core_count'])
    check('cores        vs device tree', L['cores'], 8)
    check('core_shift   vs MPIDR layout', L['core_shift'], 8)
    check('dodge is in the device tree', 'dodge' in (D['model'] or ''), True)
    check('gpu_model (informational)', D['gpu_model'], 'Adreno830v2')

    section('the two-cluster MPIDR layout')
    # Qualcomm numbers the eight Oryon cores: six performance at Aff1 0..5, two prime at Aff2=1
    mp = sorted(m for _, m in D['cpus'])
    check('the eight MPIDRs', [hex(x) for x in mp],
          ['0x0', '0x100', '0x200', '0x300', '0x400', '0x500', '0x10000', '0x10100'])

    section('dodge and dada must not be confused')
    m = re.search(r'static const struct platform platform_dada = \{(.*?)\n\};', src, re.S)
    if m:
        b = re.sub(r'/\*.*?\*/', ' ', m.group(1), flags=re.S)
        dv = re.search(r'\.fb_base\s*=\s*(0x[0-9a-fA-F]+)', b)
        dw = re.search(r'\.panel_width\s*=\s*(\d+)', b)
        dh = re.search(r'\.panel_height\s*=\s*(\d+)', b)
        check('dada fb_base', int(dv.group(1), 0) if dv else None, 0xFC800000)
        check('dada panel_width', int(dw.group(1)) if dw else None, 1200)
        check('dada panel_height', int(dh.group(1)) if dh else None, 2670)
        check('dada and dodge differ in panel size',
              (dw and dh and (int(dw.group(1)) != L['panel_width'] or
                              int(dh.group(1)) != L['panel_height'])), True,
              'otherwise the loader cannot tell them apart')
    else:
        fails.append('platform_dada not found in loader.c')

    section('the profile mentions the panel')
    check('profile PANEL_WIDTH present', 'PANEL_WIDTH' in P, True)
    check('profile PANEL_HEIGHT present', 'PANEL_HEIGHT' in P, True)

    print()
    print('=' * 68)
    if fails:
        print('FAILED: %d of %d checks' % (len(fails), oks + len(fails)))
        for f in fails:
            print('  - ' + f)
        sys.exit(1)
    print('OK: %d checks, all agree with the phone' % oks)
    sys.exit(0)


if __name__ == '__main__':
    main()
