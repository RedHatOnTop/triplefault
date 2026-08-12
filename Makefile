# TripleFault v1 skeleton
CC      ?= gcc
CFLAGS  := -m32 -std=gnu11 -ffreestanding -fno-stack-protector -fno-pic \
           -fno-builtin -O2 -Wall -Wextra -Werror
ASFLAGS := -m32
LDFLAGS := -m elf_i386 -nostdlib -T kernel/linker.ld

OBJS := build/boot.o build/kernel.o

all: build/kernel.elf

build:
	@mkdir -p build

build/%.o: kernel/%.S | build
	$(CC) $(ASFLAGS) -c $< -o $@

build/%.o: kernel/%.c | build
	$(CC) $(CFLAGS) -c $< -o $@

build/kernel.elf: $(OBJS)
	ld $(LDFLAGS) -o $@ $(OBJS)
	@grep -q . /dev/null; echo "built: $@"

run: build/kernel.elf
	python3 harness/run.py --once

score: build/kernel.elf
	python3 harness/score.py

clean:
	rm -rf build

.PHONY: all run score clean
