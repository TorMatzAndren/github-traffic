# Changelog

## v0.3.0 — Repository Metadata Semantics

### Added
- `subscribers_count` repository metadata support
- `subscribers_count` snapshot history support
- Extended metadata timeline query projections
- Extended summary JSON metadata payloads

### Changed
- Clarified GitHub repository watcher semantics
- Preserved both:
  - `watchers_count`
  - `subscribers_count`
- Improved repository metadata normalization

### Fixed
- Corrected misleading repository watcher interpretation
- `watchers_count` is now treated as GitHub's star-aligned watcher field
- Actual repository watchers/subscribers are now stored separately through `subscribers_count`

### Notes
GitHub's repository API exposes:
- `watchers_count`
- `stargazers_count`
- `subscribers_count`

For repositories:
- `watchers_count` mirrors `stargazers_count`
- `subscribers_count` represents actual repository watchers/subscribers

GTI now preserves all three explicitly for accurate observability and analysis.
