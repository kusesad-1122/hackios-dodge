#!/usr/bin/env python3
"""Summarise a kernel build log: what the errors are, and which of them matter.

The point is to separate three very different things that all look like
"error:" in one log:
  - a missing SDK header (the build cannot fix it, the header has to be supplied)
  - code written against an older XNU (a real porting job)
  - the -k noise that happens after the kernel is already linked
"""
import re
import sys
from collections import Counter, defaultdict

LOG = sys.argv[1] if len(sys.argv) > 1 else '/root/dodge/kar3.log'

files = Counter()
kinds = Counter()
examples = defaultdict(list)

ERR = re.compile(r'^(\S+?):(\d+):(?:\d+:)? error: (.*)$')

for line in open(LOG, encoding='utf-8', errors='replace'):
    m = ERR.match(line)
    if not m:
        continue
    path, lineno, msg = m.group(1), int(m.group(2)), m.group(3).strip()
    short = path.split('/')[-1] if '/' in path else path
    files[short] += 1
    # normalise the message to its first clause
    k = re.sub(r"[\"'(<].*", '', msg).strip()[:64]
    kinds[k] += 1
    if len(examples[short]) < 2:
        examples[short].append('L%d: %s' % (lineno, msg[:100]))

print('=== errors by file ===')
for f, n in files.most_common(14):
    print('  %-34s %3d' % (f, n))

print()
print('=== errors by kind ===')
for k, n in kinds.most_common(14):
    print('  %-52s %3d' % (k or '(empty)', n))

print()
print('=== one example per file ===')
for f, n in files.most_common(10):
    print('  %s (%d)' % (f, n))
    for e in examples[f]:
        print('      ' + e)

print()
print('=== the linked kernel ===')
import os
k = '/root/dodge/build/BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837'
if os.path.exists(k):
    print('  %s  %d bytes' % (k, os.path.getsize(k)))
else:
    print('  not built')
