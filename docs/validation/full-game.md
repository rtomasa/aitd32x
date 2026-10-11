# Full-game implementation and validation

The original AITD1 progression is enabled across all eight floors. The importer
includes 58 room resources and 144 original camera views; auxiliary rooms 3:6
and 4:1 have no original camera. Original LIFE/track resources drive the later
rooms, underground areas, Pregzt ritual and escape. The destruction movie uses
all 32 original ENDSEQ frames. Full manual playthrough of both characters and
physical 32X validation remain pending.

## Performance and memory decisions

Gameplay remains at 25 Hz with the independent approved 60 Hz animation clock.
Both SH2 processors keep their rendering work and the slave's autonomous PWM
audio. The 68000 retains controller, music, SRAM and mapper services from RAM;
the existing Z80 bus arrangement is unchanged.

All fixed resources avoid the 512 KiB mapper aperture. Camera pages can stay
selected between draws, with a supervisor exchange only when the page changes.
This applies to gameplay, startup, death and the ending. Legacy banks still
restore their identity mapping. All camera images remain raw and page-isolated;
no per-transition decompression or additional background buffer is introduced.

The original 50-actor pool uses compact signed-word bone channels, with the
actual imported maximum of 28 groups. Static/contact masks cover all 50 slots;
contact bookkeeping also handles 50 entries while retaining the existing
768-vertex bound. The duplicate ordinary stationary collision scan is removed.
Early-world state comparisons retain the baseline's behaviour.

The quiet-timer pose/mask cache also applies throughout the game to animated
props with no animation asset or no deformable child groups. Group zero is
replaced by actor angles during vertex generation. Position/angle/mask changes
still invalidate the bake; movable props and deforming skeletons stay dynamic.

Prepared prop programs extend across eligible poses on every floor. The fixed
ROM budget retains all 216 previous entries and expands to 1106 entries sharing
671 programs, using 759742 bytes. Poses beyond the budget, moving poses and
skeletal bodies use the normal renderer.

The movie applies precompiled changed spans to the retained background and
tracks pending repairs for both framebuffers. Dark-room lighting projects the
current lantern source once and restores the union of its old/new footprints
before drawing. Moving, appearing and disappearing lights preserve partial
repairs; no full-screen restore is needed for every ordinary lamp movement.

## Build

Built on 2026-10-11 with the preserved Marsdev GCC 13.1.0 toolchains:

```sh
make assets
make -j2 all host
python3 tools/check_bank_layout.py --output build/full-game-layout.json
```

| Resource | Complete-game build |
|---|---:|
| Padded ROM | 14155776 bytes / 13.5 MiB |
| Asset IDs | 2316 |
| Fixed bank | 3964872 bytes |
| Extra bank | 9932868 bytes |
| BIOS-loaded module | 84260 bytes |
| BSS | 160640 bytes |
| Static SDRAM, including linker overhead | 244904 bytes |
| SDRAM end | `0x0603BCA8` |
| Margin below reserved stacks | 856 bytes |
| BIOS module end in physical ROM | 4180204 bytes |
| Margin below direct 4 MiB ROM window | 14100 bytes |

ROM SHA-256:
`b159cc9aba57c0f8a53b5f77969b2e052d86f3528976530d5f5ba5808c7410b9`.
Checksum: `6C7F`. Bank SHA-256:
`d9ee34b9b1dd1b4ea6d52854fb1a99ebd95b6c48e39006ff6e82b1e9d6762c55`.

BSS grows by 464 bytes from the pre-full-game build. No image/depth buffer or
heap is added. The remaining RAM margin is small: future additions must measure
the linked result and reuse storage. Native assembler branch-extension and
freestanding RWX linker warnings remain; the layout check passes. This ROM
requires a compatible SSF2 mapper and sufficient cartridge storage. It does
not establish compatibility with the previously reported cheap flash cart.

## Focused evidence

Checks use the local original CD assets and pinned FITD reference. Generated
reports/captures remain under ignored `build/`; test SRAM is private memory.
No user battery save or preserved baseline release is modified.

| Check | Result and scope |
|---|---|
| `check_full_game_world.py --reference build/full-game-reference` | All 556 character/room/view activation cases; peak 36/50 actors; both original floor-1 staircase sequences reach floor 2. Ten baseline scenarios compare 1600 updates, all object/variable fields, live bone state and exact geometry pixels above information rows. A 50-entry contact fixture passes. |
| `check_full_game_scripts.py` | All 563 LIFE scripts: 11346 commands, 3753 branch targets and 6256 expressions validated. Both characters execute original corridor/library lighting, lantern, altar-book and final ritual/escape script fixtures. |
| `check_startup.py --world-only` | Both complete original arrivals finish without a script fault: Edward 3252 and Emily 3219 world ticks. |
| `check_full_game_save.py` | Eight preceding-format saves migrate with every serialized gameplay field preserved. New-format roundtrips and four held/dropped-lantern darkness saves pass; the old journal remains intact on the first migration write. |
| `check_save_capacity` | 50 slots, each with the largest 28-group skeleton: 53930-byte payload within 65512 bytes, exact roundtrip. |
| `check_ending.py` | Both characters, all 32 original images/palette and 142 framebuffer comparisons; paused world, natural completion, all skip buttons, preserved escape state, bright post-Pregzt escape and timed final title return. |
| `check_ending_native.py .local/tools/picodrive_libretro.so` | Final NTSC/PAL ROM: all 32 displayed original frames, 16 comparisons per physical bank, selected RGB captures, safe retained page 26, frozen objects/variables/inventory/world ticks, unchanged private SRAM and bright escape recovery. |
| `check_lighting.py` | 38 cached/full-reference comparisons: held/dropped/deactivated lamps, movement, missing/reappearing sources and changed camera; full illumination repairs both banks. |
| `check_death.py` | Both original player/enemy death script sequences, cemetery views, final picture/hold, skip/title return and private saved-game preservation pass after the GAME_OVER changes. |
| `check_bank_layout.py` | Linked bytes, checksum/header, all protected fixed resources, all 181 banked payloads and delta commands, one-page isolation, module/direct-ROM and SDRAM limits pass. |

The ritual fixtures supply required items and prerequisites to exercise the
actual original scripts. Room fixtures place the player directly. These checks
do not substitute for finding every item, solving every puzzle and completing
combat/escape naturally in a manual playthrough.

## Native emulator performance

`check_full_game_native.py .local/tools/picodrive_libretro.so --reference
build/full-game-reference` passes in NTSC and PAL. It uses fresh core processes
to isolate controller/core state and loads private host SRAM through the actual
title-menu B action. All eight floor fixtures restore the expected initial
pose/room/camera. Both physical framebuffer banks agree; uncovered cached
background pixels match original camera bytes and retained mapper pages remain
valid. Each fixture then runs a second of native LIFE without a fault/fatal.
Floor 5's heavy fixture also exercises actor slots above 31; floor 6 exercises
the lamp mask.

| Ten-second attic trace | Previous build | Complete-game build |
|---|---:|---:|
| NTSC completed draws / FPS | 243 / 24.3 | 243 / 24.3 |
| PAL completed draws / FPS | 242 / 24.2 | 242 / 24.2 |

All five trace segments match positions, angles, animation assets/frames/phases
and world ticks. The eight sampled startup/character/inventory/action selection
edges match baseline latency in both regions: startup 40–50 ms, character
60–66.7 ms, and inventory/actions 80–116.7 ms.

The one-second live floor-5 room-10/camera-18 sample completes 17 draws in NTSC
and 20 in PAL; the underground floor-6 room-0/camera-2 lamp sample completes
19 and 24. These short fixtures expose remaining complex-scene cost, rather
than establishing sustained gameplay or hardware rates. Full new-room bakes,
many animated actors and contact work remain possible frame-rate limits.
Reports are `build/full-game-native-NTSC.json` and
`build/full-game-native-PAL.json`.

Natural native destruction playback takes 2.70 seconds in each region, showing
32 image frames at approximately 11.85 FPS against the 12 FPS target. First-image
latency is 83.3 ms in NTSC and 80 ms in PAL. Reports and captures are under
`build/ending-native/`. This verifies linked type-19 delta mapping and output;
it does not establish exact DOS movie timing or physical cartridge behaviour.

The floor-3 entrance fixture runs two genuinely rotating doors and a one-shot
ghost animation. Its five successive one-second samples are 9, 10, 8, 14, 24
draws in NTSC and 11, 9, 8, 15, 26 in PAL. The preceding intermediate build's
NTSC samples were 9, 9, 9, 12, 26; these short samples do not demonstrate a
speed gain. The cache generalization preserves rendering and extends reuse to
equivalent props throughout the game. After the scripted motion and quiet
timer finish, the fixture recovers to 24–26 FPS. The offscreen ghost still pays
for vertex transforms/face sorting during animation; conservative actor
viewport rejection before sorting is a future performance target, requiring
near-plane and point/sphere coverage checks. Reports are
`build/full-game-floor3-{NTSC,PAL}.json`.

## Save compatibility and remaining limits

Existing 2053 asset IDs and fingerprint `0x0eebc721` are retained. New writes use
`0x53313601` with 50 slots, 16-bit bone channels and darkness. Loading accepts
the preceding `0x53313401` format with 24 slots and 32-bit channels. Older ROMs
cannot read the new format; retain battery backups before upgrading.

Lamp shape/centering is a console adaptation, not independently verified DOS
pixel parity. Ending playback uses five 60 Hz ticks per frame; exact original
timing still needs comparison. The inherited FITD cosmetic RND_FREQ/SHAKING/
WATER stubs remain. GET_HARD_CLIP has no applicable type-5 primitive in these
resources. CD narration remains unimplemented and music timbre approximates
AdLib on YM2612/PSG. Emulator tests establish neither physical mapper/RV/SRAM
behaviour nor hardware FPS.
