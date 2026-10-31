# Neural audio and video watermarks: AudioSeal and Video Seal (P2-06)

Status: research, 2026-10-31. **Recommendation: don't add either backend now.** On IndieWard's test fixtures, neither beat the built-in marks on any edit we tried. Both cost a PyTorch install (hundreds of MB) plus model downloads. Revisit Video Seal with real game trailers (see "What would change this").

## What's current

| | AudioSeal | Video Seal |
| --- | --- | --- |
| Release | PyPI `audioseal` 0.2.0 (2025-12-17). No GitHub releases. | PyPI `videoseal` 1.0.1 (2025-07-21). Newer models (PixelSeal, ChunkySeal) only on GitHub `main`. |
| Licence | MIT, code and weights (weights were non-commercial before 2024-04) | MIT, code and weights |
| Message | **16 bits** (all public models) | v1.0: **256 bits** (v0.0: 96; PixelSeal 256; ChunkySeal 1024) |
| Weights | Hugging Face `facebook/audioseal`, ~93 MB (generator + detector) | `dl.fbaipublicfiles.com/videoseal/`, 228 MB (v1.0) |
| Install notes | Needs mono audio resampled to 16 kHz by the caller; `sample_rate` is ignored since 0.2 | The PyPI wheel looks for its model cards and `configs/attenuation.yaml` relative to the current folder, so `videoseal.load()` fails from a normal install. We worked around it (see the script). |

The card's premise has changed for video. Video Seal 1.0 carries 256 bits, so the full 64-bit IW-Mark payload fits. No split design is needed. AudioSeal is still 16 bits, so it can't carry the payload. For audio, the honest design is still "the neural mark proves presence, and the record ID comes from the built-in mark or the certificate".

Sources:
- AudioSeal: [repo and README](https://github.com/facebookresearch/audioseal), [PyPI](https://pypi.org/project/audioseal/), [model card](https://huggingface.co/facebook/audioseal), [paper (arXiv 2401.17264)](https://arxiv.org/abs/2401.17264)
- Video Seal: [repo and model zoo](https://github.com/facebookresearch/videoseal), [PyPI](https://pypi.org/project/videoseal/), [paper (arXiv 2412.09492)](https://arxiv.org/abs/2412.09492), [official v1.0 metrics](https://dl.fbaipublicfiles.com/videoseal/sav_256b_metrics.csv)
- Independent benchmark: [AudioMarkBench (arXiv 2406.06979)](https://arxiv.org/abs/2406.06979)

## Audio: built-in vs AudioSeal

Six 12-second clips from `tests/gamefixture.py` at 44.1 kHz: three synthetic music clips and three with a noise bed added. The built-in result uses the informed check against the vault reference. AudioSeal detection means the detector's probability is above 0.5. Its message is the 16-bit value we embedded, so "exact" means all 16 bits came back.

| Edit | Built-in (informed, 64 bits) | AudioSeal detected | AudioSeal 16 bits exact | AudioSeal bit accuracy |
| --- | --- | --- | --- | --- |
| none | 6/6 | 6/6 | 3/6 | 97% |
| MP3 128 kbps | 6/6 | 6/6 | 3/6 | 96% |
| MP3 64 kbps | 6/6 | 6/6 | 4/6 | 98% |
| Ogg Vorbis q2 | 6/6 | 6/6 | 1/6 | 94% |
| AAC 96 kbps | 6/6 | 6/6 | 2/6 | 95% |
| tempo ×1.05, pitch kept | 1/6 | 0/6 | 0/6 | 85% |
| tempo ×0.95, pitch kept | 0/6 | 0/6 | 0/6 | 83% |
| speed ×1.05, pitch shifts | 0/6 | 0/6 | 0/6 | 56% |
| trim the first 3 s | 6/6 | 6/6 | 0/6 | 88% |

Quality: SNR 32.1 dB built-in, 26.3 dB AudioSeal, so AudioSeal adds more noise. AudioSeal took 0.5 s to embed a 12 s clip on a CPU, after a one-off ~8 s warm-up. No unmarked clip was flagged (0/6).

**Speed changes defeat both.** That matches the outside benchmarks: AudioMarkBench reports AudioSeal missing 25–73% of watermarked music under time stretch. Meta's paper reports 0.99 detection at speed ×1.25 on speech, but that wasn't what we saw on music. The 16-bit message isn't reliable even untouched (exact in 3 of 6 clips), so it couldn't safely carry even part of a record ID.

## Video: built-in vs Video Seal 1.0

Three 10-second 640×360 30 fps clips from `tests/gamefixture.py` (moving art plus a HUD bar), marked with each backend and saved as H.264 CRF 18. The built-in result uses its blind check, z ≥ 7. For Video Seal, the 64-bit payload is repeated 4 times across the 256 bits; reading averages every frame and sums the 4 soft copies. "Exact + MAC" means all 64 bits came back and the creator's MAC accepted them.

| Edit | Built-in (blind, 64 bits) | Video Seal exact + MAC | Video Seal bit accuracy |
| --- | --- | --- | --- |
| as saved (CRF 18) | 3/3 | 3/3 | 100% |
| H.264 CRF 28 | 3/3 | 0/3 | 85% |
| H.264 CRF 35 | 0/3 | 0/3 | 66% |
| half size + CRF 28 | 0/3 | 0/3 | 63% |
| crop 10% per side | 0/3 | 0/3 | 58% |
| re-timed to 15 fps | 3/3 | 1/3 | 98% |
| trim the first 3 s | 3/3 | 0/3 | 95% |

Quality: Video Seal PSNR 49 dB before encoding, at the default strength (0.2). It took about 55 s to embed a 10 s clip on a CPU, and no unmarked clip passed the MAC check.

Meta's own figures for v1.0 are much better: 98% bit accuracy at H.264 CRF 30, 99.9% after resizing, and 94% after a crop to 0.71 of each side. Those were measured on high-resolution natural video (SA-V, about 1350×1050). Our fixtures are small, synthetic and flat-coloured, and that likely explains most of the gap. **Treat our video numbers as "not proven on game-like footage" rather than "Video Seal is weak".** Crops beat both backends here.

## What would change this

- **Video:** a test on two or three real trailers at 1080p, ideally from the P1-04 dogfood game. Use a real error-correcting code over the 256 bits (for example BCH carrying the 64-bit payload) instead of 4× repetition; 85% bit accuracy may then be enough. If it then holds the payload through CRF 28–30, half size and a 10% crop, a `video --backend videoseal` extra would earn its install weight. Raising the strength above 0.2 is untested and would cost quality.
- **Audio:** a public AudioSeal model with 32 or more reliable bits, or one that survives tempo changes on music. Until then, the built-in mark plus audio fingerprints cover more.

## Reproduce

- `TORCHDYNAMO_DISABLE=1 python scripts/research_audioseal.py 6`
- `TORCHDYNAMO_DISABLE=1 python scripts/research_videoseal.py WORKDIR 3` (see the script's docstring for WORKDIR)

Synthetic fixtures make the numbers vary a little from run to run, because record IDs are random.
