#!/usr/bin/env python3
"""Write tests/differential_tests.nv from msgpack-python's answers.

msgpack-python (Apache-2.0) packs seeded value trees: every integer
width signed and unsigned, both float widths, strings and byte strings
around every length boundary, arrays and maps around the fix-form
boundary of 16, extension types, and timestamps in all three widths.
Each document is written as its bytes and as a rendering of the value
it holds, in a notation the suite computes from the decoded value:

    n   nil          t, f   true, false
    iN  an int       uHEX   an unsigned 64-bit value above 2^63
    gHEX, dHEX      a float 32 or float 64, by its bit pattern
    sHEX, bHEX      a str or a bin, by its bytes
    [a,b]  an array  {k:v,k:v}  a map  xT:HEX  an ext of type T

The suite decodes each document, renders it, and compares, then
encodes the decoded value and compares the bytes: msgpack-python writes
the shortest form, as this package does.

Run from the package root, with msgpack installed:
    python3 tools/differential.py
"""
import random
import struct
import subprocess

import msgpack

SEED = 20260927
COUNT = 200
OUT = 'tests/differential_tests.nv'
BOUNDS = [0, 1, 15, 16, 31, 32, 255, 256, 65535, 65536]


def rand_int(rng):
    edge = rng.choice([0, 1, 31, 32, 127, 128, 255, 256, 65535, 65536, 2**31 - 1, 2**31,
                       2**32 - 1, 2**32, 2**63 - 1])
    choice = rng.random()
    if choice < 0.3:
        return edge
    if choice < 0.6:
        return -edge - rng.choice([0, 1])
    if choice < 0.7:
        return rng.randrange(2**63, 2**64)
    return rng.randrange(-2**63, 2**63)


def rand_value(rng, depth, single):
    kind = rng.choice(['nil', 'bool', 'int', 'int', 'float', 'str', 'bin', 'ext', 'time',
                       'array', 'map'] if depth < 3 else ['int', 'str', 'bool', 'float'])
    if kind == 'nil':
        return None
    if kind == 'bool':
        return rng.random() < 0.5
    if kind == 'int':
        return rand_int(rng)
    if kind == 'float':
        f = rng.choice([0.5, -1.25, 1e300, -0.0, float('inf'), 3.141592653589793,
                        rng.uniform(-1e6, 1e6), 1e-40])
        if single:
            f = struct.unpack('>f', struct.pack('>f', f))[0] if abs(f) < 3e38 or f in (float('inf'),) else 1.5
        return f
    if kind == 'str':
        n = rng.choice(BOUNDS[:8] + [rng.randrange(0, 40)])
        alphabet = 'abcé中😀 '
        s = ''
        while len(s.encode('utf-8')) < n:
            s += rng.choice(alphabet)
        return s
    if kind == 'bin':
        n = rng.choice(BOUNDS[:9])
        return bytes(rng.randrange(256) for _ in range(n))
    if kind == 'ext':
        n = rng.choice([1, 2, 3, 4, 8, 16, 17, 255, 256])
        return msgpack.ExtType(rng.randrange(0, 128), bytes(rng.randrange(256) for _ in range(n)))
    if kind == 'time':
        return rng.choice([msgpack.Timestamp(rng.randrange(0, 2**32), 0),
                           msgpack.Timestamp(rng.randrange(0, 2**34), rng.randrange(1, 10**9)),
                           msgpack.Timestamp(-rng.randrange(1, 2**40), rng.randrange(0, 10**9))])
    if kind == 'array':
        n = rng.choice([0, 1, 3, 15, 16, 17])
        return [rand_value(rng, depth + 1, single) for _ in range(n)]
    n = rng.choice([0, 1, 3, 15, 16])
    out = {}
    while len(out) < n:
        key = rng.choice([rand_int(rng), 'k%d' % rng.randrange(1000), bytes([rng.randrange(256)])])
        out[key] = rand_value(rng, depth + 1, single)
    return out


def render(v, single):
    if v is None:
        return 'n'
    if v is True:
        return 't'
    if v is False:
        return 'f'
    if isinstance(v, int):
        return 'u%016x' % v if v >= 2**63 else 'i%d' % v
    if isinstance(v, float):
        if single:
            return 'g' + struct.pack('>f', v).hex()
        return 'd' + struct.pack('>d', v).hex()
    if isinstance(v, str):
        return 's' + v.encode('utf-8').hex()
    if isinstance(v, bytes):
        return 'b' + v.hex()
    if isinstance(v, msgpack.ExtType):
        return 'x%d:%s' % (v.code, v.data.hex())
    if isinstance(v, msgpack.Timestamp):
        return 'x-1:' + v.to_bytes().hex()
    if isinstance(v, list):
        return '[' + ','.join(render(x, single) for x in v) + ']'
    return '{' + ','.join(render(k, single) + ':' + render(x, single) for k, x in v.items()) + '}'


def main():
    rng = random.Random(SEED)
    rows = []
    for i in range(COUNT):
        single = i % 4 == 3
        v = rand_value(rng, 0, single)
        packed = msgpack.packb(v, use_bin_type=True, use_single_float=single, datetime=False)
        back = msgpack.unpackb(packed, raw=False, strict_map_key=False, timestamp=0)
        assert render(back, single) == render(v, single)
        rows.append((packed.hex(), render(v, single)))
    out = ['// differential_tests.nv — mpack against msgpack-python %s.' % '.'.join(map(str, msgpack.version)),
           '//',
           '// Written by tools/differential.py; do not edit by hand.  Each row is',
           '// a document msgpack-python packed and a rendering of the value it',
           '// holds; the script says what the rendering is.',
           '',
           'use std.test',
           'use mpack',
           '',
           'fn rows() -> [(Str, Str)]',
           '    [']
    for i, (h, r) in enumerate(rows):
        out.append('        ("%s", "%s")%s' % (h, r, ',' if i < len(rows) - 1 else ''))
    out += ['    ]',
            '',
            '// The rendering tools/differential.py describes.',
            'fn render(v: MsgValue) -> Str',
            '    match v',
            '        MsgNil          => "n"',
            '        MsgBool(b)      => if b then "t" else "f"',
            '        MsgInt(n)       => "i${n}"',
            '        MsgUint(bits)   => "u" + bytes.to_hex(bytes.u64_be(bits))',
            '        MsgFloat32(_)   => "g" + bytes.to_hex(bytes.slice(mpack.encode(v), 1, 5))',
            '        MsgFloat64(f)   => "d" + bytes.to_hex(bytes.u64_be(float.to_bits(f)))',
            '        MsgStr(t)       => "s" + bytes.to_hex(bytes.from_str(t))',
            '        MsgBin(b)       => "b" + bytes.to_hex(b)',
            '        MsgArray(items) => "[" + str.join(list.map(items, (x) => render(x)), ",") + "]"',
            '        MsgMap(entries) => "{" + str.join(list.map(entries, (e) => render(e.key) + ":" + render(e.value)), ",") + "}"',
            '        MsgExt(kind, d) => "x${kind}:" + bytes.to_hex(d)',
            '',
            '@test',
            'fn test_every_document_msgpack_python_packed_reads_and_writes_back() [io]',
            '    for row in rows()',
            '        let (hex, expected) = row',
            '        test.case(hex)',
            '        let raw = bytes.from_hex(hex) ?? bytes.zeros(0)',
            '        match mpack.decode(raw)',
            '            Err(e) => test.fail(e.message())',
            '            Ok(v)  =>',
            '                test.assert_eq(render(v), expected)',
            '                test.assert_eq(bytes.to_hex(mpack.encode(v)), hex)',
            '']
    open(OUT, 'w').write('\n'.join(out))
    subprocess.run(['novo', 'fmt', OUT], check=True, stdout=subprocess.DEVNULL)
    print('%d documents' % len(rows))


if __name__ == '__main__':
    main()
