# Format references and dependencies

The native Mail metadata reader independently implements the narrow format facts
in libyal/dtformats at commit `308ce8c38df2eb95a71b6e832b3f9803f0c4b169`,
particularly `dtformats/spotlight_storedb.py` and its YAML definition.
Reference author: Joachim Metz <joachim.metz@gmail.com> (upstream AUTHORS).
That reference is licensed under Apache License 2.0:
https://www.apache.org/licenses/LICENSE-2.0
No dtformats source is vendored. Changes here are an independent typed, bounded
identity-only reader with process-memory compressed-block fingerprints.

The locked `lz4` dependency retains its own BSD license and upstream LZ4 notices
in the installed distribution. No GPL research helper or decompiled native source
is included. Native trie/posting structures are independently implemented from
observed on-disk format facts documented in `docs/NATIVE_MAIL_INDEX_FORMAT.md`.
