# Claudio Symphony 🎼

> **Hear your Claude Code sessions.** Every tool call, file edit, and finished thought becomes a soft, in-key sound — ambient music that moves with your AI pair-programmer.

Claudio listens to Claude Code's hook events and turns them into generative, always-in-key ambient music. Twenty tool calls in three seconds become one soft blur of tones, not twenty separate dings — because that's the difference between music and Slack notifications.

It is **not** a notification system. It's a room your Claude session is happening inside. After about twenty minutes you stop hearing it as *music* and start hearing it as *the room* — and the room moves with your work.

![Claudio web console — a living constellation of voices that bloom in real time as Claude plays them](docs/web-console.png)
> *The `claudio web` console: each voice is a glowing orb that lights up the instant Claude triggers it. Tune everything live; switch any of 40 presets with a click.*

---

## ⚡ Quick start

Install it as a Claude Code plugin — two lines, pasted right into Claude Code:

```
/plugin marketplace add allaspectsdev/claudio-symphony
/plugin install claudio-symphony
```

The hooks wire themselves — no editing `settings.json`. Install the one synthesis dependency explicitly with `python3 -m pip install numpy`, then run **`claudio setup`** once to render sounds. Hooks never install packages or access the network on your behalf, and **`claudio doctor`** verifies everything anytime. Prefer a hands-on setup, or not using plugins? See [Install](#-install).

> **macOS / Linux.** The plugin hooks call `python3`, which is standard there. On Windows `python3` often isn't on PATH — use the [manual install](#-install) (or alias `python3`) for now.

---

## ✨ Why you'll love it

- 🎧 **It's calm, not noisy.** No beeps, no buzzes, no notification DNA. Soothing tones, soft mallets, distant bells — everything tuned to the same key (A = 432 Hz) so it never clashes, no matter how fast Claude is moving.
- 👂 **You can *hear* what your agent is doing.** A pluck for a tool call, a chime when a sub-agent returns, a slow bloom when a turn finishes. Without looking, you know whether Claude is grinding, waiting, or done.
- 🪟 **Hear every session at once.** Running Claude in five terminals? Give each project its own room. Now the chord of your whole workspace is audible — you can tell the quiet one finished and the busy one hit an error, eyes closed.
- 🎹 **40 presets, each a complete world.** Sunlit music box, lush cathedral, near-silent rainfall, plucked koto, vibraphone lounge, handbell carillon, Rhodes warmth… switch live, mid-session, with one command.
- 🖥️ **A console you'll leave open just to watch.** A living constellation of your voices blooms in real time as Claude plays them — and the canvas *narrates the work*: a finished turn breaks across the screen as a slow wave of light, a sub-agent return is a smaller echo, "needs you" pulses the edges. Five physics-driven views (orbs that nudge each other, ripples, ribbons, a particle current, orbiting stars). Click an orb to hear it; drag a slider to tune.
- 🎤 **It jams with the room.** Hit **Listen** and Claudio detects what you're humming — or what music you're playing — and re-keys its whole palette to match, live. Put on headphones, enable **mic monitor**, and your own voice or instrument comes back drenched in Claudio's reverb and delay: you're not listening to your agent anymore, you're *in the band with it*. Turn on a chord progression and the room cycles changes underneath you while you play.
- 🎚️ **Tune everything, or nothing.** Sensible defaults out of the box — or open the TUI / web panel and shape every voice, reverb tail, and event mapping to taste.
- 🪶 **Featherweight & private.** Pure Python, one dependency (numpy), no daemon, no telemetry, no network. Hooks fire async with a 1-second timeout, so they *never* slow Claude down.

---

## 🎧 Listen first

Pick the room you want to work in. **`meadow` is the default** — bright, friendly, no drone. Switch any time, live, no restart:

```bash
claudio preset use cathedral
```

A few of the flagship rooms:

### 🌳  `meadow` — the happy one *(default)*
> *Wooden felt-mallets and kalimba in a sunlit room. A-major pentatonic — universal happy mode, no possible dissonance.*

Bright, satisfying, soft attacks. The "thock" of felt on wood for tool calls, kalimba tines for file edits, a small bird-chirp for shell commands, a 9-second major-triad bloom when Claude finishes. Like a music box in a sunny room.

### 🏛️  `cathedral` — the lush one
> *Modal drone bed with a full event palette. Eight voices. Always-on. The Eno / Budd / Frahm lane.*

A low drone never stops. Soft felt-piano notes resolve as tools complete; faint airy tones pass by during bash commands; a tuned bell rings when a sub-agent finishes. Nothing has a melody, nothing repeats — the room just moves with the work.

### 🌧️  `rainfall` — the quiet one
> *Sparse drops in a still room with rare long blooms. Silence is the canvas.*

Most of the time you hear nothing. PostToolUse plays a tiny 250 ms drop — a single bead of water on a still pond. Once a minute or two, a 25-second pad blooms in the distance and recedes. Late-night, deep-focus, almost-silent.

### 🎋  `koto` — the contemplative one
> *Plucked silk strings and a temple bowl in the A In-Sen scale. Spare, deliberate, like working through a tea ceremony.*

A different emotional space from the bright A-major family — minor-leaning, Japanese, unhurried. Koto for melody, bowl for sustains, mokugyo (wooden fish) for accents.

### 🌌  …and 36 more
Crystal glass bowls (`glassbright`), vibraphone (`lounge`), handbell carillon (`peal`), steel pan (`isleshine`), hammered dulcimer (`shimmerwire`), Rhodes EP (`tinewarm`), vocal-oo choir (`choirloft`), nylon guitar (`courtyard`), ocarina (`clayround`), santoor (`sunraga`), and many more — each a complete, render-tested room.

> **Hear them all in seconds:** `claudio audition` walks every preset on your speakers, or open the web panel and click ▶ on any card.

---

## 👂 Hear all your sessions at once

This is the part you didn't know you wanted. Claudio routes sound **per session**, with three lookup tiers (most specific wins):

1. **Session pin** — `claudio session pin <id> cathedral` → that one terminal, forever
2. **Directory rule** — `claudio rule add "/Users/me/quiet*" rainfall` → every session under that path
3. **Global default** — `claudio preset use meadow` → the catch-all

```bash
claudio sessions
#  #  sid       pin  preset      ago    src       cwd
#  1  33159931       meadow      0m     default   ~/Projects/shipping-app
#  2  ab12cd34  📌    rainfall    3m     pin       ~/Projects/quiet-stuff
```

Give your noisy refactor a different voice than your delicate prod fix, and the two coding sessions become *audibly* distinct. You stop alt-tabbing to check on them — you just *hear* which one needs you.

---

## 🖥️ The web control panel

```bash
claudio web      # opens a local, no-deps control panel in your browser
```

A "warm nocturne observatory" you'll actually want to leave open:

- 🌠 **A living constellation** — each voice is a glowing orb in a slow-drifting galaxy that **blooms in real time** the instant Claude triggers it — and when one bursts, it *pushes* its neighbours, so the whole sky wobbles like one fabric. Watch your session play itself.
- 🌊 **Five ways to watch** — hover the canvas for the ✦ ◍ ≈ ❋ ✸ switcher: the orb **constellation** (orbs bloom and nudge their neighbours), a **still pond** of ripples, **flowing tides** of silk ribbons, a **flow field** that sprays particles into a drifting current, and **gravity** where each voice is a star and sounds fling orbiters that slingshot around it — all real-time physics.
- ✨ **The light reacts to the work** — on top of every view, the moments that matter announce themselves: when Claude **finishes a turn** a luminous shockwave rolls out across the canvas; a **sub-agent** returning is a quieter ripple; a **notification** glows the edges; session start sweeps, session end fades. Tool calls stay calm, so the big beats land. You can feel the shape of a session from across the room.
- 🎚️ **Tune anything live** — per-voice gain, reverb, echo; remap any event; switch presets; set per-session rules — all written to the same files the CLI and hooks read, so every change is instant.
- 🔊 **The Sounds tab puts cause and effect in one view** — "Claude does this → you hear that" up top, the full voice rack right below. Hover any event and hit **✎** to jump straight to that voice's controls; clicking a constellation orb does the same. Three tabs total: **Sounds · Music · Setup**.
- 🔭 **Browse 40 presets** in a searchable gallery, audition with one click.
- 🎵 **Music tab** — global scale override, quantize-to-tempo, MIDI song mode, and a live **root-note** readout.
- 🎶 **Chord progressions** — cycle the whole room through the four-chord pop song (I–V–vi–IV), doo-wop, the Andalusian cadence, Pachelbel's Canon, or a lo-fi ii–V–I–vi — or build your own from thirteen chords. The live chord glows in the Music tab and sweeps toward the next change. No daemon, no clock process: the chord is pure wall-time math, so every session and the browser always agree on where you are in the cycle. The drone holds its A pedal underneath — the classic ambient move — or flip **Drone follows chords** (Setup tab, `claudio drone follow on`) and the bed walks the progression's roots with you. And if you've mic-jammed to a new key, the whole progression transposes too. CLI: `claudio chords pop`, `claudio chords Am F C G`, `claudio chords every 12`, `claudio chords off`.
- 🎤 **Jam with the room** — hit **Listen** and Claudio tunes its key to whatever's around you. (See below.)
- 🎨 **Make it yours** — the **⋯ → Options** menu re-skins the whole console to any accent color (six presets or a custom hue — orbs, glows, sparklines, everything), and sets headphone mode, mic monitoring, and how lively the constellation feels. Saved per-browser.

Pure Python standard library on the backend (`127.0.0.1` only), Fraunces + Hanken + Space Mono on the front. No build step, no node_modules.

### 🎤 Listen — jam with the room

Hit **🎤 Listen** in the top bar and Claudio starts singing along with whatever's happening around your computer. It listens through your mic and **detects the note you're humming** — or the key of the music you're playing, a guitar, a piano down the hall — and **re-keys its entire palette to match, live**. Hum a note and watch the button flip to it; put an album on and Claudio slides into its key. The whole room shifts with you; nothing re-renders, so it's instant. Turn the **drone bed** on (Setup tab, or `claudio drone on`) and it's the best part: the bed **bends to your voice within about half a second** — hum a new note and hear the room's foundation lean over to meet you.

**Tap to latch it on** (it keeps listening until you tap again), or **press-and-hold to jam only while held** — handy for grabbing one note and letting go. Either way, **turning Listen off restores the key you were in before** — the mic is a live performance mode, not a permanent setting. The on-button readout shows the note it's settled on and only changes when one note clearly wins, so it reads steady instead of twitchy.

It stays out of its own way without any audio routing or extra dependencies: Claudio is sparse and ambient, so it **listens in the gaps** between its own notes (ignoring the ~0.4s right after it plays), runs a noise gate so quiet hiss is ignored, and only commits to a note that *holds steady* for a beat. If it ever does catch its own tail, that just re-affirms the key it's already in — so it settles instead of drifting. Pitch detection is plain Web Audio autocorrelation in the browser; the mic stream is released the moment you toggle it off.

> Set the key by hand too: the **Root note** field in the Music tab (↺ back to A), or `claudio root C` / `claudio root -2` / `claudio root off` from the CLI. Heads-up: an always-on drone preset (e.g. `cathedral`) gives the mic fewer gaps to listen in — the bright, sparse presets jam most readily.

**🎧 Headphone mode — the real jam setup.** Wearing headphones? Tell Claudio in **⋯ → Options** and Listen gets sharper: with the output in your ears the mic physically can't hear Claudio, so the listening-in-the-gaps filter switches off entirely and it tracks you continuously. Then flip on **Mic monitor** — mic passthrough with **Claudio's reverb and delay on your own voice or instrument**, straight into your headphones. You're processed into the same room Claudio is playing in, and now you can actually **jam with your Claudio**: it follows your key, you ride its texture. A **Monitor space** slider runs dry ↔ drenched. Monitoring is headphones-only by design, so it can never feed back through your speakers, and none of it leaves the browser.

**Take it further: jam over changes.** Turn on a [chord progression](#-the-web-control-panel) (Music tab → Chord progression, or `claudio chords pop`) while Listen and the monitor are running — Claudio cycles the four-chord song (or your own changes) underneath you, in your key, while your voice floats through its reverb. A coding-session ambient system is now, quietly, a backing band.

---

## 🎙️ Record & share your sounds

Found a preset + workflow that sounds *amazing*? Capture it and show it off.

```bash
claudio record           # record 30 seconds (the default)
claudio record 120       # record up to 5 minutes (300s max)
claudio record --drone   # add a faded drone bed for a more song-like clip
claudio record stop      # finish early and save right now
claudio record list      # see your saved clips
```

Here's the neat part: because Claudio already knows every sound it plays, recording **doesn't touch your mic or system audio** — it mixes the *exact* samples back into one clean track. Only Claudio, no room noise, no other apps, no virtual-audio-device setup. Clips land in `recordings/` as a `.wav` plus a small `.m4a` for easy sharing.

**Optional drone bed.** The drone stays **off** for everyday use, but recordings can opt into one (`--drone`, or the toggle in `claudio web`). It lays a low, A-rooted drone under the clip and **fades it in and out**, so the take feels like one cohesive piece rather than scattered sounds. Off by default — it's there when you want body, gone when you don't.

Prefer buttons? Hit **● Rec** in `claudio web` — pick a length, optionally flip on the drone bed, go work in your sessions, and grab the clip with a built-in player and download link.

**🎹 Jukebox (a little easter egg).** Don't want to wait for Claude to make sounds? *Perform* a whole MIDI file through Claudio's voices. Pick the **sound kit** in the header — any of the 40 presets, independent of the room you're working in. Four are purpose-built song kits with real drums, bass and melodic voices: **`studio`** (clean drums · bass · synth), **`dnb`** (breakbeats, sub + reese bass, stabs & pad), **`synthwave`** (gated-snare 80s with saw bass, lead, arp & poly pad), and **`lofi`** (dusty kit, upright bass, Rhodes-y keys & a hazy pad). Each track shows its register, note range, and a density bar, then maps to a sound however you like: to an **event** (with live fire counts, so the melody can ride whatever your sessions use most), to **any voice directly**, or **⊞ any sound from any preset**. Preview a row with ▶, or hit **✨ smart arrange** and Claudio matches drums to percussive sounds and melodies to voices in the right register. Pitch always comes from the MIDI — pitched voices land exactly on every note. The Sounds tab and constellation bloom in time as it plays; start a recording first and you've captured a whole song in your palette; and when a mix sounds right, **💾 save as preset** turns it into a self-contained room you can use anywhere. Open it with the **`.`** after *Claudio* (or the Music-tab **🎹 Jukebox** button), drop in any `.mid`, and press play. CLI: `claudio play <song>` (`claudio song import <file.mid>` to add one).

**🎬 Session mini-tracks — replay your workflow.** Every Claude session is quietly captured as a tiny **symbolic timeline** (a few KB of JSON — just *what happened, when*, no audio). In `claudio web`, each session in the left rail gets a **heavy-traffic sparkline** (see the dense, bursty stretches at a glance) and a **▶ replay** button. Replay re-runs your actual workflow as music through *any* preset — so you can audition the same session across presets and tune until it sounds great. Idle gaps are compressed so the busy parts stay punchy. Then **● render WAV** bounces it to a shareable clip, or **⤓ score** saves the tiny `.score.json` (far lighter to share than a WAV, and replayable anywhere). From the CLI: `claudio replay list`, `claudio replay <session|latest> [--preset X] [--tempo 1] [--loop] [--render]`.

> **Share it! 🎧** Post your clip with the preset name so others can hear how their sessions could sound. The more sounds people share, the richer Claudio gets — and if you tune a combination you love, [open a PR with the preset](#-make-your-own-preset) too.

---

## 📦 Install

### Easiest: as a Claude Code plugin (two lines)

Paste these into Claude Code:

```
/plugin marketplace add allaspectsdev/claudio-symphony
/plugin install claudio-symphony
```

The hooks wire themselves and the `claudio` command is on your PATH. Then install the synthesis dependency and render the sound library explicitly:

```bash
python3 -m pip install numpy
claudio setup
```

Claudio's hooks never modify Python or install anything silently. If numpy is missing, a setup note is written to Claudio's platform log directory and `claudio doctor` prints the exact fix.

> Prefer to drive it by hand, or not using plugins? Use the manual install below — just don't do both (you'd get double sounds).

### Manual

```bash
git clone https://github.com/allaspectsdev/claudio-symphony.git
cd claudio-symphony
python3 -m pip install -r requirements.txt
./bin/claudio setup           # verify + migrate legacy data + render samples
./bin/claudio install         # adds hooks to ~/.claude/settings.json
```

Open a new Claude Code session and listen. That's it.

> **👉 There's a full UI.** Run **`claudio web`** to open the browser control panel — a live constellation of your voices where you can tune everything, browse and switch all 40 presets, build your own, and record clips. No build step, runs locally on `127.0.0.1`. See [The web control panel](#️-the-web-control-panel).

**Requirements**
- 🖥️ **macOS, Linux, or Windows.** Claudio auto-detects the best audio player on your system (override with `CLAUDIO_PLAYER`):
  - 🍎 **macOS** — built-in `afplay`. Nothing to install; full quality.
  - 🐧 **Linux** — `ffplay` (from `ffmpeg`) for full quality; falls back to `mpv` / `sox` / `pw-play` / `paplay` / `aplay`. `sudo apt install ffmpeg` (or your distro's equivalent) recommended.
  - 🪟 **Windows** — `ffplay` (`winget install -e --id Gyan.FFmpeg`) for full quality; falls back to PowerShell MediaPlayer (volume only) then `winsound` (basic blips).
- 🐍 Python 3.9+ with **numpy** — still the only Python dependency. (Players are auto-detected, never auto-installed.)
- 💾 ~250 MB free for generated samples (one-time render, then static)

Song-mode pitch micro-tuning is native on afplay/ffplay/mpv/sox; on volume-only backends (`pw-play`/`paplay`/Windows MediaPlayer) it's reproduced by an offline numpy pre-render in Claudio's platform cache, so it still works everywhere. The requirements file installs `windows-curses` only on Windows; `claudio web` remains available everywhere.

All mutable data lives outside the checkout in the platform-standard config, data, state, cache, and log directories. Set `CLAUDIO_HOME=/path` for a portable installation, or run `claudio migrate` to copy data from an older checkout-local installation without deleting the originals.

Tip: add `alias claudio='~/path/to/claudio-symphony/bin/claudio'` to your shell profile (macOS/Linux). On Windows, run via `bin\claudio.cmd`.

---

## 🎛️ Use it

```bash
claudio status                          # what's installed and active
claudio preset list                     # see all 40 presets
claudio preset use cathedral            # switch live (no Claude restart)
claudio preset diff cathedral           # inspect edits from the shipped baseline
claudio preset undo cathedral           # undo the most recent preset edit
claudio preset export cathedral room.json
claudio preset import room.json my-room
claudio off / claudio on                # silence everything / restore
claudio web                             # the browser control panel
claudio tune                            # interactive terminal tuner (TUI)
claudio audition                        # hear every preset, then pick one
claudio test                            # walk every voice in the active preset
claudio volume 0.4                      # master gain
claudio coffee                          # ☕ support the project (see below)
```

### `claudio tune` — the interactive tuner

```
─────────────── claudio tune ─────────────────────────────────
 preset: meadow   master: ▰▰▰▰▰▱▱▱▱▱ 0.55              ✓ saved
─ Voices — [gain]  press t for mioi ──────────────────────────
 ▶ mallet     gain ▰▰▰▰▰▱▱▱ 0.55  mioi ▰▰▱▱ 0.35s
   kalimba    gain ▰▰▰▰▰▱▱▱ 0.50  mioi ▰▰▱▱ 0.30s
   bloom      gain ▰▰▰▰▰▱▱▱ 0.55  mioi ▰▰▰▰ 10.00s
─ Events ─────────────────────────────────────────────────────
   PreToolUse              → wood
       · Bash              → bird
   PostToolUse             → mallet
       · Edit              → kalimba
       · on_failure        → chime
   Stop                    → bloom
─ TAB pane │ ↑↓ row │ ←→ value │ SPC play │ s save │ q ──────
```

Arrow keys move sliders, SPACE previews, `s` saves, `q` saves + quits. Changes are live — the next event picks them up without restarting Claude.

### Power-user CLI

```bash
claudio voice mallet gain 0.45            # per-voice gain in the active preset
claudio voice mallet mioi 0.5             # rate-limit (min seconds between hits)
claudio map PostToolUse:Edit pluck        # remap by tool
claudio map PostToolUse:on_failure -      # silence the failure variant
claudio scale use A_lydian                # global scale override
claudio root C                            # live-transpose the whole room (root off → back to A)
claudio chords pop                        # cycle the four-chord song (chords Am F C G · every 12 · off)
claudio song use mario                    # drive a voice from a MIDI melody
```

---

## 🎨 Make your own preset

**The easy way — build one in the browser.** Open `claudio web`, hit **✚ Build a preset**, and you get a palette of *every voice from all 40 presets*. Audition any sound with ▶, pick the ones you love, name it, and hit Create — Claudio copies those samples into a new, self-contained preset that works everywhere instantly (start blank, or duplicate an existing preset and add to it). No code, no render step.

- **Swap a single sound** — in the Sounds tab, the **↺** button on any voice lets you replace just that one sound with any voice from any preset, keeping its level, echo, and event mappings.
- **Manage your presets** — custom presets you build get **rename** (✎) and **delete** (🗑) right on their gallery card; the 40 shipped presets are protected and can't be deleted.

**The hands-on way — author it in code.** Each preset is three things:

```
presets/<your-preset>/
├── preset.json    # voice configs + event → voice mapping
├── render.py      # generates the WAV samples
└── samples/       # output (gitignored — generated by render.py)
```

`render.py` imports the shared DSP helpers from the top-level `synth.py` (FFT-convolved reverb, ADSR envelopes, FFT lowpass, A = 432 frequency math) and writes WAVs into `samples/<voice>/`.

There's a full [composer's brief](docs/SONIC_FRAMEWORK.md) covering scale choices, palette design, and the anti-machine-gun strategies (per-voice MIOI, pressure accumulators, voice stealing, reverb-as-glue). **If you build a room you love, open a PR — we'd genuinely love to hear it.**

---

## ⚙️ How it actually works

```
Claude Code event
       │  hook fires (async, timeout 1s — never blocks the agent)
       ▼
event.py  (~50 ms total)
       │  ├─ reads the event JSON from stdin
       │  ├─ resolves the preset:  session pin → cwd rule → global default
       │  ├─ maps event → voice via preset.json
       │  ├─ rate-limits per voice (drops too-soon hits, banks "pressure"
       │  │   that bumps the next note's amplitude)
       │  ├─ picks a pitch melodically (Markov-weighted, stays in scale)
       │  └─ launches the detected player detached (afplay / ffplay / … via `audio.py`)
       ▼
   (your speakers)
```

`event.py` is stateless except for tiny per-voice timestamp files. `drone.py` is the only long-running process, and it auto-exits after 10 minutes of silence. No daemon to babysit, no port to conflict, no config server. Pure Python, one dependency.

---

## 🎼 The composer's notes

Three principles shaped every design choice:

1. **Inverse frequency → prominence.** Rare events get the foreground; common events whisper. The end-of-turn bloom feels loud because it happens once every few minutes; tool-starts get the softest, most disposable voice because they fire 5–30× a minute.
2. **No tempo, no melody, no notification DNA.** With nothing to predict and no memorable hook, the ear settles into landscape mode instead of flinch-mode. The instant something sounds like a notification, your nervous system flags every event as a possible interruption.
3. **The reverb tail is the glue.** A long tail on every voice means dense bursts smear into a wash rather than stack as discrete hits. The same patch handles the calm session and the chaotic one — the wash gets *thicker*, not *louder*.

Read [the full composer's brief](docs/SONIC_FRAMEWORK.md) — it's worth your time even if you never touch the code.

---

## 💛 Why I built this

I wanted my Claude Code sessions to make soothing, pleasant sounds — all in key, all cohesive — so that AI-assisted coding simply felt nicer to sit inside.

Then something happened while I was building it: I started to *rely* on it. I could suddenly hear what was happening across all of my active coding sessions — which one was busy, which had gone quiet, which just finished. What began as a small idea turned into something I genuinely can't use Claude Code without.

Slack pings condition you to flinch. A cathedral does not. A bell tuned to the room you're working in becomes a *fact about the room*, not an interruption. The hope is that the room starts to move with your work — and that you fall for it the way I did. 🌙

---

<a name="support"></a>

## ☕ Support — buy me a coffee

Claudio is free and MIT-licensed, built and maintained in my spare time. If it makes your sessions a little nicer, an on-chain tip means the world and keeps new presets coming. No platform, no cut, no signup — just send to whichever chain you already use:

| Chain | Address | Also accepts | Scan |
|---|---|---|---|
| **Bitcoin** (BTC) | `3Ht6H531DyWjgsxV289cWLYKJG8tVza2P5` | — | <img src="web/qr/btc.svg" width="84" alt="BTC QR"> |
| **Ethereum** (ETH) | `0xB239b34e42b4Bc571158e48a779099950C81C7d8` | USDC (ERC-20) · any EVM token | <img src="web/qr/eth.svg" width="84" alt="ETH QR"> |
| **Solana** (SOL) | `2PiDya4hpbpki7iUceyE1uYBDR3dQgW6uCN27JVJUHwS` | USDC (SPL) | <img src="web/qr/sol.svg" width="84" alt="SOL QR"> |
| **Dogecoin** (DOGE) | `D5HMGHjcRnvdcNY5LGAb1EcMpBm8FD8YHN` | — | <img src="web/qr/doge.svg" width="84" alt="DOGE QR"> |

The Ethereum and Solana addresses receive their **native coin first** (ETH / SOL) and **also** take USDC on that chain — same address, no extra step. Send tokens only on the network listed above so they land somewhere I can reach them. You can also pull these up any time with `claudio coffee`, or via **⋯ → Buy me a coffee** in `claudio web` (with QR + one-tap copy).

> **Verifying these addresses:** all four live in [`donate.json`](donate.json) as the single source of truth, and the app reads the same file. If an address here ever disagrees with `donate.json` or your wallet, treat it as a tampered diff and don't send. (These are public *receiving* addresses — never a private key.)

⭐ Can't tip? **Starring the repo and sharing it** helps just as much.

---

## 🙏 Credits

- The two design briefs in [`docs/`](docs/) — `SONIC_FRAMEWORK.md` and `TRIGGER_SURFACE.md` — were drafted as the spec for this project, and are worth reading on their own.
- DSP synthesis: pure numpy. Synthetic-IR FFT convolution for the reverb. No scipy, no external audio libraries.
- Inspired by Brian Eno (*Music for Airports*), Harold Budd (*The Pearl*), Stars of the Lid, Nils Frahm (*Felt*), William Basinski, Susumu Yokota.
- Tuning: A = 432 Hz throughout. Drone fundamentals are strictly just-intoned (3:2 root-to-fifth); upper voices are equal-tempered.

---

## 📄 License

MIT. Do whatever you want with it. If you build a preset you love, we'd love to see it. 💫

---

```
   tune the drone first
   get the reverb right
   add the pluck
   everything else is decoration on those three foundations
```
