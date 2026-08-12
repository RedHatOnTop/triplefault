typedef unsigned long long u64;
typedef unsigned int u32;

#define H_PUT_TERM_CHAR 0x58
#define VTERM 0x71000000ULL

static long hcall(u64 op, u64 a1, u64 a2, u64 a3, u64 a4) {
    register u64 r3 __asm__("r3") = op;
    register u64 r4 __asm__("r4") = a1;
    register u64 r5 __asm__("r5") = a2;
    register u64 r6 __asm__("r6") = a3;
    register u64 r7 __asm__("r7") = a4;
    __asm__ volatile("sc 1"
        : "+r"(r3), "+r"(r4), "+r"(r5), "+r"(r6), "+r"(r7)
        : : "r0","r8","r9","r10","r11","r12","ctr","xer","cc","memory");
    return (long)r3;
}

void kputs(const char *s) {
    while (*s) {
        u64 buf[2] = {0,0};
        int n = 0;
        unsigned char *b = (unsigned char *)buf;
        while (*s && n < 8) {
            if (*s == '\n') { b[n++] = '\r'; if (n>=8) break; }
            b[n++] = (unsigned char)*s++;
        }
        hcall(H_PUT_TERM_CHAR, VTERM, (u64)n, buf[0], buf[1]);
    }
}

void kmain(void *fdt) {
    (void)fdt;
    kputs("TripleFault hardmode v1: ppc64 (big-endian, PAPR/pseries)\n");
    kputs("[[TF:M10:HELLO]]\n");

    /* YOUR JOB STARTS HERE.
     *
     * M15 is next: recover the per-run nonce from the platform. On pseries
     * it is in the flattened device tree, /chosen/bootargs, and the FDT
     * pointer arrived in r3 -- it is the `fdt` argument above. No, there is
     * no libfdt here.
     *
     * Note before you copy anything from an x86 kernel: this machine is
     * BIG-ENDIAN, and the FDT is big-endian too, which will hide the bug
     * rather than reveal it. It will stop hiding it at M30.
     */

    kputs("[[TF:HALT]]\n");
    for(;;) {}
}
