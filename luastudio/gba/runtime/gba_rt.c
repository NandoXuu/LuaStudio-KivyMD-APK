/* LuaStudio GBA runtime - implementacao. Compilada em todo build. */
#include "gba.h"

extern const u8  gba_font[95][8];       /* gerados em gba_data.c */
extern const u16 gba_note_pulse[128];
extern const u16 gba_note_wave[128];

#ifdef GBA_HOST
u8 gba_host_io[0x400], gba_host_pal[0x400], gba_host_vram[0x18000], gba_host_oam[0x400];
void (*gba_host_vsync_hook)(void);
#endif

u16 key_cur, key_prev;
static volatile u32 g_frames;
static u32 g_rng = 0x1234567u;

/* ===================================================================== */
/*  memoria                                                              */
/* ===================================================================== */
#ifndef GBA_HOST
IWRAM_CODE void *memcpy(void *d, const void *s, unsigned n)
{
    u8 *dp = (u8 *)d; const u8 *sp = (const u8 *)s;
    if ((((u32)dp | (u32)sp) & 3) == 0) {
        u32 *dw = (u32 *)dp; const u32 *sw = (const u32 *)sp;
        while (n >= 4) { *dw++ = *sw++; n -= 4; }
        dp = (u8 *)dw; sp = (const u8 *)sw;
    }
    while (n--) *dp++ = *sp++;
    return d;
}
IWRAM_CODE void *memset(void *d, int c, unsigned n)
{
    u8 *p = (u8 *)d;
    if (n >= 8 && (((u32)p & 3) == 0)) {
        u32 v = (u8)c; v |= v << 8; v |= v << 16;
        u32 *w = (u32 *)p;
        while (n >= 4) { *w++ = v; n -= 4; }
        p = (u8 *)w;
    }
    while (n--) *p++ = (u8)c;
    return d;
}
IWRAM_CODE void *memmove(void *d, const void *s, unsigned n)
{
    u8 *dp = (u8 *)d; const u8 *sp = (const u8 *)s;
    if (dp <= sp || dp >= sp + n) return memcpy(d, s, n);
    dp += n; sp += n;
    while (n--) *--dp = *--sp;
    return d;
}
#endif

IWRAM_CODE void cpu_copy32(void *dst, const void *src, u32 words)
{
    u32 *d = (u32 *)dst; const u32 *s = (const u32 *)src;
    while (words >= 8) {
        u32 a = s[0], b = s[1], c = s[2], e = s[3], f = s[4], g = s[5], h = s[6], i = s[7];
        d[0] = a; d[1] = b; d[2] = c; d[3] = e; d[4] = f; d[5] = g; d[6] = h; d[7] = i;
        d += 8; s += 8; words -= 8;
    }
    while (words--) *d++ = *s++;
}
IWRAM_CODE void cpu_fill32(void *dst, u32 v, u32 words)
{
    u32 *d = (u32 *)dst;
    while (words >= 8) {
        d[0] = v; d[1] = v; d[2] = v; d[3] = v; d[4] = v; d[5] = v; d[6] = v; d[7] = v;
        d += 8; words -= 8;
    }
    while (words--) *d++ = v;
}

#ifdef GBA_HOST
void dma_copy32(void *d, const void *s, u32 w) { cpu_copy32(d, s, w); }
void dma_fill32(void *d, u32 v, u32 w) { cpu_fill32(d, v, w); }
#else
void dma_copy32(void *dst, const void *src, u32 words)
{
    if (words < 16) { cpu_copy32(dst, src, words); return; }
    IO32(0xD4) = (u32)src; IO32(0xD8) = (u32)dst;
    IO32(0xDC) = (0x8400u << 16) | words;         /* enable | 32 bits */
    __asm volatile("nop; nop" ::: "memory");      /* CPU para ate o DMA acabar */
}
void dma_fill32(void *dst, u32 value, u32 words)
{
    static u32 v; v = value;
    IO32(0xD4) = (u32)&v; IO32(0xD8) = (u32)dst;
    IO32(0xDC) = (0x8500u << 16) | words;         /* src fixa */
    __asm volatile("nop; nop" ::: "memory");
}
#endif

/* LZ77 do BIOS (tipo 0x10) para RAM de destino */
void lz77_decompress(const void *src, void *dst)
{
    const u8 *s = (const u8 *)src; u8 *d = (u8 *)dst;
    u32 size = s[1] | (s[2] << 8) | ((u32)s[3] << 16);
    u8 *end = d + size; s += 4;
    while (d < end) {
        u32 flags = *s++;
        for (int i = 0; i < 8 && d < end; i++, flags <<= 1) {
            if (flags & 0x80) {
                u32 len = (s[0] >> 4) + 3;
                u32 disp = (((s[0] & 15) << 8) | s[1]) + 1; s += 2;
                while (len-- && d < end) { *d = d[-(int)disp]; d++; }
            } else *d++ = *s++;
        }
    }
}

/* ===================================================================== */
/*  matematica                                                           */
/* ===================================================================== */
void rand_seed(u32 s) { g_rng = s ? s : 0x1234567u; }
u32 rand_u32(void)
{
    u32 x = g_rng; x ^= x << 13; x ^= x >> 17; x ^= x << 5; return g_rng = x;
}
u32 isqrt32(u32 v)
{
    u32 r = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit) {
        if (v >= r + bit) { v -= r + bit; r = (r >> 1) + bit; } else r >>= 1;
        bit >>= 2;
    }
    return r;
}

/* ===================================================================== */
/*  video                                                                */
/* ===================================================================== */
static int g_mode = 3;
u8 *gfx_buf;
u32 frame_count(void) { return g_frames; }

void gfx_init(int mode)
{
    g_mode = (mode == 4) ? 4 : 3;
    REG_DISPCNT = (g_mode == 4 ? DCNT_MODE4 : DCNT_MODE3) | DCNT_BG2;
    gfx_buf = (g_mode == 4) ? MEM_VRAM + 0xA000 : MEM_VRAM;   /* modo 4: desenha na pagina oculta */
}
void gfx_flip(void)
{
    if (g_mode != 4) return;
    REG_DISPCNT ^= DCNT_PAGE;
    gfx_buf = (REG_DISPCNT & DCNT_PAGE) ? MEM_VRAM : MEM_VRAM + 0xA000;
}

/* preenche n pixels de 16 bits (alinhamento 2 ou 4) */
IWRAM_CODE static void fill16(u16 *p, u16 v, int n)
{
    if (n <= 0) return;
    if (((u32)p & 2) && n) { *p++ = v; n--; }
    u32 w = v | ((u32)v << 16);
    u32 *q = (u32 *)p;
    while (n >= 16) {
        q[0] = w; q[1] = w; q[2] = w; q[3] = w; q[4] = w; q[5] = w; q[6] = w; q[7] = w;
        q += 8; n -= 16;
    }
    while (n >= 2) { *q++ = w; n -= 2; }
    if (n) *(u16 *)q = v;
}

/* pixel de 8 bits em VRAM exige leitura-modificacao-escrita de 16 bits */
IWRAM_CODE static inline void put8(u8 *base, int idx, u32 c)
{
    u16 *p = (u16 *)base + (idx >> 1);
    if (idx & 1) *p = (u16)((*p & 0x00FF) | (c << 8));
    else         *p = (u16)((*p & 0xFF00) | (c & 0xFF));
}

IWRAM_CODE static void hline_nc(int x, int y, int w, u32 c)   /* ja recortado */
{
    if (g_mode == 3) { fill16((u16 *)gfx_buf + y * SCREEN_W + x, (u16)c, w); return; }
    int idx = y * SCREEN_W + x;
    u8 col = (u8)c;
    if (idx & 1) { put8(gfx_buf, idx, col); idx++; w--; }
    u16 pair = (u16)(col | (col << 8));
    fill16((u16 *)gfx_buf + (idx >> 1), pair, w >> 1);
    if (w & 1) put8(gfx_buf, idx + w - 1, col);
}

IWRAM_CODE void gfx_clear(u32 c)
{
    if (g_mode == 3) cpu_fill32(gfx_buf, (c & 0xFFFF) * 0x10001u, SCREEN_W * SCREEN_H / 2);
    else             cpu_fill32(gfx_buf, (c & 0xFF) * 0x01010101u, SCREEN_W * SCREEN_H / 4);
}

IWRAM_CODE void gfx_pixel(int x, int y, u32 c)
{
    if ((u32)x >= SCREEN_W || (u32)y >= SCREEN_H) return;
    if (g_mode == 3) ((u16 *)gfx_buf)[y * SCREEN_W + x] = (u16)c;
    else put8(gfx_buf, y * SCREEN_W + x, c);
}
u32 gfx_get(int x, int y)
{
    if ((u32)x >= SCREEN_W || (u32)y >= SCREEN_H) return 0;
    if (g_mode == 3) return ((u16 *)gfx_buf)[y * SCREEN_W + x];
    return gfx_buf[y * SCREEN_W + x] & 0xFF;   /* leitura de 8 bits em VRAM e permitida */
}

IWRAM_CODE void gfx_hline(int x, int y, int w, u32 c)
{
    if ((u32)y >= SCREEN_H) return;
    if (x < 0) { w += x; x = 0; }
    if (x + w > SCREEN_W) w = SCREEN_W - x;
    if (w > 0) hline_nc(x, y, w, c);
}
IWRAM_CODE void gfx_vline(int x, int y, int h, u32 c)
{
    if ((u32)x >= SCREEN_W) return;
    if (y < 0) { h += y; y = 0; }
    if (y + h > SCREEN_H) h = SCREEN_H - y;
    if (h <= 0) return;
    if (g_mode == 3) {
        u16 *p = (u16 *)gfx_buf + y * SCREEN_W + x;
        while (h--) { *p = (u16)c; p += SCREEN_W; }
    } else {
        int idx = y * SCREEN_W + x;
        while (h--) { put8(gfx_buf, idx, c); idx += SCREEN_W; }
    }
}
IWRAM_CODE void gfx_fill(int x, int y, int w, int h, u32 c)
{
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > SCREEN_W) w = SCREEN_W - x;
    if (y + h > SCREEN_H) h = SCREEN_H - y;
    if (w <= 0 || h <= 0) return;
    for (int j = 0; j < h; j++) hline_nc(x, y + j, w, c);
}
void gfx_rect(int x, int y, int w, int h, u32 c)
{
    if (w <= 0 || h <= 0) return;
    gfx_hline(x, y, w, c); gfx_hline(x, y + h - 1, w, c);
    gfx_vline(x, y + 1, h - 2, c); gfx_vline(x + w - 1, y + 1, h - 2, c);
}
IWRAM_CODE void gfx_line(int x0, int y0, int x1, int y1, u32 c)
{
    if (y0 == y1) { gfx_hline(x0 < x1 ? x0 : x1, y0, ABS(x1 - x0) + 1, c); return; }
    if (x0 == x1) { gfx_vline(x0, y0 < y1 ? y0 : y1, ABS(y1 - y0) + 1, c); return; }
    int dx = ABS(x1 - x0), sx = x0 < x1 ? 1 : -1;
    int dy = -ABS(y1 - y0), sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    for (;;) {
        gfx_pixel(x0, y0, c);
        if (x0 == x1 && y0 == y1) break;
        int e2 = err << 1;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}
void gfx_circle(int cx, int cy, int r, u32 c)
{
    int x = r, y = 0, err = 1 - r;
    while (x >= y) {
        gfx_pixel(cx + x, cy + y, c); gfx_pixel(cx - x, cy + y, c);
        gfx_pixel(cx + x, cy - y, c); gfx_pixel(cx - x, cy - y, c);
        gfx_pixel(cx + y, cy + x, c); gfx_pixel(cx - y, cy + x, c);
        gfx_pixel(cx + y, cy - x, c); gfx_pixel(cx - y, cy - x, c);
        y++;
        if (err < 0) err += 2 * y + 1; else { x--; err += 2 * (y - x) + 1; }
    }
}
void gfx_fill_circle(int cx, int cy, int r, u32 c)
{
    int x = r, y = 0, err = 1 - r;
    while (x >= y) {
        gfx_hline(cx - x, cy + y, 2 * x + 1, c); gfx_hline(cx - x, cy - y, 2 * x + 1, c);
        gfx_hline(cx - y, cy + x, 2 * y + 1, c); gfx_hline(cx - y, cy - x, 2 * y + 1, c);
        y++;
        if (err < 0) err += 2 * y + 1; else { x--; err += 2 * (y - x) + 1; }
    }
}

IWRAM_CODE void gfx_blit(const void *img, int x, int y, int w, int h, int transp)
{
    int sx = 0, sy = 0, stride = w;
    if (x < 0) { sx = -x; w += x; x = 0; }
    if (y < 0) { sy = -y; h += y; y = 0; }
    if (x + w > SCREEN_W) w = SCREEN_W - x;
    if (y + h > SCREEN_H) h = SCREEN_H - y;
    if (w <= 0 || h <= 0) return;
    if (g_mode == 3) {
        const u16 *src = (const u16 *)img + sy * stride + sx;
        u16 *dst = (u16 *)gfx_buf + y * SCREEN_W + x;
        for (int j = 0; j < h; j++, src += stride, dst += SCREEN_W) {
            if (transp < 0) {
                int i = 0;
                if (((u32)dst & 2) && w) { dst[0] = src[0]; i = 1; }
                if ((((u32)(src + i)) & 2) == 0) {
                    cpu_copy32(dst + i, src + i, (w - i) >> 1);
                    i += (w - i) & ~1;
                }
                for (; i < w; i++) dst[i] = src[i];
            } else {
                for (int i = 0; i < w; i++) { u16 p = src[i]; if (p != (u16)transp) dst[i] = p; }
            }
        }
    } else {
        const u8 *src = (const u8 *)img + sy * stride + sx;
        for (int j = 0; j < h; j++, src += stride) {
            int idx = (y + j) * SCREEN_W + x;
            for (int i = 0; i < w; i++) {
                u8 p = src[i];
                if (transp < 0 || p != (u8)transp) put8(gfx_buf, idx + i, p);
            }
        }
    }
}
void gfx_set_palette(int first, const u16 *pal, int count)
{
    for (int i = 0; i < count; i++) PAL_BG(first + i) = pal[i];
}

/* ------------------------------------------------------------- texto */
int str_len(const char *s) { int n = 0; while (s[n]) n++; return n; }

char *int_to_str(int v, char *buf)
{
    char *p = buf + 11; *p = 0;
    u32 u = v < 0 ? (u32)(-v) : (u32)v;
    do {
        u32 q = (u * 0xCCCDu) >> 19;                /* u/10 sem divisao (u < 2^16 ok) */
        if (u >= 65536) q = u / 10;
        *--p = (char)('0' + (u - q * 10)); u = q;
    } while (u);
    if (v < 0) *--p = '-';
    return p;
}

IWRAM_CODE static void glyph(int x, int y, int ch, u32 c, int has_bg, u32 bg)
{
    /* ASCII imprimivel (32..126). Evita indexacao invalida com chars signed. */
    if (ch < 32 || ch > 126) ch = '?';
    const u8 *g = gba_font[(u32)(ch - 32)];

    /* Caminho unico e seguro para modos 3 e 4, inclusive texto parcialmente
       fora da tela. A fonte e armazenada por LINHAS, bit 0 = pixel esquerdo. */
    for (int j = 0; j < 8; j++) {
        u8 bits = g[j];
        for (int i = 0; i < 8; i++) {
            int px = x + i;
            int py = y + j;
            if ((u32)px >= SCREEN_W || (u32)py >= SCREEN_H) continue;
            if (bits & (1u << i)) gfx_pixel(px, py, c);
            else if (has_bg) gfx_pixel(px, py, bg);
        }
    }
}
void gfx_text(int x, int y, const char *s, u32 c)
{
    for (; *s; s++, x += 8) { if (*s == '\n') { y += 8; x = -8; continue; } glyph(x, y, *s, c, 0, 0); }
}
void gfx_text_bg(int x, int y, const char *s, u32 c, u32 bg)
{
    for (; *s; s++, x += 8) { if (*s == '\n') { y += 8; x = -8; continue; } glyph(x, y, *s, c, 1, bg); }
}
void gfx_int(int x, int y, int v, u32 c) { char b[12]; gfx_text(x, y, int_to_str(v, b), c); }
void gfx_hex(int x, int y, u32 v, int digits, u32 c)
{
    char b[9]; if (digits > 8) digits = 8; if (digits < 1) digits = 1;
    for (int i = 0; i < digits; i++) { u32 n = (v >> (4 * (digits - 1 - i))) & 15; b[i] = (char)(n < 10 ? '0' + n : 'A' + n - 10); }
    b[digits] = 0; gfx_text(x, y, b, c);
}

/* ------------------------------------------------------ modo 0 / tiles */
void bg_tiles_4bpp(int cb, const void *tiles, u32 bytes) { cpu_copy32(MEM_VRAM + cb * 0x4000, tiles, (bytes + 3) >> 2); }
void bg_map(int sb, const u16 *map, u32 entries) { cpu_copy32(MEM_VRAM + sb * 0x800, map, (entries + 1) >> 1); }
void bg_config(int n, int cb, int sb, int size, int prio)
{
    REG_BGCNT(n) = (u16)(prio | (cb << 2) | (sb << 8) | (size << 14));
    REG_DISPCNT = (REG_DISPCNT & ~7) | DCNT_MODE0 | (DCNT_BG0 << n);
}
static int g_txt_sb = 31;
void txt_init(int bg, int cb, int sb)
{
    u32 *t = (u32 *)(MEM_VRAM + cb * 0x4000);
    for (int i = 0; i < 8; i++) t[i] = 0;                          /* tile 0 = espaco */
    for (int ch = 0; ch < 95; ch++)
        for (int j = 0; j < 8; j++) {
            u32 row = 0, bits = gba_font[ch][j];
            for (int i = 0; i < 8; i++) if (bits & (1u << i)) row |= 1u << (4 * i);
            t[ch * 8 + j] = row;
        }
    PAL_BG(0) = BLACK; PAL_BG(1) = WHITE;
    g_txt_sb = sb;
    bg_config(bg, cb, sb, 0, 0);
    txt_clear();
}
void txt_clear(void) { cpu_fill32(MEM_VRAM + g_txt_sb * 0x800, 0, 0x800 / 4); }
void txt_print(int tx, int ty, const char *s)
{
    u16 *map = (u16 *)(MEM_VRAM + g_txt_sb * 0x800);
    for (; *s && tx < 32; s++, tx++) {
        int c = *s - 32; if (c < 0 || c > 94) c = 0;
        map[ty * 32 + tx] = (u16)c;
    }
}

/* ------------------------------------------------------------ sprites */
static u16 g_oam[128 * 4] ALIGN4;
void spr_init(void)
{
    for (int i = 0; i < 128; i++) { g_oam[i * 4] = 0x200; g_oam[i * 4 + 1] = 0; g_oam[i * 4 + 2] = 0; g_oam[i * 4 + 3] = 0; }
    spr_flush();
    REG_DISPCNT |= DCNT_OBJ | DCNT_OBJ_1D;
}
void spr_set(int id, int x, int y, int tile, int pal, u32 size_flags)
{
    u16 *o = &g_oam[(id & 127) * 4];
    o[0] = (u16)(y & 0xFF);
    o[1] = (u16)((x & 0x1FF) | (size_flags & 0xF000));
    o[2] = (u16)((tile & 0x3FF) | (pal << 12));
}
void spr_hide(int id) { g_oam[(id & 127) * 4] = 0x200; }
void spr_flush(void) { cpu_copy32(MEM_OAM, g_oam, 128 * 4 / 2); }
void spr_tiles(int first, const void *d, u32 bytes) { cpu_copy32(MEM_VRAM + 0x10000 + first * 32, d, (bytes + 3) >> 2); }
void spr_palette(const u16 *pal, int n) { for (int i = 0; i < n; i++) PAL_OBJ(i) = pal[i]; }

/* ===================================================================== */
/*  som                                                                  */
/* ===================================================================== */
#define SQ1_L IO16(0x60)
#define SQ1_H IO16(0x62)
#define SQ1_X IO16(0x64)
#define SQ2_L IO16(0x68)
#define SQ2_H IO16(0x6C)
#define WAV_L IO16(0x70)
#define WAV_H IO16(0x72)
#define WAV_X IO16(0x74)
#define NSE_L IO16(0x78)
#define NSE_H IO16(0x7C)
#define SND_CNT_L IO16(0x80)
#define SND_CNT_H IO16(0x82)
#define SND_CNT_X IO16(0x84)

static const u8 *sn_base, *sn_pc;
static u16 sn_loop;
static int sn_wait;
static u8 sn_paused;
static u8 sn_len[4];
static const s8 *sn_pcm; static u32 sn_pcm_len, sn_pcm_hz, sn_pcm_frames; static u8 sn_pcm_loop;

static void wave_default(void)
{
    static const u8 tri[16] = { 0x10,0x32,0x54,0x76,0x98,0xBA,0xDC,0xFE,0xEF,0xCD,0xAB,0x89,0x67,0x45,0x23,0x01 };
    WAV_L = 0x40;                                   /* toca banco 1, escreve no banco 0 */
    for (int i = 0; i < 8; i++) IO16(0x90 + i * 2) = (u16)(tri[i * 2] | (tri[i * 2 + 1] << 8));
    WAV_L = 0x00;                                   /* toca o banco 0 */
}
void snd_init(void)
{
    SND_CNT_X = 0x80;
    SND_CNT_L = 0xFF77;
    SND_CNT_H = 0x0306 | 0x0800;     /* PSG 100%, FIFO A 100% em L+R (Timer0), reseta FIFO */
    wave_default();
}

IWRAM_CODE static void note_off(int ch)
{
    sn_len[ch] = 0;
    switch (ch) { case 0: SQ1_H = 0; break; case 1: SQ2_L = 0; break; case 2: WAV_L = 0; break; default: NSE_L = 0; }
}
IWRAM_CODE static void note_on(int ch, int note, int vb)
{
    int vol = vb & 15, duty = (vb >> 4) & 3, env = (vb >> 6) & 3;
    u16 e = (u16)((vol << 12) | (env << 8));
    switch (ch) {
    case 0: SQ1_L = 0; SQ1_H = (u16)((duty << 6) | e); SQ1_X = 0x8000 | gba_note_pulse[note & 127]; break;
    case 1: SQ2_L = (u16)((duty << 6) | e); SQ2_H = 0x8000 | gba_note_pulse[note & 127]; break;
    case 2: {
        int code = vol == 0 ? 0 : (vol >= 12 ? 1 : (vol >= 6 ? 2 : 3));
        WAV_L = 0x80; WAV_H = (u16)(code << 13); WAV_X = 0x8000 | gba_note_wave[note & 127]; break; }
    default: NSE_L = e; NSE_H = (u16)(0x8000 | (note & 0xFF)); break;     /* note = parametros do ruido */
    }
}

static void snd_silence(void) { for (int i = 0; i < 4; i++) note_off(i); }
void snd_play(const u8 *song)
{
    snd_silence();
    sn_base = song; sn_loop = (u16)(song[0] | (song[1] << 8));
    sn_pc = song + 4; sn_wait = 0; sn_paused = 0;
}
void snd_stop(void) { sn_pc = 0; snd_silence(); }
void snd_pause(int p) { sn_paused = (u8)p; if (p) snd_silence(); }
int  snd_playing(void) { return sn_pc != 0; }
void snd_beep(int ch, int note, int vol, int frames) { note_on(ch & 3, note, vol); sn_len[ch & 3] = (u8)(frames > 255 ? 255 : frames); }

static void pcm_start(void)
{
#ifndef GBA_HOST
    IO16(0xC6) = 0; IO16(0x102) = 0;
    SND_CNT_H |= 0x0800;
    IO32(0xBC) = (u32)sn_pcm; IO32(0xC0) = 0x040000A0; IO32(0xC4) = 0xB6400000u;
    IO16(0x100) = (u16)(65536 - 16777216 / sn_pcm_hz); IO16(0x102) = 0x80;
#endif
}
void snd_pcm_play(const s8 *data, u32 len, u32 hz, int loop)
{
    if (hz < 4000) hz = 4000;
    sn_pcm = data; sn_pcm_len = len; sn_pcm_hz = hz; sn_pcm_loop = (u8)loop;
    sn_pcm_frames = (len * 60u) / hz + 1;
    pcm_start();
}
void snd_pcm_stop(void)
{
    sn_pcm_frames = 0;
#ifndef GBA_HOST
    IO16(0xC6) = 0; IO16(0x102) = 0; SND_CNT_H |= 0x0800;
#endif
}

/* chamado 1x por frame (ISR de VBlank) */
IWRAM_CODE void snd_tick(void)
{
    for (int c = 0; c < 4; c++) if (sn_len[c] && --sn_len[c] == 0) note_off(c);
    if (sn_pcm_frames && --sn_pcm_frames == 0) { if (sn_pcm_loop) { sn_pcm_frames = (sn_pcm_len * 60u) / sn_pcm_hz + 1; pcm_start(); } else snd_pcm_stop(); }
    if (!sn_pc || sn_paused) return;
    if (sn_wait) { sn_wait--; return; }
    for (int guard = 0; guard < 512; guard++) {
        u8 op = *sn_pc++;
        if (op & 0x80) { sn_wait = op & 0x7F; return; }
        switch (op & 0xF0) {
        case 0x10: note_on(op & 3, sn_pc[0], sn_pc[1]); sn_pc += 2; break;
        case 0x20: note_off(op & 3); break;
        default:
            if (op == 2 && sn_loop != 0xFFFF) { sn_pc = sn_base + sn_loop; break; }
            snd_stop(); return;
        }
    }
}

/* ===================================================================== */
/*  IRQ / vsync                                                          */
/* ===================================================================== */
#ifndef GBA_HOST
IWRAM_CODE void gba_isr(void)
{
    u16 f = REG_IF & REG_IE;
    if (f & 1) { g_frames++; snd_tick(); }
    REG_IF = f;
    *(vu16 *)0x03007FF8 |= f;                      /* flag que o IntrWait do BIOS espera */
}
void gba_init(void)
{
    REG_IME = 0;
    *(vu32 *)0x03007FFC = (u32)gba_isr;
    REG_DISPSTAT |= 8;                             /* IRQ de VBlank */
    REG_IE |= 1; REG_IME = 1;
    snd_init();
}
void vsync(void)
{
#if defined(__thumb__)
    __asm volatile("swi 0x05" ::: "r0", "r1", "r2", "r3", "memory");
#else
    __asm volatile("swi 0x050000" ::: "r0", "r1", "r2", "r3", "memory");
#endif
}
#else
void gba_init(void) { snd_init(); }
void vsync(void) { g_frames++; snd_tick(); if (gba_host_vsync_hook) gba_host_vsync_hook(); }
#endif
