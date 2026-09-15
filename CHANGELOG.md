# Changelog

Every published version, newest first. This file is on the publish
allow-list, so it travels with the package: it is the only thing a
consumer deciding whether to upgrade can read.

## 0.0.2 — 2026-09-15

README rewritten to the package README style guide (docs/writing-a-readme.md); no change to the interface.

## 0.0.1 — 2026-09-11

The **interface**, before anyone implements it.  Every signature, every
type and every effect row is published; every body is `todo()`, and the
release is stamped `NOT IMPLEMENTED — interface only`.  Adding this
package works and calling it panics.

- Three surfaces.  `mpack` is the value tree and the encoder;
  `mpackdec` is the same decoder fed a chunk at a time, for a document
  that arrives off a socket in pieces; `mpackserde` is the bridge to
  the standard library's `Serialize` and `Deserialize`.
- The whole format, not a subset: every integer width, both float
  widths kept apart because the width is on the wire, `str` and `bin`
  as the separate families they are, `array`, `map`, `ext`, and the
  `-1` timestamp extension in all three of its widths.
- `MsgUint` for a `uint 64` above 2^63, which does not fit a signed
  `Int`.  A separate case rather than a silent reinterpretation,
  because a reader that saw `-1` for `18446744073709551615` would have
  no way to tell it from an actual `-1`.
- `MsgMap` as a LIST of pairs, because a MessagePack key is any value
  and the specification permits duplicates without saying which wins.
  `get` answers the first; `as_map` shows both.
- A depth limit, defaulting to 64, on the decoder rather than on the
  call.  An array header is one byte and can open a level, so a
  five-byte message can ask for five levels of recursion and a large
  one for a hundred thousand.
- Named refusals with offsets: the reserved `0xc1`, a truncation that
  says how many bytes it still wanted, a non-UTF-8 `str`, nesting past
  the limit, trailing bytes, an accessor given the wrong type, a
  malformed timestamp, and a destination buffer too small.

**The serde bridge is writable today, both halves**, and that is the
finding worth recording.  postcard-nv publishes a read half that is not,
because a nameless format's member 2 begins where member 1 ended and the
trait's cursor is not threaded; MessagePack writes a key in front of
every member, so `field` scans the map at the parent's own offset and
the parent never has to move.  And postcard cannot write a `Some`
because the trait announces only `None`; MessagePack needs no `Some`
marker, since `nil` has its own format byte and `Some(x)` is `x`.  Both
of postcard's blockers are consequences of being nameless and untagged.

**Four places the bridge is still short of the format**, each with the
value tree as its answer: one integer hook, so `uint 64` above 2^63 is
unreachable; one float hook, so everything goes out as `float 64`; no
bytes hook at all, so the `bin` family is unreachable — the standard
library declares `Serialize` for `Int`, `Float`, `Bool` and `Str` and
nothing else; and no way to open a map whose keys are not strings.

**No device claim.**  There is no `tests/embedded_probe.nv`: the surface
speaks `Bytes`, `Str` and `Result`, and none of the three links at
`@tier(embedded)` today.  cbor-nv is the one of this pair with a device
half, because the grid's row for it says the embedded tier prefers CBOR.

**No dependencies.**  Not leb128-nv or zigzag-nv — MessagePack's
integers are big-endian fixed width and not variable-length quantities
at all — and not serde-nv, because the traits are the standard
library's and a dependency would put a second MessagePack
implementation in every consumer's assembly.
