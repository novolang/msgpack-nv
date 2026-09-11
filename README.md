# msgpack-nv

**Status: NOT IMPLEMENTED — interface only.**

Every public function below is published with its signature and its
effect row, and every body is `todo()`.  Installing this package works;
calling it panics with `not implemented`.

## What this is

MessagePack, whole.  JSON's data model with the tags on the wire: every
value begins with a format byte that says what it is and how long it is,
so a reader that has never seen the schema can walk a document and a
`{"a":1}` that costs seven bytes as JSON costs four here.

Three surfaces, and a reader should know which one they are on.

| surface | module | reach for it when |
| --- | --- | --- |
| the **value tree** | `mpack` | the other end is not novo-lang, the document's shape is not a struct, or a map's keys are not strings |
| the **stream** | `mpackdec` | the document arrives off a socket in pieces |
| the **trait bridge** | `mpackserde` | both ends are novo-lang and you would rather not write any code |

## Adding it, and checking it

```bash
novo pkg add msgpack-nv       # into your novo.toml
novo pkg build                # type- and effect-check the package
novo test --isolate tests/msgpack_tests.nv
```

`novo test` is red today and that is the point of the release: every
assertion fails with `not implemented: mpack.<fn>`.  They turn green one
at a time as bodies land.

## The one example that will work

```novo
use std.bytes
use mpack

fn main() [io]
    let doc = MsgMap([
        MsgPair { key: MsgStr("id"), value: MsgInt(7) },
        MsgPair { key: MsgStr("ok"), value: MsgBool(true) },
    ])
    println(bytes.to_hex(mpack.encode(doc)))
    // 82a26964 07a26f6b c3 — a two-entry map in nine bytes
```

## serde-nv already has a MessagePack module — why this one?

`serde-nv`'s `msgpack` module is the **subset its trait walk needs**: a
writer and an offset cursor covering the formats a novo-lang struct
produces.  Its own `skip` says so — it answers 0 for a header "this
subset does not cover" — and it has no value tree, no streaming, no
`bin`, no `ext` and no timestamp.

This package is the whole format.  What it adds:

- **A value tree.**  `MsgValue` for documents whose shape is not a
  struct: a configuration file, an RPC envelope, anything written by a
  Python or Ruby peer.
- **The families the walk cannot produce.**  `bin`, `ext`, the
  timestamp extension, `uint 64` above 2^63, and `float 32`.
- **A streaming decoder.**  `mpackdec` takes a chunk and answers
  whatever finished, so a socket reader does not have to buffer a whole
  message before it knows there is one.
- **Named refusals with offsets.**  The reserved format byte, a
  truncation that says how many bytes it still wanted, a non-UTF-8
  `str`, a depth limit, trailing bytes.

Both can be in one program: the module names and the type names are
disjoint on purpose (`mpack` and `MsgValue` here, `msgpack` and
`MsgPackWriter` there).  That disjointness is also the reason this
module is not called `msgpack` — two dependencies of one program may
not both ship a module of the same name, and serde-nv had the name
first.  `mpack` is what the C implementation of this format is called,
so the spelling is a borrowing rather than an invention.

**This package does not depend on serde-nv.**  The `Serializer` and
`Deserializer` traits are the standard library's (`std.serialize`), and
a dependency would put a second MessagePack implementation in every
consumer's assembly.

## Is the serde bridge writable today? Yes — both halves

This is the question the interface milestone exists to answer, and for
this format the answer is yes, where for postcard-nv it was half no.
The difference is entirely that MessagePack is self-describing.

**The read half works.**  postcard-nv's `Deserializer` cannot be written
correctly because `field(self, name)` answers a child cursor and leaves
the parent unchanged, and a nameless format's member 2 begins wherever
member 1 ended — which the parent has no way to learn.  MessagePack
writes a key in front of every member, so `field("beta")` **scans the
map at the parent's own offset** and needs no threading at all.  The
parent is never advanced because it never has to be.  serde-nv's
existing reader is built exactly that way and works, which is the proof
rather than the argument.

**The write half works too.**  postcard-nv cannot write an optional
because the trait announces `None` (as `put_null`) and announces `Some`
not at all, so a present optional reaches the format as a bare value
with no discriminant in front of it.  MessagePack needs no
discriminant: `nil` is `0xc0` and is distinguishable from every other
value by its own format byte, so `None` is `put_null` and `Some(x)` is
`x`, and the two are already different documents.

So both stdlib defects postcard-nv found are consequences of a
**nameless, untagged** format, and a self-describing one meets neither.

## Where the trait bridge is still short of the format

Four places, and every one has the value tree as its answer.  None of
them blocks the impl; they are the reason `mpack` exists beside it.

**One integer hook.**  `put_int(v: Int)` is all there is, so `uint 64`
above 2^63 is unreachable: the walk has no way to say "this is
unsigned and it does not fit".  A document that needs one is built with
`MsgUint`.  The read side refuses such a value rather than answering the
bit pattern, because a negative number for a positive document is worse
than an error.

**One float hook.**  `put_float(v: Float)` writes `float 64`, always.
`float 32` halves the bytes of a sensor reading and is what most
embedded producers send; a caller who wants it builds `MsgFloat32`.

**No bytes hook.**  The trait has `put_str` and nothing for `Bytes` —
the standard library declares `Serialize` for `Int`, `Float`, `Bool` and
`Str` and for nothing else — so the entire `bin` family is unreachable
from the walk.  A member that is really bytes travels as a `str` of
whatever the caller encoded it to, or the document is built with
`MsgBin`.  This is the one of the four that is a standard library gap
rather than a novo-lang/MessagePack impedance: a `Serialize` impl for
`Bytes` and a `put_bytes` hook would close it, and would close the same
gap for cbor-nv.

**Struct keys are always strings.**  `begin_struct` and `field(name)`
are the only way into a map, so a document whose keys are integers —
which MessagePack permits and which a compact protocol uses — has to be
built with `MsgMap`.

One thing that is a **choice** rather than a shortfall: a struct writes
itself as a `map` keyed by member name, not as an `array` of its members
in declaration order.  The array form is half the bytes and is what two
novo-lang programs sharing a schema would rather have.  It is
deliberately not what this does, because the trait gives the reader no
way to know which convention the writer chose, and a package with both
would produce documents that decode as the wrong shape with no
diagnostic.

## The layer, and why

`core`.  Everything here is arithmetic over bytes the caller already
holds, and no function declares an effect — a wire format has nowhere to
put one.  The timestamp extension takes its seconds as a parameter for
the same reason a gzip header's mtime is a parameter: **a `core` package
has no clock**, and a document that cannot ask for the time is a
document that is reproducible.

It carries **no `tests/embedded_probe.nv`**, so it makes no device
claim, and the audit's `core-embedded` row passes by saying so.  That is
deliberate: the surface speaks `Bytes`, `Str` and `Result`, and none of
the three links at `@tier(embedded)` today.  **cbor-nv is the one of
this pair with a device half**, because the grid's row for it says the
embedded tier prefers CBOR — and the two formats are close enough that
an embedded producer choosing between them should choose the one that
compiles.

## Not leb128-nv, not zigzag-nv

postcard-nv depends on both, and a reader coming from there will look
for them here.  MessagePack's integers are **big-endian and fixed
width** — one, two, four or eight bytes, chosen by the format byte in
front of them — and are not variable-length quantities at all.  Two
copies of an encoding are two things to keep in step; so are two
encodings called by the same name, and this one is a different encoding.

## The reference implementation

The MessagePack format specification (github.com/msgpack/msgpack,
revision 2, 2017-08-09) and `msgpack-python` / `rmp` as the
implementations to check against.  Every vector in
`tests/msgpack_tests.nv` is from the specification's format table, its
worked examples or its timestamp section, so a reader can check the port
against the specification rather than against this package.

## Status

| function | implemented |
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
