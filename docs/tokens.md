# Tokens

`*Token` classes: (21 descendants)

Names are relatively similar to other libs out there, but emphasis is on keeping things as simple as possible.
Some token names are intentionally shorter (easier to read).

Some differences with ruamel for example:

- Shorter names:
    - `BlockMapToken` corresponds to `BlockMappingStartToken`
    - `FlowEndToken` corresponds to `FlowSequenceEndToken`
- More "intuitive" names (naively simpler... self-explanatory):
    - `DashToken` corresponds to `BlockEntryToken` (since it corresponds to `-` character...)
    - `CommaToken` corresponds to `FlowEntryToken`

Tokens are represented by objects in such a way that mostly no if/elseif cascades are needed while parsing.


# Scanning

The scanner has a simple equivalent of a 2-pass approach (see `Scanner().tokens()`)

- Pass 1 (see `_raw_tokens()`) yields `*Token` objects, as seen from input.
- Each token can optionally yield more "auto-filled" tokens (see the `auto_*` fields)
- Example "auto-filled" token: `DocumentStartToken` is always yielded, even if not explicitly in the input
- This ensures a consistent sequence of tokens coming in to the `TokenVisitor` implementations

Quick overview of `Token`-s with custom auto-fill behavior:

```
*Token:
    + auto start doc
    yield self

DocumentStartToken
    + end prev doc if started
    + mark doc started
    yield self

DocumentEndToken
    ! require flow terminated (don't auto-terminate)
    + unravel simple key, block
    + mark doc ended
    yield self

DirectiveToken
    ! require no doc started
    + handle %YAML special case, record directive
    yield self

ExplicitMapToken
    + auto start doc, map block
    + yield KeyToken

DashToken
    + auto start doc, seq block
    yield self

ColonToken
    + auto start doc, map block
    + unravel simple key
    + yield ValueToken

ScalarToken
    + auto start doc
    accumulate simple key (don't yield)
```
