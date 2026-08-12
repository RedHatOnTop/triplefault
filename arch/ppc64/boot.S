.section .text
.global _start
_start:
    /* ELFv2: r2 must point at the TOC before any C code runs. */
    lis   2, .TOC.@highest
    ori   2, 2, .TOC.@higher
    sldi  2, 2, 32
    oris  2, 2, .TOC.@h
    ori   2, 2, .TOC.@l

    lis   1, stack_top@highest
    ori   1, 1, stack_top@higher
    sldi  1, 1, 32
    oris  1, 1, stack_top@h
    ori   1, 1, stack_top@l
    li    0, 0
    std   0, 0(1)
    std   0, 8(1)
    bl    kmain
1:  b 1b

.section .bss
.align 4
stack_bottom:
    .space 32768
stack_top:
