# Native 32X build. Both CPUs are freestanding; no SDL, libc, heap or OS.
-include local.mk
MARSDEV ?= $(HOME)/mars
GAME_DATA ?= $(CURDIR)/msdos-game/AITD_CD/INDARK
MDCC := $(MARSDEV)/m68k-elf/bin/m68k-elf-gcc
MDOBCOPY := $(MARSDEV)/m68k-elf/bin/m68k-elf-objcopy
SHCC := $(MARSDEV)/sh-elf/bin/sh-elf-gcc
SHCXX := $(MARSDEV)/sh-elf/bin/sh-elf-g++
SHAS := $(MARSDEV)/sh-elf/bin/sh-elf-as
SHOBCOPY := $(MARSDEV)/sh-elf/bin/sh-elf-objcopy
SHSIZE := $(MARSDEV)/sh-elf/bin/sh-elf-size
BUILD ?= RELEASE
OPT := -O2
ifeq ($(BUILD),DEBUG)
OPT := -Og -g -DDEBUG
endif
ifeq ($(BUILD),PROFILE)
OPT := -O2 -g -DPROFILE
endif
SHFLAGS := -m2 -mb -std=c++17 -ffreestanding -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-unwind-tables -fno-asynchronous-unwind-tables -fno-builtin -Wall -Wextra $(OPT) -MMD -MP
CORE := src/render/book.cpp src/platform/audio.cpp src/engine/save.cpp src/engine/startup.cpp src/platform/save_bridge.cpp src/engine/math.cpp src/engine/trig.cpp src/engine/actor.cpp src/engine/collision.cpp src/engine/game.cpp src/engine/world.cpp src/engine/life.cpp src/platform/storage.cpp src/render/render.cpp src/render/raster.cpp src/render/worker.cpp src/render/font.cpp
SHSRC := $(CORE) src/sh2/master.cpp src/sh2/slave.cpp src/sh2/memory.cpp src/sh2/profile.cpp
SHOBJ := $(patsubst %.cpp,build/%.o,$(SHSRC))
.PHONY: all assets clean host check FORCE
all: build/AITD32X.32x
assets:
	@test -n "$(GAME_DATA)" || { echo 'Use make assets GAME_DATA="/path/to/INDARK"'; exit 1; }
	python3 tools/aitdpack/aitdpack.py "$(GAME_DATA)"
build/md_start.o: src/md/start.S src/md/common.h
	@mkdir -p build
	"$(MDCC)" -m68000 -Wa,--register-prefix-optional -Isrc/md -c $< -o $@
build/md_font.o: src/md/font.s
	@mkdir -p build
	"$(MDCC)" -x assembler-with-cpp -m68000 -Wa,--register-prefix-optional -c $< -o $@
build/md_main.o: src/md/main68k.c src/md/common.h
	@mkdir -p build
	"$(MDCC)" -m68000 -mshort -O2 -ffreestanding -fno-builtin -Wall -Wextra -Isrc/md -c $< -o $@
build/md_start.elf: build/md_start.o build/md_font.o build/md_main.o src/md/md.ld
	"$(MDCC)" -m68000 -mshort -nostdlib -T src/md/md.ld -Wl,-Map=build/md.map $(filter %.o,$^) -o $@ -lgcc
build/md_start.bin: build/md_start.elf
	"$(MDOBCOPY)" -O binary $< $@
build/start.o: src/sh2/start.s build/md_start.bin
	"$(SHAS)" --small $< -o $@
build/assets.o: src/sh2/assets.s assets/bank-main.bin assets/bank-extra.bin
	"$(SHAS)" --small $< -o $@
build/sh-flags: FORCE
	@mkdir -p build
	@python3 -c 'from pathlib import Path; import sys; p=Path(sys.argv[1]); s=sys.argv[2]+"\n"; p.write_text(s) if not p.exists() or p.read_text()!=s else None' $@ '$(SHFLAGS)'
build/%.o: %.cpp assets/resource_ids.h build/sh-flags
	@mkdir -p $(dir $@)
	"$(SHCXX)" $(SHFLAGS) -c $< -o $@
build/AITD32X.elf: build/start.o $(SHOBJ) build/assets.o src/sh2/mars.ld
	"$(SHCXX)" -m2 -mb -nostdlib -T src/sh2/mars.ld -Wl,-Map=build/AITD32X.map $(filter %.o,$^) -o $@ -lgcc
	"$(SHSIZE)" $@
build/AITD32X.32x: build/AITD32X.elf tools/finalize_rom.py
	"$(SHOBCOPY)" -O binary $< build/unpadded.bin
	python3 tools/finalize_rom.py build/unpadded.bin $@
host: build/libaitd32x.so
build/libaitd32x.so: $(CORE) tools/host.cpp assets/resource_ids.h
	@mkdir -p build
	c++ -std=c++17 -O2 -fPIC -shared -Wall -Wextra $(CORE) tools/host.cpp -o $@
check: build/check_clock build/check_render build/check_animation
	./build/check_clock
	./build/check_render
	./build/check_animation
build/check_clock: tools/check_clock.cpp src/engine/game.hpp src/platform/32x/frame_stats.hpp
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra $< -o $@
build/check_animation: tools/check_animation.cpp $(CORE) assets/resource_ids.h
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra $(CORE) $< -o $@
build/check_render: tools/check_render.cpp $(CORE) assets/resource_ids.h
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra $(CORE) $< -o $@
# Optional differential raster coverage; compare its report with a reference build.
build/check_raster: tools/check_raster.cpp src/render/render.cpp src/render/raster.cpp src/render/worker.cpp src/render/font.cpp src/engine/math.cpp src/engine/trig.cpp src/render/render_api.hpp
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra -I. tools/check_raster.cpp src/render/render.cpp src/render/raster.cpp src/render/worker.cpp src/render/font.cpp src/engine/math.cpp src/engine/trig.cpp -o $@
build/check_bands: tools/check_bands.cpp src/render/raster.cpp src/render/raster.hpp
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra -I. tools/check_bands.cpp src/render/raster.cpp -o $@
clean:
	rm -rf build
-include $(SHOBJ:.o=.d)
# Focused decoder parity and camera-row indexing after transition optimization.
build/check_decode: tools/check_decode.cpp src/platform/storage.cpp src/platform/platform_api.hpp
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra $< src/platform/storage.cpp -o $@
# Full actor-pool serialization bound, with no test code in the cartridge.
build/check_save_capacity: tools/check_save_capacity.cpp $(CORE) assets/resource_ids.h
	@mkdir -p build
	c++ -std=c++17 -O2 -Wall -Wextra $(CORE) $< -o $@
