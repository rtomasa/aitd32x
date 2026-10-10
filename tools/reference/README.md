# Headless FITD core oracle

Pinned upstream: yaz0r/FITD `543e22bc78b64405537ae545ecd382dcdf2c12b2`.

This harness compiles the actual LIFE, animation, collision, track and room code. The patch renames presentation/audio entry points; `oracle.cpp` substitutes input, timer, menus, drawing, text and sound with deterministic stubs. `BufferAnim` is initialized as in OpenProgram. Graphics dependencies are not required. This is a gameplay-core oracle, not a complete graphical desktop validation. It logs the original item offer rather than opening/accepting the PC pickup UI.

Build using a checkout or extracted archive of that exact commit (the helper verifies source SHA-256 hashes) and GCC with C++20 `<format>` support:

```sh
python3 tools/reference/build_reference.py /path/to/FITD /path/to/reference-build
/path/to/reference-build/build/fitd-headless /path/to/INDARK 500 0 stairs
```

Arguments after game data: number of 25 Hz ticks, character (0 Edward / 1 Emily), scenario (`stairs`, `chest`, `push`, `book`, `zombie`, `melee`, `throw`, or empty idle). JSON lines contain original variables, active actors and object records. Audio/messages/books/offers are diagnostic stderr output. The harness uses the game's original object and resource files read-only.

Source differences observed in this milestone are recorded in `docs/VALIDATION.md`. In particular, it does not establish identical collision displacement, fight pacing, visual/UI behavior, or full-house parity. The reverse-tested console walk/run timing remains the approved 60 Hz fractional animation clock.
