# Alpha.3 hardware audio and save investigation — 2026-10-19

Follow-up: the [SRAM fix](sram.md) implements the save correction. The text
below records the preceding investigation; audio remains unchanged.

Source revision: `4078eb4`. ROM SHA-256:
`691dfce0283d2b9e48a2e20fb533b3b5650f1f96dccd5f5e3aa26f89197854d1`.
This investigation leaves production code, release bundles, assets and battery
saves unchanged. All experiments use private emulator memory.
The working checkout is the newer rendering revision `8392965`. The final
checks instead use an isolated `4078eb4` source rebuild whose ROM matches the
published alpha.3 SHA-256 byte for byte. The audio and save transport sources
are also unchanged between those two revisions.

## Report and confidence

[Issue #1](https://github.com/rtomasa/aitd32x/issues/1) reports alpha.3 booting
on a physical 32X and Mega EverDrive Pro, firmware `26.0925`. Its screenshots
show `SSF+32X (5)` and `SRAM 128K`, and an in-game **Save failed** notice.
The tone starts with the first logo thunder and continues afterward. The user
subsequently confirmed **Save failed** on MiSTer as well, with sharper/pitched-up
effects but no persistent idle tone. That timbre/rate difference is a separate
observation whose exact cause has not yet been established.

The PWM configuration is a strong explanation for the tone: its carrier is
audible and remains enabled in idle. The exact sound from the reported console
has not been recorded or measured here. For saves, the tests identify a
documented SRAM-layout mismatch and a separate MiSTer width/capacity mismatch.
They do not yet prove which failure is occurring on that EverDrive firmware.

## Audio: an approximately 8 kHz carrier remains enabled

`Audio_SlavePoll` configures cycles 2877 (NTSC) or 2851 (PAL). At sample end,
`Audio_PWMInterrupt` masks the slave interrupt but writes control `0x0005`,
leaving both PWM output channels enabled at midpoint duty. The comment about
centered output describes the decoded PCM level; it does not stop the physical
pulse train.

[Sega's hardware manual](https://consolemods.org/wiki/images/e/e9/32X_Hardware_Manual_1994_Sega_text.pdf),
printed pages 24–25 and 57, specifies the clock/cycle relationship, the retained
pulse width when FIFO empties, and that disabling both channels stops the cycle
counter. Calculating clock/(cycle−1) gives about 8 kHz for our settings. A
midpoint pulse train still has an audible carrier for the console's analog
filter to suppress; silence in a decoded PCM stream is insufficient evidence.

Native stock-PicoDrive register traces of the unchanged ROM show:

| Region | First thunder | After thunder | Cycle |
| --- | --- | --- | ---: |
| NTSC | 3.683 s: control `0x0305` | 7.533 s: control `0x0005` | 2877 |
| PAL | 3.700 s: control `0x0305` | 7.540 s: control `0x0005` | 2851 |

These traces confirm the register configuration and its lifetime, not analog
noise amplitude. No 8 kHz carrier appears merely by decoding the constant
midpoint to digital audio.

The likely correction is to decouple 8 kHz ADPCM decoding from the output
carrier. A three-times output rate near 24 kHz matches the three-entry FIFO:
decode one source sample and enqueue it three times per interrupt. This needs
no reimported samples or full audio buffer. It raises interrupt frequency, so
slave rendering and audio timing must be measured before adopting it. Merely
changing the cycle register would speed effects up. Disabling idle output is
a useful isolated hardware diagnostic, but does not remove an audible carrier
while effects play and can introduce a transition click.

## Saves: failure is before SD export

`Game_Save` writes a record and immediately calls `Inspect` to verify its magic,
format, fingerprint and checksum. An in-game **Save failed** therefore cannot
be explained solely by forgetting to return to the EverDrive menu to export
SRAM to SD. The failure is already in serialization or its write/readback path.
The same ROM saves successfully with the current word-wide SRAM model.

### Extended SRAM address assumption

`SaveWord` selects page 31 in bank 4 and accesses `0x200000 + save_cursor`,
the start of that 512 KiB page. The
[manufacturer's extended-SSF specification](https://krikzz.com/pub/support/mega-everdrive/x3x5x7/dev/extended_ssf-v2.txt)
instead places battery SRAM in page 31's **upper 256 KiB**. With bank 4 selected,
that starts at `0x240000`.
The pinned [Doom 32X Resurrection reference](https://github.com/viciious/d32xr/blob/55bf94b43a039ae0a0d2f09ad9bc23bea5963714/src-md/crt0.s)
also uses the upper half for that mapper family, with odd-byte accesses.

Native 68000 execution against a private bus model of the documented layout
reproduces **Save failed**: all 10,629 word writes miss the battery window.
Changing only the access base to `0x240000` in private emulator RAM makes the
same record pass immediate verification. No ROM or battery file is patched.

This is a concrete compatibility defect against the documented layout, but
not yet a proven explanation for the reported Pro. The published
[Pro SSF implementation](https://github.com/krikzz/mega-ed-pub/blob/23dbd5ef527999eb85590ece7ad0ba6e202c8a4c/fpga/mapper/map_ssf/map_ssf.sv)
routes the whole page to BRAM. Its
[physical bus wiring](https://github.com/krikzz/mega-ed-pub/blob/23dbd5ef527999eb85590ece7ad0ba6e202c8a4c/fpga/fpga_pro/top.sv)
exposes both byte lanes. A model of that path passes with the existing address.
The shipped firmware/FPGA behavior and SRAM import layout must be checked on
the cartridge rather than inferred from the older specification alone.

### Detection remains an untested hardware variable

The existing `check_ssf_sram_native.py` forces `extended_mapper=1` after boot.
It tests the compiled save transport against its own assumed bus layout, but
does not test the bank-0 remapping probe. Thus its passing result cannot rule
out a false-negative probe selecting conventional SRAM on the real cartridge.
The current probe matches the reference technique in principle. There is no
measurement of its actual result on the reported EverDrive yet.

The test also expects the same lower-page address as the implementation;
therefore it cannot detect the upper-half mismatch above. Both detection and
the independently specified SRAM window belong in follow-up validation.

## MiSTer: a different save limitation, and digital PWM output

The inspected S32X source revision is
`3d4209c659512a8c0f43913b1fa54d3d550b2794`; this is source inspection, not a
claim of testing the user's installed FPGA bitstream.

Its [cartridge decoder](https://github.com/MiSTer-devel/S32X_MiSTer/blob/3d4209c659512a8c0f43913b1fa54d3d550b2794/rtl/CART/cart.sv)
does not implement extended bank-0 mapping. Conventional SRAM has a 15-bit
address, an 8-bit data port, stores the low byte and returns `0xFF` in the high
byte of word reads. Our fallback assumes 128 KiB of word-wide SRAM. That is
incompatible both in byte lanes and capacity. Switching only to odd-byte
access would not make the current two 64 KiB journals fit its 32 KiB store.

A private bus model of that decoder, running the unchanged native conventional
save path, reproduces **Save failed**. The expected `41 49 54 44` magic loses
its high bytes. This predicts a MiSTer save failure independently of the
EverDrive diagnosis; a matching outcome would not establish a shared cause.

MiSTer's [32X interface](https://github.com/MiSTer-devel/S32X_MiSTer/blob/3d4209c659512a8c0f43913b1fa54d3d550b2794/rtl/32X/IF.sv)
converts pulse-width values to digital PCM. It does not send the game's
8 kHz carrier through a physical 32X analog output stage. Consequently, a
clean-sounding MiSTer result cannot clear the console carrier-noise issue.
The reported absence of a persistent MiSTer tone is consistent with this
distinction. Pitched-up effects still need a duration comparison: the imported
logo thunder contains 30,801 samples at 8 kHz (3.850125 seconds), and its native
PicoDrive playback agrees with that duration. The user subsequently confirmed
correct effect duration on MiSTer, with only occasional sharper sound. This
argues against a systematic playback-rate/pitch error. A filtering or
reconstruction difference is the leading explanation for that observation,
but a recording or controlled comparison is needed to establish it.

The core's
[audio mixer](https://github.com/MiSTer-devel/S32X_MiSTer/blob/3d4209c659512a8c0f43913b1fa54d3d550b2794/rtl/GEN/gen.sv)
mixes PWM into the signal before the selectable output low-pass filter.
`Audio & Video → Audio Filter → Model 1` is therefore a relevant diagnostic
comparison against Minimal/No Filter; the separate HiFi PCM option affects
the FM component. These settings do not change our 8 kHz source rate or fix
the cartridge save path. A FIFO artifact is not excluded: our interrupt
currently submits three decoded samples without consulting FIFO space.

## Focused results and next evidence

| Private model, native alpha.3 code | Result |
| --- | --- |
| Existing full-page, word-wide Pro model | Save verified |
| Manufacturer-documented upper-half window | Save failed |
| Same upper-half model, RAM-only access-base correction | Save verified |
| Published MiSTer conventional SRAM width/capacity | Save failed |

These are attribution experiments, not validations of a physical cartridge,
SD export, analog audio, or a complete MiSTer core simulation. The extended
models deliberately select the extended path; none proves probe correctness.

To resolve the remaining EverDrive uncertainty, a diagnostic should report
the selected save backend and compare the documented upper-half access on
that cartridge. Imported saves additionally need their byte-lane/file layout
checked. Audio confirmation should compare idle output off or a higher-carrier
candidate on the same physical console. Preserve existing saves; use ordinary
in-game saves rather than synthetic hardware fixtures.

Reports, scripts, screenshots and pinned source copies are under ignored
`build/hardware-issue-1/`: `audio-register-trace.json`, `inspect_audio.py`,
`check_save_models.py` and `save-model-*.json`. All four save-model checks and
the NTSC/PAL audio traces completed successfully with their expected outcomes.
Those initial outputs describe the current checkout. The final release-specific
results are `alpha3-audio-register-trace.json`, `alpha3-save-model-*.json` and
their prefixed logs. `alpha3-reference/` retains the matching source/build;
the `alpha3-*.py` helpers run from that directory.
No production fix, commit, release replacement or GitHub comment was made.
