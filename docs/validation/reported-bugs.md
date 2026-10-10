# Reported opening, occlusion and saber faults

Working-tree fixes after `v15-baseline`; no new release tag or commit.

The original furniture opening/offer/automatic-closing scripts are retained.
The user confirmed that automatic closing also occurs in MS-DOS. No LIFE or
asset patches are applied.

## Changes

- Stationary models snap to the original animation key when starting an
  opening, avoiding interpolation from unrelated bind geometry. One-shot
  animations retain their final pose when stopped or reactivated. LIFE and
  combat still observe the original frame-zero wrap at completion.
- Clear the frame-completion pulse each simulation tick, including stationary
  actors, so an old completion cannot retrigger ANIM_SAMPLE indefinitely.
- Keep a found-item script's world identity across actor-pool refreshes.
  Breaking the OLD CAVALRY SABER (object 38, LIFE 49) drops its blade and releases
  the temporary caller slot; the subsequent weight update previously faulted
  with LIFE -1, word 25. This is distinct from the SWORD item.
- Sort disjoint actor bounds using camera depth before the horizontal-distance
  fallback. This places the far hallway door behind the character.
- Resolve nearby character/prop intersections in standing and other poses, as
  well as Search/Push. Moving doors and hatches are eligible. Apply each actor's
  architectural masks before it contributes per-pixel depth, preserving nearer
  characters. Retain the 768-vertex limit and painter fallback.
- Coalesce duplicate one-shot requests for the key unlock effect (3) and door
  creak (4) while a voice is already playing that effect. Accept it again after
  completion or STOP_SAMPLE. Other effects and explicit repeat/chaining commands
  retain their existing behaviour. Two interactions requesting the same guarded
  effect during its playback now share that playback.

## Focused verification

```sh
make -j2 host all build/check_animation
python3 tools/check_reported_bugs.py
./build/check_animation
```

The host check uses original assets and both characters. It covers saber
breakage, opening key poses, stopped-pose save/load with in-memory SRAM, the
attic chest's original automatic closing and single effect-37 request, hallway
door ordering, and hatch/player depth at opening angles 400 and 700. Cached
frames agree with fresh cache rebuilds. The animation check preserves the
approved 60 Hz animation/25 Hz simulation, root totals and regional catch-up.

Transient SH2 RAM diagnostics in the local PicoDrive libretro core
(`PicoDrive 2.04aitd32x`) also checked Edward's hallway camera 2 and attic camera
3, with identical scene pixels in both physical framebuffer banks in NTSC and
PAL. The five-second hallway sample advanced 125/126 world ticks and completed
17.2/16.8 draws per second respectively. These are focused emulator observations,
not full-game or physical 32X validation.

## Key/chest audio reproduction

The user confirmed the other gameplay fixes and the effect-4 door fix on
PicoDrive libretro/RePlayOS on Raspberry Pi. They then identified the remaining
chest trigger: use the key, open the chest while it remains selected, then
reselect Search to make the repetition disappear.

This sequence reproduces with the original room-2 chest (object 36, LIFE 45)
and key (object 37, found LIFE 50). At position `(1800, 0, 1400)`, beta 256,
LIFE 45 word 27 requests effect 3 every tick while the key is selected and the
player is searching, before its END_ANIM check. A two-tick tap produces three
requests before the idle animation takes over; a completed search produces 25.
The next opening still produces 25 because the key remains selected. Reselecting
Search runs found LIFE 561, selects the Actions object (2), and produces zero
unlock requests. The chest opening effect (37) is requested once in each full
interaction. Earlier room-3 chest fixtures exercised a different chest/script
and missed this key-dependent path.

`check_key_chest.py` verifies that original-script sequence for Edward and
Emily, including taking the offered saber and the original automatic closing.
The fix is in the native mixer: repeated one-shot requests share the active
unlock voice rather than repeatedly replacing it. Key selection, original
scripts and animations stay intact.

`check_creak_native.py` injects requests into transient emulator RAM and checks
the actual slave/PWM voice state. Effect 3 remains monotonic through 60/50
duplicate requests in NTSC/PAL and completes all 15,241 samples; effect 4 remains
monotonic through 120/100 requests and completes all 21,803 samples. Both can
play again afterward. STOP_SAMPLE, other effect overlap, and explicit repeat
and chaining commands pass. The pre-guard mixer previously reset a voice on
19 of 20 effect-4 burst frames. These are local emulator checks; the expanded
effect-3 fix still awaits confirmation on the user's Pi and is not physical
32X hardware validation.

```sh
make -j2 host all
python3 tools/check_key_chest.py
python3 tools/check_creak_native.py .local/tools/picodrive_libretro.so --region NTSC
python3 tools/check_creak_native.py .local/tools/picodrive_libretro.so --region PAL
```

Reports are in the ignored `build/key-chest.json` and
`build/creak-native-{ntsc,pal}.json`.

No frontend battery files, original data or preserved baseline were modified.
Save schema, serialized layouts and asset fingerprint remain unchanged.

## Build and memory

The ROM remains 4,128,768 bytes; SHA-256:
`d010ddede10c54f1eb507d0acd76b73e38f6d76320572ddd207c6e2d696892d6`.
The original asset bank hash remains
`b1a17763e20dd481337d4495c0ee32147b08a9e474c3a4e2c122164079f97dfa`.
BSS remains 160,120 bytes. The startup module is 85,060 bytes and static SDRAM
ends at `0x0603BDC0`, leaving 576 bytes below the existing stack reservation.
The audio guards add 160 bytes to the module and no global RAM allocation;
including effect 3 adds 16 bytes over the previous effect-4-only guard.
The pose-snap helper executes from ROM. Added temporary workspaces are a
512-byte mask bitmap in the depth pass and 192 bytes of camera-depth ranges in
the draw-list sort; there is no new global buffer or full-screen depth buffer.
Linking retains the existing RWX LOAD-segment warning.
