.section .text
.global _start
_start:
    larl  %r15, stack_top
    aghi  %r15, -160
    brasl %r14, kmain
1:  j 1b
.section .bss
.align 8
stack_bottom:
    .space 32768
stack_top:

.section .note.GNU-stack, "", @progbits
