#!/usr/bin/env python3
"""Check the kernel's SoC layer (hakios_soc.c) against the phone's own device tree.

The SoC layer carries hardware addresses. If one of them is wrong, the driver
that uses it writes to the wrong place -- on a phone, that is a bus error at
best. So every address in hakios_soc.c is checked here against the device tree
the phone produced (backup/out/hw/hw/device-tree.dts), which is the only
authority.

Usage: python port/check-soc.py [--dts <device-tree.dts>]
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOC_C = os.path.join(HERE, 'hakios_soc.c')
DEFAULT_DTS = os.path.join(HERE, '..', 'backup', 'out', 'hw', 'hw', 'device-tree.dts')

fails = []
oks = 0


def check(label, got, want):
    global oks
    if got == want:
        oks += 1
        print('  PASS  %-40s %s' % (label, got if not isinstance(got, int) else hex(got)))
    else:
        fails.append('%s: got %r want %r' % (label, got, want))
        print('  FAIL  %-40s got %r, want %r' % (label, got, want))


def section(t):
    print()
    print('--- %s ---' % t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dts', default=DEFAULT_DTS)
    args = ap.parse_args()
    dts = os.path.abspath(args.dts)

    if not os.path.exists(SOC_C):
        print('no hakios_soc.c')
        sys.exit(1)
    if not os.path.exists(dts):
        print('no device tree at %s' % dts)
        sys.exit(1)

    soc = open(SOC_C, encoding='utf-8', errors='replace').read()
    # the initialisers, without the comments
    body = re.sub(r'/\*.*?\*/', ' ', soc, flags=re.S)
    body = re.sub(r'//[^\n]*', ' ', body)

    def val(key):
        m = re.search(r'\.%s\s*=\s*(0x[0-9a-fA-F]+|\d+)' % key, body)
        return int(m.group(1), 0) if m else None

    src = open(dts, encoding='utf-8', errors='replace').read()

    def node(pattern):
        for mm in re.finditer(r'([a-zA-Z0-9_,@\.\-]+)\s*\{', src):
            if re.search(pattern, mm.group(1)):
                depth = 0
                i = mm.end() - 1
                while i < len(src):
                    if src[i] == '{':
                        depth += 1
                    elif src[i] == '}':
                        depth -= 1
                        if depth == 0:
                            return src[mm.start():i + 1]
                    i += 1
        return None

    def reg(pattern):
        """(base, size) of the node, read the way extract-soc-table.py does."""
        b = node(pattern)
        if not b:
            return None
        m = re.search(r'reg\s*=\s*<([^>]*)>', b)
        if not m:
            return None
        cells = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', m.group(1))]
        if len(cells) < 2:
            return None
        if len(cells) % 4 != 0:
            per = 2
        elif len(cells) % 8 == 0:
            per = 2
        else:
            per = 4
        if per == 2:
            return cells[0], cells[1]
        return cells[1], cells[3]

    print('checker: %s' % os.path.basename(__file__))
    print('soc layer: %s' % os.path.basename(SOC_C))
    print('device tree: %s' % dts)

    section('the identities')
    m = re.search(r'^\s*model\s*=\s*"([^"]+)"', src, re.M)
    check('device tree says dodge', bool(m and 'dodge' in m.group(1)), True)
    check('the layer knows "dodge"', '"dodge"' in soc, True)
    check('the layer knows "dada"', '"dada"' in soc, True)

    section('the addresses, against the phone\'s own tree')
    check('smem_phys', val('smem_phys'), reg(r'^smem_region@')[0])
    check('smem_size', val('smem_size'), reg(r'^smem_region@')[1])
    check('cmd_db_phys', val('cmd_db_phys'), reg(r'aop_cmd_db_region@')[0])
    check('adsp_phys', val('adsp_phys'), reg(r'remoteproc-adsp@')[0])
    check('adsp_memory', val('adsp_memory'), reg(r'adspslpi_region@')[0])
    check('adsp_memory_size', val('adsp_memory_size'), reg(r'adspslpi_region@')[1])
    check('ipcc_phys', val('ipcc_phys'), reg(r'qcom,ipcc@')[0])
    check('ufs_hc_phys', val('ufs_hc_phys'), reg(r'ufshc@')[0])
    check('apps_smmu_phys', val('apps_smmu_phys'), reg(r'apps-smmu@')[0])
    check('aoss_phys', val('aoss_phys'), reg(r'power-controller@')[0])

    section('the GIC')
    gic = node(r'interrupt-controller@16000000')
    if gic:
        m = re.search(r'reg\s*=\s*<([^>]*)>', gic)
        cells = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', m.group(1))] if m else []
        check('gic_dist', val('gic_dist'), cells[0] if cells else None)
        check('gic_redist', val('gic_redist'), cells[2] if len(cells) > 2 else None)
        check('gic_redist_size', val('gic_redist_size'), cells[3] if len(cells) > 3 else None)
        m = re.search(r'redistributor-stride\s*=\s*<([^>]*)>', gic)
        sc = [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', m.group(1))] if m else []
        check('gic_redist_stride', val('gic_redist_stride'), (sc[0] << 32 | sc[1]) if len(sc) > 1 else None)

    section('the cores')
    cpus = re.findall(r'cpu@([0-9a-fA-F]+)\s*\{', src)
    check('cores', val('cores'), len(cpus))
    check('core_shift', val('core_shift'), 8)

    section('the panel, from the phone')
    check('panel_width', val('panel_width'), 1440)
    check('panel_height', val('panel_height'), 3168)

    section('the difference between the two phones of this family')
    # dada's ADSP window is 0x4580000; this phone's is 0x5080000. If the layer
    # carried dada's number, the ADSP driver would write past the window.
    check('the ADSP window is this phone\'s, not dada\'s',
          val('adsp_memory_size'), 0x5080000)
    check('and not dada\'s 0x4580000', val('adsp_memory_size') != 0x4580000, True)

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
