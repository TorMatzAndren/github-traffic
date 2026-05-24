# Changelog

## v0.3.0 — Repository Metadata Semantics

### Added
- `subscribers_count` repository metadata support
- `subscribers_count` metadata snapshot support
- `subscribers_count` summary JSON/query projection support

### Changed
- Preserved GitHub's `watchers_count` field for API fidelity
- Added separate `subscribers_count` storage for the actual GitHub "watching" count
- Extended repository metadata snapshots to include subscriber history

### Fixed
- Corrected misleading repository watcher interpretation
- Fixed metadata snapshot normalization so `subscribers_count` is persisted alongside stars, forks, and issues
- Backfilled current metadata from stored raw GitHub repository API responses

### Notes
GitHub's repository API exposes both `watchers_count` and `subscribers_count`.

For repositories:
- `watchers_count` mirrors `stargazers_count`
- `subscribers_count` represents the actual GitHub "watching" count shown in the UI

GTI now preserves both values explicitly so repository attention metrics are not conflated.
