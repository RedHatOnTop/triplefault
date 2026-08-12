/* TripleFault v1 skeleton: Multiboot1 entry stub (i386).
 *
 * This file is part of the PROVIDED SKELETON. You may modify it.
 * It exists so that agents do not burn their entire budget on toolchain
 * setup. Everything above Milestone 10 is your problem.
 */

.set MB_MAGIC,    0x1BADB002
.set MB_FLAGS,    0x00000003          /* align modules + provide meminfo */
.set MB_CHECKSUM, -(MB_MAGIC + MB_FLAGS)

.section .multiboot, "a"
.align 4
    .long MB_MAGIC
    .long MB_FLAGS
    .long MB_CHECKSUM

.section .bss, "aw", @nobits
.align 16
stack_bottom:
    .skip 16384                       /* 16 KiB boot stack */
stack_top:

.section .text
.global _start
.type _start, @function
_start:
    cli
    movl $stack_top, %esp
    xorl %ebp, %ebp

    /* Multiboot leaves the info struct pointer in %ebx and 0x2BADB002 in %eax.
       Pass both to kmain(magic, mbi). */
    pushl %ebx
    pushl %eax
    call  kmain
    addl  $8, %esp

.hang:
    cli
    hlt
    jmp .hang
.size _start, . - _start

.section .note.GNU-stack, "", @progbits
