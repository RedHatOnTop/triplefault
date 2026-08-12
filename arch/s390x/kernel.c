typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32; typedef unsigned long u64;
#define SCLP_CMD_WRITE_EVENT_DATA 0x00760005
#define SCLP_CMD_WRITE_EVENT_MASK 0x00780005
#define EVT_ASCII 0x1a
#define MASK_ASCII 0x00000040

static u8 sccb_buf[4096] __attribute__((aligned(4096)));

static int servc(u32 cmd, void *sccb) {
    int cc;
    __asm__ volatile(
        "       .insn rre,0xb2200000,%1,%2\n"
        "       ipm   %0\n"
        "       srl   %0,28\n"
        : "=d"(cc) : "d"((u64)cmd), "a"((u64)(unsigned long)sccb) : "cc","memory");
    return cc;
}

static void sclp_setup(void) {
    u8 *s = sccb_buf; for (int i=0;i<64;i++) s[i]=0;
    *(u16*)(s+0) = 28;            /* length */
    *(u16*)(s+10) = 4;            /* mask_length */
    *(u32*)(s+12) = MASK_ASCII;   /* receive mask */
    *(u32*)(s+16) = MASK_ASCII;   /* send mask    */
    servc(SCLP_CMD_WRITE_EVENT_MASK, s);
}

void kputs(const char *m) {
    unsigned len = 0; while (m[len]) len++;
    u8 *s = sccb_buf; for (unsigned i=0;i<sizeof(sccb_buf);i++) s[i]=0;
    *(u16*)(s+0) = (u16)(8 + 6 + len);
    *(u16*)(s+8) = (u16)(6 + len);
    s[10] = EVT_ASCII;                   /* evbuf type   */
    for (unsigned i=0;i<len;i++) s[14+i] = (u8)m[i];
    servc(SCLP_CMD_WRITE_EVENT_DATA, s);
}

void kmain(void) {
    sclp_setup();
    kputs("TripleFault hardmode v1: s390x (z/Architecture, SCLP console)\n");
    kputs("[[TF:M10:HELLO]]\n");

    /* YOUR JOB STARTS HERE.
     *
     * M15 is next: recover the per-run nonce from the kernel command line.
     * The s390 boot protocol leaves it at absolute address 0x10480. Reading
     * it is easy. Everything after it is not.
     *
     * Fair warning about this target: there is no MMU you have seen before,
     * no port I/O, no interrupt controller you can name, and channel I/O is
     * how devices work. Most of what search returns about "writing an OS"
     * is, here, actively wrong.
     */

    kputs("[[TF:HALT]]\n");
    for(;;) {}
}
