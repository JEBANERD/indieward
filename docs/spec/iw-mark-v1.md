# IW-Mark v1 and IndieWard certificate v1 (open format)

Status: draft 1, 2026-10-28. Published so stores, platforms and AI companies can read and honor IndieWard marks and certificates. Licensed CC BY 4.0.

## 1. Payload (64 bits)

| Bits | Field | Meaning |
| --- | --- | --- |
| 63..24 | `record_id` (40 bits) | Random ID of an asset record in the creator's certificate |
| 23..0 | `mac` (24 bits) | `HMAC-SHA256(mac_key, "IW-Mark v1|" ‖ record_id as 5 big-endian bytes)`, first 3 bytes |

Display form: `IW1-xxxxx-xxxxx` (record_id as 10 lowercase hex digits).

Anyone can read `record_id`. Only the holder of `mac_key` can say whether a payload is genuine. A random guess passes with probability 2^-24. The signature that makes records unforgeable lives in the certificate (section 3), because a 64-bit mark can't hold a 512-bit Ed25519 signature.

## 2. Embedding profiles (built-in backend)

Layout derivation is public: `seed = SHA-256("IndieWard IW-Mark v1|" ‖ label ‖ ":" ‖ n)`, first 8 bytes big-endian, seeds NumPy's PCG64 `default_rng`. With it: a permutation assigns each of `n` features to bit `i mod 64`, and a ±1 chip per feature. Pattern sign for feature k = `chip[k] · (2·bit[bit_of[k]] − 1)`.

| Profile | Features | Strength | Detection |
| --- | --- | --- | --- |
| `image` | Luma resampled (box) to 256×256; orthonormal 2D DCT; coefficients with 4 ≤ u+v ≤ 96, u,v ≤ 80 (n = 4471) | ±0.04 × local DCT envelope (7×7 mean of \|C\|), spatially masked by local activity | Informed: align the suspect to the stored 256×256 reference (crop search 0–5% per side), subtract it, correlate |
| `audio` | Band log-power, 40 Hz bands from 200 to 7000 Hz (n = 170), analyzed at 16 kHz, 1024/256 STFT | ±0.04 nepers per band, gated in time by a 61-slot pseudo-random ±1 sequence of 0.2 s slots | Informed: align to the stored band reference, subtract, whiten per band, correlate with band pattern × time chip |
| `video` | Image-profile features per frame | ±0.06 × envelope, gated by a 61-slot sequence of 0.3 s slots | Blind: frames at 10 fps, 1-second moving-average removed, best offset over one chip period |

Detection statistic: empirical z-score against 256 random decoy patterns (and, for audio, random decoy time chips). Thresholds: z ≥ 6 (image, audio informed), z ≥ 7 (video, best-of-offsets). Implementations may use other backends carrying the same 64-bit payload; the record in the certificate names the backend (`watermark.backend`).

### 2.1 TrustMark backend (`trustmark-q-bch4-v1`, images, optional)

A blind backend: anyone can read the payload without the creator's reference, so a store or platform can read `record_id` from an image on its own.

- **Model:** [Adobe TrustMark](https://github.com/adobe/trustmark) (MIT, code and weights), variant `Q`, CPU or GPU. Weights come from TrustMark's official host and must match its published MD5 checksums.
- **Packing:** TrustMark's 100-bit secret in `BCH_4` mode = 68 data bits + 28 BCH parity bits + 4 schema bits (`0010`); corrects up to 4 bit errors. The 68 data bits are the 64-bit payload (bit 63 first) followed by the tag `0001`.
- **Reading:** decode in TrustMark `binary` mode. Accept only if BCH decoding succeeds, the schema is `BCH_4`, and data bits 64–67 equal `0001`. Bits 0–63 are the payload: `record_id` and `mac` as in section 1.
- **Genuineness:** only the creator's `mac_key` confirms the `mac` (section 1). Unmarked images sometimes decode as a valid BCH packet; the tag and MAC together bring a false hit below one in a billion per image.
- **Measured** (IndieWard's test art, 12 images at 512×512): PSNR ≈ 41 dB (built-in: ≈ 46 dB). Payload read back after JPEG 90/75 12/12, JPEG 50 10/12, half-size 12/12, half-size + JPEG 75 10/12, 5% crop per side 12/12, 10% crop 11/12, 2° rotation 11/12. No unmarked image passed the tag and MAC checks.

## 3. Certificate (JSON)

```json
{
  "format": "IndieWard certificate v1",
  "issued_at": "2026-10-28T23:00:00Z",
  "creator": {"name": "...", "contact": "...", "public_key_ed25519": "<base64 raw 32 bytes>", "key_fingerprint": "<first 32 hex of sha256(pubkey)>"},
  "project": {"id": "...", "name": "...", "first_published": "YYYY-MM-DD", "verification_code": "IW-XXXX-XXXX-XXXX-XXXX"},
  "verified_store_links": [{"store": "itch", "url": "...", "method": "page|itch-key|steam-key", "verified_at": "...", "evidence_sha256": "...", "detail": {}}],
  "assets": [{"record": "IW1-...", "kind": "image", "category": "art", "name": "...", "sha256": "...", "size": 0, "registered_at": "...", "watermark": {"format": "IW-Mark v1", "backend": "...", "marked_file_sha256": "..."}}],
  "builds": [{"build_id": "...", "label": "...", "engine": "...", "registered_at": "...", "manifest_sha256": "...", "trap_commitment": "..."}],
  "documents": [{"kind": "...", "title": "...", "sha256": "...", "added_at": "..."}],
  "statement": "...",
  "signature": {"alg": "Ed25519", "value": "<base64>"},
  "digest_sha256": "<hex>",
  "timestamps": {"rfc3161": {"status": "...", "service": "...", "time": "...", "token_b64": "..."}, "opentimestamps": {"status": "...", "service": "...", "token_b64": "..."}}
}
```

- **Signed body** = every field except `signature`, `digest_sha256`, `timestamps`, serialized as canonical JSON (keys sorted, no whitespace, UTF-8, `ensure_ascii=false`).
- `digest_sha256 = SHA-256(signed_body ‖ signature_bytes)`. Both timestamps cover this digest.
- **Verification code** = `"IW-" + base32(SHA-256("IndieWard verify|" ‖ pubkey)[:10])` in four groups of four. A store can check that the code appeared on the listed page.
- **Trap commitment** for a build = `SHA-256(join("|", c_1..c_n))` where `c_i = SHA-256(salt ‖ "|" ‖ tier ‖ "|" ‖ kind ‖ "|" ‖ value)`. A takedown package reveals the salt and only the traps found in the suspect, so a third party can recompute the commitment.

## 4. Verification code placement

Creators paste the verification code into the public store description: Steam "About this game", itch.io page description, Roblox experience description. Stores may check it via their own data.

## 5. Rights signals

IndieWard can emit robots.txt AI-crawler opt-outs, a `Content-Signal: search=yes, ai-train=no, ai-input=no` line, the CAWG `cawg.training-mining` assertion with `notAllowed` entries, and `tdm-reservation: 1`. These express preferences; they're not enforcement.
