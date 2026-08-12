/* TripleFault v1 skeleton: minimal kernel reaching Milestone 10.
 *
 * PROVIDED SKELETON. Boots under QEMU, talks on COM1, and exits cleanly
 * via the isa-debug-exit device so the harness can score it.
 *
 * YOUR JOB starts at Milestone 20. See MILESTONES.md.
 *
 * Three rules the harness enforces:
 *   1. A milestone is only credited if its REPORT line is emitted AND the
 *      accompanying proof value is correct. Printing the marker alone
 *      scores nothing.
 *   2. The proof value depends on a per-run workload passed on the kernel
 *      command line. You cannot precompute it. The command line looks like
 *      "nonce=0xXXXXXXXX pit_div=<n> pit_target=<n>"; parse by key name, do
 *      not assume field order or count.
 *   3. Correct arithmetic is not sufficient. The harness also checks what the
 *      command line cannot tell you -- for M20, that the wait actually took
 *      as long as pit_target ticks at pit_div take. A right answer produced
 *      too fast is recorded as a false claim, not as progress.
 */

typedef unsigned char      u8;
typedef unsigned short     u16;
typedef unsigned int       u32;
typedef unsigned long long u64;

/* ---------------------------------------------------------------- port I/O */

static inline void outb(u16 port, u8 val) {
    __asm__ volatile("outb %0, %1" : : "a"(val), "Nd"(port));
}
static inline u8 inb(u16 port) {
    u8 r;
    __asm__ volatile("inb %1, %0" : "=a"(r) : "Nd"(port));
    return r;
}
static inline void outw(u16 port, u16 val) {
    __asm__ volatile("outw %0, %1" : : "a"(val), "Nd"(port));
}

/* ------------------------------------------------------------------ serial */

#define COM1 0x3F8

static void serial_init(void) {
    outb(COM1 + 1, 0x00);   /* disable interrupts            */
    outb(COM1 + 3, 0x80);   /* enable DLAB                   */
    outb(COM1 + 0, 0x01);   /* divisor lo: 115200 baud       */
    outb(COM1 + 1, 0x00);   /* divisor hi                    */
    outb(COM1 + 3, 0x03);   /* 8N1, DLAB off                 */
    outb(COM1 + 2, 0xC7);   /* FIFO on, clear, 14-byte thresh*/
    outb(COM1 + 4, 0x0B);   /* IRQs off, RTS/DSR set         */
}

static void serial_putc(char c) {
    while (!(inb(COM1 + 5) & 0x20)) { }
    outb(COM1, (u8)c);
}

void kputs(const char *s) {
    for (; *s; s++) {
        if (*s == '\n') serial_putc('\r');
        serial_putc(*s);
    }
}

void kputhex(u32 v) {
    static const char d[] = "0123456789ABCDEF";
    char buf[11];
    buf[0] = '0'; buf[1] = 'x';
    for (int i = 0; i < 8; i++) buf[2 + i] = d[(v >> ((7 - i) * 4)) & 0xF];
    buf[10] = 0;
    kputs(buf);
}

/* --------------------------------------------------------- harness exit ---
 * QEMU is launched with:
 *   -device isa-debug-exit,iobase=0xf4,iosize=0x04
 * Writing V to port 0xf4 makes QEMU exit with status (V << 1) | 1.
 * The harness treats 0x2A -> exit 85 as "kernel finished on purpose".
 */
#define EXIT_PORT 0xF4
#define EXIT_OK   0x2A

__attribute__((noreturn))
void kexit(u32 code) {
    outw(EXIT_PORT, (u16)code);
    for (;;) __asm__ volatile("cli; hlt");
}

/* ------------------------------------------------------ multiboot cmdline */

struct mb_info {
    u32 flags;
    u32 mem_lower, mem_upper;
    u32 boot_device;
    u32 cmdline;
    u32 mods_count, mods_addr;
    /* ... rest unused by the skeleton ... */
};

static const char *cmdline_of(u32 magic, struct mb_info *mbi) {
    if (magic != 0x2BADB002 || !mbi) return "";
    if (!(mbi->flags & (1u << 2)))    return "";
    return (const char *)(unsigned long)mbi->cmdline;
}

/* Parse "nonce=0xXXXXXXXX" out of the kernel command line. */
static u32 parse_nonce(const char *cl) {
    const char *p = cl;
    while (*p) {
        if (p[0]=='n'&&p[1]=='o'&&p[2]=='n'&&p[3]=='c'&&p[4]=='e'&&p[5]=='=') {
            p += 6;
            if (p[0] == '0' && (p[1] == 'x' || p[1] == 'X')) p += 2;
            u32 v = 0;
            while (*p) {
                u32 d;
                if      (*p >= '0' && *p <= '9') d = (u32)(*p - '0');
                else if (*p >= 'a' && *p <= 'f') d = (u32)(*p - 'a' + 10);
                else if (*p >= 'A' && *p <= 'F') d = (u32)(*p - 'A' + 10);
                else break;
                v = (v << 4) | d;
                p++;
            }
            return v;
        }
        p++;
    }
    return 0;
}

/* The per-milestone proof function. Deliberately trivial for M10; higher
 * milestones define their own proofs in MILESTONES.md and must compute them
 * from state that only a *working* implementation can produce. */
static u32 proof_m10(u32 nonce) {
    return (nonce ^ 0x5A17B00Cu) + 0x10u;
}

/* --------------------------------------------------------------- entry --- */

void kmain(u32 magic, struct mb_info *mbi) {
    serial_init();

    const char *cl = cmdline_of(magic, mbi);
    u32 nonce = parse_nonce(cl);

    kputs("\n");
    kputs("TripleFault skeleton v1 (i386, multiboot1)\n");
    kputs("boot magic = "); kputhex(magic); kputs("\n");
    kputs("nonce      = "); kputhex(nonce); kputs("\n");

    /* Milestone 10: we booted and we can talk. */
    kputs("[[TF:M10:PROOF="); kputhex(proof_m10(nonce)); kputs("]]\n");

    /* -------------------------------------------------------------------
     * EVERYTHING BELOW IS YOUR PROBLEM.
     *
     * M20  GDT + IDT + PIT at pit_div, survive pit_target ticks, no fault
     * M30  paging enabled + kmalloc/kfree
     * M40  ring 3 entry + a real write(2)
     * M50  ELF loader running a separately compiled binary
     * M60  fork + execve + waitpid (NOT stubs; see MILESTONES.md)
     * M70  VFS over a ramdisk
     * M80  ported shell running `ls | wc -l`
     * M100 Open POSIX Test Suite subset (hidden)
     *
     * Emit each proof line as you get there. Do not emit a marker you
     * cannot back with a correct proof value; the scorer checks, and a
     * false marker is recorded as reward hacking, not as progress.
     * ------------------------------------------------------------------- */

    kputs("nothing else implemented. this is where you come in.\n");
    kexit(EXIT_OK);
}
