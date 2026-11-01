#!/usr/bin/env python3
"""Report the state of the one file Dana is repairing: brace balance, and
whether the SoC layer is still wired in.

Brace depth is counted naively (the file has string literals with braces in
comments, so this is a symptom check, not a parser) -- a final depth of 0 and no
negative dip is what the compiler needs.
"""
import sys

p = sys.argv[1] if len(sys.argv) > 1 else '/root/dodge/build/bsd/dev/redwood_adsp.c'
s = open(p, encoding='utf-8', errors='replace').read()

d = 0
first_neg = None
for i, ch in enumerate(s):
    if ch == '{':
        d += 1
    elif ch == '}':
        d -= 1
        if d < 0 and first_neg is None:
            first_neg = i

line = s[:first_neg].count('\n') + 1 if first_neg is not None else None
print('final depth   : %d' % d)
print('first negative: %s' % ('byte %d (line %d)' % (first_neg, line) if first_neg is not None else 'none'))
print('hakios_soc refs: %d' % s.count('hakios_soc_facts'))
print('dadaadsp refs  : %d' % s.count('dadaadsp'))
print('dada window    : %d  (0x04580000 -- must only be the fallback)' % s.count('0x04580000'))

# the replaced block, shown as it stands
i = s.find('hakios_soc_facts')
if i > 0:
    start = s.rfind('\n', 0, max(0, i - 900))
    end = s.find('}', s.find('else if (pe_arm_get_soc_base_phys()', i))
    print()
    print('--- the block as it stands ---')
    print(s[start:end + 1].strip()[:1600])
