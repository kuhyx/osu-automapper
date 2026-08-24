# Using the local lazer library

The lazer install at `~/.local/share/osu` is the source of the sweep's songs and
of every human map in the blind test. This documents how to get maps and audio
out of it, and — more usefully — which approaches **do not work**, so they are
not retried.

## Layout

`~/.local/share/osu/files` is a content-addressed blob store: 16 top-level
shards, ~16k files, no extensions, names are SHA-256 hashes. `ls | wc -l` on the
root returns 16 (shards), not the file count.

Blobs are identified by sniffing their first bytes:

| signature | kind |
|---|---|
| `osu file format` in the first 64 bytes | beatmap |
| `ID3` / `\xff\xfb` | mp3 |
| `OggS` | ogg |
| `RIFF` | wav |
| `\x89PNG` / `\xff\xd8` | image |

Measured on this install: 3,149 beatmaps (2,867 std, 140 taiko, 103 mania, 39
catch), 2,891 audio blobs, 9,325 images, across 490 distinct beatmap sets.

## Joining a map to its audio

A `.osu` names its audio as a *filename* (`AudioFilename: audio.mp3`), but the
blob store has no filenames. The link lives in `client.realm`.

**What does not work — do not retry:**

- **Byte-proximity scraping of `client.realm`.** Pairing each filename string
  with the nearest 64-hex hash looks plausible and produces thousands of pairs.
  It is wrong: validating those pairs by content type showed **1,141 of 2,445
  mismatched** (47%), including two different `.osu` files mapped to one hash and
  a 910 KB blob mapped to a `.osu`. Any join must be validated by opening the
  blob and checking its type — a plausible-looking pair count proves nothing.
- **Python Realm readers.** `pip install realm` installs an unrelated package.
  There is no maintained Python reader for Realm's file format.
- **Reading `client.realm` while lazer is running.** It holds a lock. Copy the
  file first and read the copy.

**What works:** join on audio tags plus duration.

1. `ffprobe` every audio blob for `title`/`artist`/`duration`.
2. For each map, take its last hit-object timestamp.
3. Match maps to audio whose tags equal the map's `Artist`/`Title` and whose
   duration contains the map (`duration >= end - 2s`, and not absurdly longer).
4. Keep only unambiguous winners.

This joined **400 of 2,867 std maps**, all 400 verified to point at real audio.
The ceiling is not the method — only 482 of 2,891 audio blobs carry tags at all.
400 songs is far more than the sweep or a blind test needs, so this was accepted
rather than pursued further.

## Why this matters for the blind test

`pack_blindtest` packs every entry as a difficulty of **one set sharing one
audio file**. A blind test that mixed songs would give the answer away through
the audio alone. So a valid pack needs human *and* generated maps of the **same
song** — which is exactly what the join above provides: e.g. Megalovania has
seven human difficulties spanning 1.61★ to 6.11★ on the same audio blob, and the
sweep generates AI maps for that same song.

Match the AI maps' target difficulty to the human maps' measured star rating, or
difficulty becomes the tell rather than mapping quality.
