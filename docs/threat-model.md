# Threat model (short)

| Attacker goal | What stops or limits it | Residual risk |
| --- | --- | --- |
| Register someone else's game and file takedowns against its real creator | Registration, checks and packages require store verification (page code, itch.io key or Steam publisher key). Certificates record method, URL and a hash of what was seen, so stores can re-check the code. | Open source: a bad actor can patch out the check in their copy. The certificate then lacks a verifiable store link, which a store can notice. The filer stays legally liable (17 U.S.C. 512(f)). |
| Forge a watermark pointing at a victim | 24-bit MAC under the creator's private key; certificates signed with Ed25519 | 1 in 16.7M chance per guess for the MAC alone; certificates can't be forged without the key |
| Strip watermarks | None technically. Fingerprints and traps still catch direct rips | Redraws and re-implementations beat all three |
| Find and remove traps | Values are secret; core traps don't change between builds, so diffing two builds only reveals build traps | A careful cloner who reads every string can still find some |
| Tune a clone to stay under the scores | Nothing (the matcher is open). Dodging it takes heavy changes, which makes the clone less of a copy | Accepted trade-off of open source |
| Use IndieWard to automate mass false notices | No send code exists; packages are drafts; packages refuse weak-evidence checks unless deliberately overridden; every notice carries perjury and 512(f) language | A determined abuser can write notices by hand anyway |
| Steal a creator's unreleased builds | Nothing is uploaded. Vault holds hashes and fingerprints by default (`--keep-copy` is opt-in) | Device compromise; keep backups encrypted |
| Steal a creator's keys | Keys live in `.indieward/keys` with user-only permissions; optional passphrase on the signing key | Device compromise; back up privately |
