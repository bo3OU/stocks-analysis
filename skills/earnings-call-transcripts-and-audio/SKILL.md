---
name: earnings-call-transcripts-and-audio
description: Get earnings call transcripts or audio for a company, and transcribe audio locally with Whisper. Use when an analysis needs the call (prepared remarks vs Q&A). Explains what was reachable and what was blocked.
---

# Earnings call transcripts and audio

## What worked: a free third-party transcript
- stockanalysis.com lists transcripts per ticker (`https://stockanalysis.com/stocks/<ticker>/transcripts/`) including earnings calls, investor days and conference talks (SNDK: 25 entries, Feb 2025 to Oct 2026). Each transcript page credits Quartr as the provider.
- SNDK Q1 FY2027 call (2026-10-29): `https://stockanalysis.com/stocks/sndk/transcripts/725299-q1-2027/`. Plain `curl` returned HTTP 200 (364 KB HTML). Converting to text gave about 9,800 words with speaker names on their own lines (operator, IR, CEO, CFO, 12 analysts), prepared remarks and Q&A. Use the converter in `sec-edgar-access` (Working with filings).
- No paywall or login was seen. It is a third-party transcript: label it as such (provider Quartr, hosted by stockanalysis.com), note that wording may contain errors, and do not present it as the company's official transcript. Terms of use were not reviewed: keep it for analysis, do not republish.
- Use WebFetch only to read the listing/summary. For exact quotes, save the HTML with curl.

## What was blocked or gated (do not bypass)
- SanDisk's IR site (`investor.sandisk.com`) returned 403 "Access Denied" (Akamai) to curl and to headless Chrome. The company's own press-release page on `www.sandisk.com` loads but only points to the IR site for the webcast.
- AMD's IR event page loads in the browser and links the call audio, but it opens a webcast player (`edge.media-server.com/mmc/p/<id>/`) that requires registration (first name, last name, e-mail, company, country). Not completed. The same page links the slide deck as a public PDF on a CloudFront CDN, which downloaded fine with curl.
- SLB, Micron, NVIDIA, Tesla, Apple, Seagate and Netflix IR sites were blocked (see `playwright-browsing`). NSE India call-recording archives failed at the network level.
- Result: no real earnings-call audio was obtained in testing. If the user supplies an audio file (or has an account for a replay), use the pipeline below. A speech-to-text transcript of audio the user is entitled to is the right fallback when no transcript exists.

## Local Whisper (verified on synthetic speech)
- Installed: `mlx-whisper` in a Python 3.12 venv (Apple Silicon, M4 Pro, 48 GB). `ffmpeg` and `ffprobe` are installed via Homebrew.
- Convert to 16 kHz mono WAV, then transcribe:

```bash
ffmpeg -loglevel error -y -i call.mp3 -ar 16000 -ac 1 call.wav
.venv/bin/mlx_whisper call.wav --model mlx-community/whisper-large-v3-turbo \
  --output-dir out --output-format txt --language en
```
  Other output formats exist (srt, json, vtt). There is no speaker labelling, so Q&A turns are not attributed.
- Test result: a 81-second clip (macOS text-to-speech reading real transcript text) transcribed in about 24 s on the first run (includes model download) and 3.0 s warm, roughly 27x real time; word error rate against the source text was 1.0% (203 reference words). A one-hour call should take a few minutes. Caveat: synthetic speech is far cleaner than a phone-line call with accents, overlap and jargon, so expect a higher error rate on real audio. Spot-check numbers and names against the filed press release.
- Not tested: real call audio, `yt-dlp` (installed in the venv). Downloading from YouTube may breach its terms; check before using it.
- A transcript of a call is not the call's prepared remarks plus Q&A unless the source says so: label what was actually reviewed (full call, prepared remarks only, or release only).

## Verification
Cross-check key figures spoken on the call (revenue, guidance, buybacks, split terms) against the 8-K exhibit 99.1 earnings release, and note any difference. For SNDK, the release stated revenue $11.0B, a $5.0B buyback and the 8-for-1 split effective 2026-11-19.
