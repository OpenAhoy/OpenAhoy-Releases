# Third-party notices and runtime dependencies

- Phosphor Icons: embedded interface icon SVG paths; MIT license text included at assets/third-party/Phosphor-Icons-LICENSE.txt.
- Management fonts: modified, renamed Resource Han Rounded and Nunito UI subsets, distributed under SIL Open Font License 1.1. License texts and exact source and payload digests are included in assets/management/fonts/.
- WeChat Official Account, X, and Xiaohongshu marks: third-party platform identifiers. Exact asset provenance/hashes are in assets/platforms/SOURCES.json; no affiliation or endorsement is claimed. These marks are not relicensed as OpenAhoy software.
- The editorial-notebook demo text/HTML/images are generic distributable template examples, not user articles; each version includes LICENSE.md and manifest.json. The demo images are AI generated, with no claim of exclusive copyright.
- Xiaohongshu workflow research: xpzouying/xiaohongshu-mcp (Apache-2.0), commit bb6fa2e. Independently implemented normal-browser adapter; no upstream source code or upstream binary is bundled.
- Python 3.11+, Node.js, Playwright and Google Chrome are target-local runtime dependencies, not bundled or silently installed. Their own licenses apply. The XHS adapter locates the Codex-managed Node/Playwright runtime when available.
- The included macOS-arm64 inline-binding-crypto helper is built from OpenAhoy-owned Swift source against Apple's system CryptoKit; no private user certificate, signing identity or standalone Apple library is bundled. Native hash and source hash are recorded in native/manifest.json.

- The included macOS-arm64 OpenAhoy video inspector targets macOS 13+ and uses Apple system AVFoundation and ImageIO. No separate media codec or framework binary is distributed.

OpenAhoy-owned Python/JavaScript/HTML/CSS and runtime helper are distributed for use with this plugin under LICENSE.md. Public availability is not an open-source license grant.
