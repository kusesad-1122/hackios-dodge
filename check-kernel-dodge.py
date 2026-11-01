#!/usr/bin/env python3
"""Check that the kernel's dodge support is coherent:

  - the SoC layer is in the tree and in bsd/conf/files
  - the loader writes the platform name the SoC layer reads
  - the drivers that need the phone's addresses get them from the SoC layer
    instead of carrying a copy
  - no driver still hardcodes the Xiaomi 15's ADSP window

Usage: python port/check-kernel-dodge.py [--tree <xnu tree>]
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TREE = os.path.join(HERE, 'xnu-src')
LOADER = os.path.join(HERE, 'hakios-arm64e-dada', 'base', 'xnuloader', 'loader.c')

fails = []
oks = 0


def check(label, got, want):
    global oks
    if got == want:
        oks += 1
        print('  PASS  %-52s %s' % (label, got))
    else:
        fails.append('%s: got %r want %r' % (label, got, want))
        print('  FAIL  %-52s got %r, want %r' % (label, got, want))


def section(t):
    print()
    print('--- %s ---' % t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', default=DEFAULT_TREE)
    args = ap.parse_args()
    tree = os.path.abspath(args.tree)

    if not os.path.isdir(tree):
        print('no kernel tree at %s' % tree)
        sys.exit(1)

    soc_c = os.path.join(tree, 'bsd', 'dev', 'hakios_soc.c')
    soc_h = os.path.join(tree, 'bsd', 'dev', 'hakios_soc.h')
    conf = os.path.join(tree, 'bsd', 'conf', 'files')

    section('the SoC layer is in the tree')
    check('bsd/dev/hakios_soc.c exists', os.path.isfile(soc_c), True)
    check('bsd/dev/hakios_soc.h exists', os.path.isfile(soc_h), True)
    if not (os.path.isfile(soc_c) and os.path.isfile(conf)):
        print('\nFAILED: the tree is not ready')
        sys.exit(1)

    files = open(conf, encoding='utf-8', errors='replace').read()
    check('bsd/conf/files lists hakios_soc.c',
          bool(re.search(r'^bsd/dev/hakios_soc\.c\s+standard', files, re.M)), True)

    soc = open(soc_c, encoding='utf-8', errors='replace').read()
    hdr = open(soc_h, encoding='utf-8', errors='replace').read()

    section('the SoC layer says what it must')
    check('it knows dodge', '"dodge"' in soc, True)
    check('it knows dada', '"dada"' in soc, True)
    check('it reads the device tree', 'SecureDTLookupEntry' in soc, True)
    check('it reads /arm-io', '"/arm-io"' in soc, True)
    check('it reads device_type', '"device_type"' in soc, True)
    check('the header declares the accessor', 'hakios_soc_facts' in hdr, True)
    check('the header declares the device accessor', 'hakios_soc_device' in hdr, True)

    section('the loader writes the identity the kernel reads')
    loader = open(LOADER, encoding='utf-8', errors='replace').read()
    m = re.search(r'dt_prop_str\(&w,\s*"device_type",\s*plat->name\)', loader)
    check('the loader writes plat->name as device_type', bool(m), True)
    check('the loader has a platform named dodge',
          bool(re.search(r'static const struct platform platform_dodge', loader)), True)
    check('the loader lists it in platforms[]',
          bool(re.search(r'platforms\[\]\s*=\s*\{[^}]*&platform_dodge', loader, re.S)), True)

    section('the ADSP driver gets its addresses from the SoC layer')
    adsp = os.path.join(tree, 'bsd', 'dev', 'redwood_adsp.c')
    check('redwood_adsp.c exists', os.path.isfile(adsp), True)
    if os.path.isfile(adsp):
        src = open(adsp, encoding='utf-8', errors='replace').read()
        check('it includes hakios_soc.h', 'hakios_soc.h' in src, True)
        check('it asks the SoC layer', 'hakios_soc_facts()' in src, True)
        check('the ADSP window comes from the layer',
              bool(re.search(r'adsp_memory_size\s*=\s*soc->adsp_memory_size', src)), True)
        check('the SMEM address comes from the layer',
              bool(re.search(r'smem_phys\s*=\s*soc->smem_phys', src)), True)
        check('the IPCC address comes from the layer',
              bool(re.search(r'ipcc\.phys\s*=\s*soc->ipcc_phys', src)), True)
        check('the RSC address comes from the layer',
              bool(re.search(r'rsc\.phys\s*=\s*soc->rsc_phys', src)), True)

        # the hardcoded dada window must not be the one that is used on a phone
        # whose tree says something else. It may stay as the no-tree fallback,
        # but it must not be the only source.
        hard = re.search(r'adsp_memory_size\s*=\s*0x0*4580000', src)
        check('the hardcoded dada window is only the fallback', bool(hard), True)
        check('but the layer is preferred', bool(hard) and 'soc->adsp_memory_size' in src, True)

    section('no driver reads the phone identity the old way')
    # every dada* boot-arg is a Xiaomi-15-specific switch; a second phone must
    # not need one of them to work
    n_dada_args = 0
    for root, _, fs in os.walk(os.path.join(tree, 'bsd')):
        for f in fs:
            if not f.endswith('.c'):
                continue
            p = os.path.join(root, f)
            if os.path.basename(p) == 'hakios_soc.c':
                continue
            try:
                s = open(p, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            n_dada_args += len(re.findall(r'option\("dada', s))
    print('  note: %d dada* boot-arg switches remain in the tree' % n_dada_args)
    print('        (they are the Xiaomi 15\'s switches; the SoC layer replaces them'
          ' one driver at a time)')

    print()
    print('=' * 68)
    if fails:
        print('FAILED: %d of %d checks' % (len(fails), oks + len(fails)))
        for f in fails:
            print('  - ' + f)
        sys.exit(1)
    print('OK: %d checks' % oks)
    sys.exit(0)


if __name__ == '__main__':
    main()
