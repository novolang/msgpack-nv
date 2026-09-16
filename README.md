# msgpack-nv

MessagePack is a binary format for the same data JSON describes:
numbers, strings, booleans, nothing, arrays and maps. Every value begins
with a **format byte** saying what it is and how long it is, so a reader
that has never seen the schema can walk a document, and `{"a":1}` costs
four bytes rather than seven. The format is defined by the
[MessagePack specification](https://github.com/msgpack/msgpack/blob/master/spec.md),
revision 2 of 9 August 2017. This package implements all of it.

**Status: NOT IMPLEMENTED — interface only.** Every function is declared
with its full signature, but every body is a `todo()` that panics when
called. The package is published so its design can be reviewed and
depended on before it is implemented. Version 0.1.0 will be the first
working release.

## What MessagePack is

A document is one value. A value is a format byte and then, for the
types that need it, a length and a payload. A format that carries its
own types this way is called **self-describing**: nothing outside the
bytes is needed to read them.

The specification groups the format bytes into **families**. The `str`
family is text, and its bytes are UTF-8. The `bin` family is bytes, and
it was separated from `str` in 2013 so that a reader can tell text from
data with no schema. The `array` and `map` families carry a count and
then that many values, or that many key and value pairs. A map key is
any value, not only a string.

The `ext` family is an application-defined type: a small signed number
and a payload. Negative type numbers are reserved by the specification,
and `-1` is the **timestamp extension**, which carries seconds and
nanoseconds in one of three widths.

Integers are big-endian and fixed width: one, two, four or eight bytes,
chosen by the format byte in front of them. An encoder writes the
shortest format that holds the number, so a round trip preserves the
value and not the spelling.

| Quantity | Value |
| --- | --- |
| Format byte for nil | `0xc0` |
| Format bytes for false and true | `0xc2`, `0xc3` |
| Format byte reserved and never assigned | `0xc1` |
| Format bytes for the two float widths | `0xca` (32-bit), `0xcb` (64-bit) |
| Timestamp extension type | -1 |
| Timestamp payload widths | 4, 8 or 12 bytes |
| Nanoseconds field range | 0 to 999999999 |
| Range of an `ext` type number | -128 to 127 |
| Default nesting limit of a decoder | 64 |
| Cost of a two-entry map of short keys | 9 bytes |

## Install

```
novo pkg add msgpack-nv
```

## Example

```novo
use std.bytes
use mpack

fn main() [io]
    // A document built as a value tree: a map of two entries.
    let doc = MsgMap([
        MsgPair { key: MsgStr("id"), value: MsgInt(7) },
        MsgPair { key: MsgStr("ok"), value: MsgBool(true) },
    ])

    // Nine bytes: 82 a2 69 64 07 a2 6f 6b c3.
    println(bytes.to_hex(mpack.encode(doc)))
```

Build and test with `novo pkg build` and `novo test`. Today `novo test`
fails on purpose: every test reaches a `not implemented: mpack.<fn>`
panic. The tests are the specification the implementation will have to
satisfy.

## What the package contains

| Module | Contents |
| --- | --- |
| `mpack` | The value tree and the format itself: the eleven cases of a value, the accessors, the timestamp extension, the size question, encode, and decode of a whole document or of one document and its length. |
| `mpackdec` | The same decoder fed a chunk at a time, for a document that arrives in pieces. It holds the tail that did not finish a value, and counts offsets from the start of the stream. |
| `mpackserde` | The bridge to the standard library's `Serialize` and `Deserialize` traits, so a novo-lang type writes and reads itself with no code to write. |

## How to choose an entry point

**`mpack` is the value tree.** Reach for it when the other end is not
novo-lang, when the document's shape is not a struct, when a map's keys
are not strings, or when you need `bin`, `ext`, a timestamp, a 32-bit
float or an unsigned integer above 2^63.

**`mpackdec` is the streaming decoder.** Reach for it when the document
arrives off a socket in pieces. Feed a chunk, take whatever finished.

**`mpackserde` is the trait bridge.** Reach for it when both ends are
novo-lang and the data is a struct. `to_bytes` and `from_bytes` are the
whole surface for that case.

**`mpack.decode_prefix` reads one document out of a buffer of many.**
MessagePack has no terminator, so `consumed` is the only way to find
where the next one starts.

## The rules a user needs

1. **An encoder writes the shortest format that holds the value.** The
   specification recommends it and every implementation does it. A
   document whose author wrote `0` as an eight-byte integer comes back
   as one byte, so a round trip preserves the number and not the
   spelling.
2. **An unsigned 64-bit value above 2^63 is its own case.** `MsgUint`
   carries the bit pattern, which reads as a negative number. A reader
   that answered `MsgInt(-1)` for `18446744073709551615` would give a
   caller no way to tell it from an actual `-1`.
3. **The two float widths stay apart.** `MsgFloat32` and `MsgFloat64`
   are different cases, because the width is on the wire and a value
   that goes out as four bytes should not come back as eight.
4. **`str` is UTF-8 and `bin` is not checked.** A `str` whose bytes are
   not UTF-8 is `MsgBadUtf8`. That rule is what `bin` exists to avoid.
5. **A map is a list of pairs, not a keyed collection.** A key is any
   value, and the specification permits duplicate keys without saying
   which wins. `mpack.get` answers the first match, which is what a
   reader scanning the document reaches. A caller checking for
   duplicates walks `mpack.as_map`.
6. **A decoder has a nesting limit, and it is 64 by default.** An array
   header is one byte and can open a level, so a small document can ask
   for a hundred thousand levels of recursion. Past the limit is
   `MsgDepthExceeded`. `mpackdec.with_depth_limit` raises or lowers it,
   and the limit travels on the decoder so that two decoders in one
   program may differ.
7. **`mpack.decode` refuses trailing bytes.** One buffer, one document.
   A caller reading several uses `decode_prefix` or `mpackdec`.
8. **`0xc1` is not MessagePack.** The specification reserves that byte
   and never assigns it. `MsgReservedFormat` names its offset.
9. **A truncation says how many bytes it still wanted.**
   `MsgTruncated(at, need)`. For a stream reader that is how it learns
   to read more.
10. **The timestamp's seconds are the caller's argument.** This package
    has no clock. `mpack.timestamp_value` picks the shortest of the
    three widths, and nanoseconds outside 0 to 999999999 are refused on
    the way back as `MsgBadTimestamp`.
11. **`mpack.encode_into` writes nothing when the destination is
    short.** Size it with `mpack.encoded_len`, which is exact because
    every length is known before anything is written.
12. **A struct written through the trait bridge becomes a map keyed by
    member name.** Not an array of members in declaration order. The
    array form is half the size, and the traits give a reader no way to
    know which convention the writer used.

## What is not included

- **A build for a microcontroller.** The surface speaks `Bytes`, `Str`
  and `Result`, none of which links on a device today, so this package
  does not build for a microcontroller with no heap allocator and
  carries no probe program.
  [cbor-nv](https://novo-lang.org/packages/cbor-nv) is the format with a
  device half.
- **Unsigned integers above 2^63 through the trait bridge.** The
  standard library's `Serialize` has one integer hook, `put_int(Int)`,
  and no way to say "unsigned, and it does not fit". Build such a
  document with `MsgUint`.
- **32-bit floats through the trait bridge.** `put_float` writes the
  64-bit form always. Build `MsgFloat32` for the narrow one, which is
  what most embedded producers send.
- **The `bin` family through the trait bridge.** The standard library
  declares `Serialize` for `Int`, `Float`, `Bool` and `Str`, and has no
  hook for `Bytes`. A member that is really bytes travels as a `str` of
  whatever the caller encoded it to, or the document is built with
  `MsgBin`. A `put_bytes` hook would close this, and would close it for
  cbor-nv too.
- **Non-string map keys through the trait bridge.** `begin_struct` and
  `field(name)` are the only way in, so a document keyed by integers is
  built with `MsgMap`.
- **A dependency on
  [leb128-nv](https://novo-lang.org/packages/leb128-nv) or
  [zigzag-nv](https://novo-lang.org/packages/zigzag-nv).** MessagePack's
  integers are big-endian and fixed width, not variable-length
  quantities.
- **Any input or output.** Every function here is arithmetic over bytes
  the caller already holds.

## Related packages

- [serde-nv](https://novo-lang.org/packages/serde-nv) has a `msgpack`
  module, which is the subset its own trait walk produces: a writer and
  an offset cursor, with no value tree, no streaming, no `bin`, no `ext`
  and no timestamp. Both packages can be in one program, because the
  module and type names are disjoint: `mpack` and `MsgValue` here,
  `msgpack` and `MsgPackWriter` there. This package does not depend on
  it; the traits come from `std.serialize`.
- [cbor-nv](https://novo-lang.org/packages/cbor-nv) is the other
  self-describing binary format, standardised as RFC 8949. It is the one
  to reach for on a device.
- [postcard-nv](https://novo-lang.org/packages/postcard-nv) is the
  opposite trade: no tags on the wire at all, so it is smaller and both
  ends must already agree on the schema.
- [protobuf-nv](https://novo-lang.org/packages/protobuf-nv) tags fields
  by number rather than by name, and needs a schema for everything else.

## Tests

```bash
novo test tests/msgpack_tests.nv      # 35 tests
```

Every vector is from the specification's format table, its worked
examples or its timestamp section. The implementations to check a port
against are `msgpack-python` and the `rmp` crate in Rust.

The suite asserts that nil and the booleans are one byte each, that an
integer takes the shortest format that holds it and that every format
decodes to the same number, that an unsigned value above 2^63 is its own
case, that the two float widths stay apart, that bytes are their own
family, that a map key is any value, that duplicate keys survive to the
caller with the first one winning, that the timestamp extension is type
-1 and picks its width, that the reserved format byte is refused, that a
truncation names what it still needed, that nesting past the limit is
refused rather than recursed, that a value split across chunks finishes
on the chunk that completes it, that one chunk carrying several messages
drains them all, and that a struct writes itself as a map and reads
itself back.

The tests compile today and fail at run, each on the `not implemented`
panic that is its body. That is the expected state of an interface
release. They turn green one at a time as bodies land.

## Implementation status

| Item | Implemented |
| --- | --- |
| `mpack.type_name`, `.format_byte`, `.default_depth_limit` | no |
| `mpack.as_int`, `.as_bool`, `.as_float`, `.as_str`, `.as_bytes` | no |
| `mpack.as_array`, `.as_map`, `.get` | no |
| `mpack.timestamp_type`, `.timestamp_value`, `.timestamp_of` | no |
| `mpack.encoded_len`, `.encode`, `.encode_into` | no |
| `mpack.decode`, `.decode_prefix` | no |
| `mpack.MsgError.message` | no |
| `mpackdec.decoder`, `.with_depth_limit`, `.pending`, `.stream_at` | no |
| `mpackdec.feed`, `.finish` | no |
| `mpackserde.writer`, `.writer_bytes`, `.reader`, `.reader_at` | no |
| `MsgWriter`'s `Serializer` methods | no |
| `MsgReader`'s `Deserializer` methods | no |
| `mpackserde.to_bytes`, `.from_bytes` | no |

## Licence

Apache-2.0. See `LICENSE`.

<!-- docs/writing-a-readme.md is the style guide for this page. -->
