/* LuaStudio GBA runtime (gba.h)
 * Biblioteca minima e otimizada para o Game Boy Advance.
 * Tudo aqui foi pensado para ARM7TDMI @16.78MHz, sem FPU, sem malloc e sem libc.
 *
 * Compila no GBA (arm-none-eabi-gcc) e, com -DGBA_HOST, no PC (testes).
 */
#ifndef GBA_H
#define GBA_H

#ifdef __cplusplus
extern "C" {
#endif

typedef unsigned char  u8;   typedef signed char  s8;
typedef unsigned short u16;  typedef signed short s16;
typedef unsigned int   u32;  typedef signed int   s32;
typedef volatile u8  vu8;    typedef volatile u16 vu16;   typedef volatile u32 vu32;
typedef s32 fixed;                 /* ponto fixo 24.8 */
typedef u16 color_t;
#ifndef NULL
#define NULL ((void *)0)
#endif

/* ------------------------------------------------------------- memoria */
#ifdef GBA_HOST
extern u8 gba_host_io[0x400], gba_host_pal[0x400], gba_host_vram[0x18000],
          gba_host_oam[0x400];
#define MEM_IO   ((u8 *)gba_host_io)
#define MEM_PAL  ((u8 *)gba_host_pal)
#define MEM_VRAM ((u8 *)gba_host_vram)
#define MEM_OAM  ((u8 *)gba_host_oam)
#define IWRAM_CODE
#define IWRAM_DATA
#define EWRAM_DATA
#define EWRAM_BSS
#else
#define MEM_IO   ((u8 *)0x04000000)
#define MEM_PAL  ((u8 *)0x05000000)
#define MEM_VRAM ((u8 *)0x06000000)
#define MEM_OAM  ((u8 *)0x07000000)
/* Codigo quente roda em IWRAM (barramento 32 bits, 0 wait states): 3-5x mais rapido que a ROM */
#define IWRAM_CODE __attribute__((section(".iwram.text"), long_call, target("arm")))
#define IWRAM_DATA __attribute__((section(".iwram")))
#define EWRAM_DATA __attribute__((section(".ewram")))   /* inicializado */
#define EWRAM_BSS  __attribute__((section(".sbss")))    /* NAO zerado */
#endif
#define ALIGN4 __attribute__((aligned(4)))
#define INLINE static inline __attribute__((always_inline))

#define IO16(o) (*(vu16 *)(MEM_IO + (o)))
#define IO32(o) (*(vu32 *)(MEM_IO + (o)))
#define REG_DISPCNT   IO16(0x000)
#define REG_DISPSTAT  IO16(0x004)
#define REG_VCOUNT    IO16(0x006)
#define REG_BGCNT(n)  IO16(0x008 + 2 * (n))
#define REG_BGHOFS(n) IO16(0x010 + 4 * (n))
#define REG_BGVOFS(n) IO16(0x012 + 4 * (n))
#define REG_KEYINPUT  IO16(0x130)
#define REG_IE        IO16(0x200)
#define REG_IF        IO16(0x202)
#define REG_IME       IO16(0x208)

/* ---------------------------------------------------------------- video */
#define SCREEN_W 240
#define SCREEN_H 160
#define RGB15(r, g, b) ((color_t)((r) | ((g) << 5) | ((b) << 10)))
#define RGB8(r, g, b)  RGB15((r) >> 3, (g) >> 3, (b) >> 3)
#define BLACK RGB15(0, 0, 0)
#define WHITE RGB15(31, 31, 31)
#define RED   RGB15(31, 0, 0)
#define GREEN RGB15(0, 31, 0)
#define BLUE  RGB15(0, 0, 31)
#define YELLOW RGB15(31, 31, 0)

#define DCNT_MODE0 0x0000
#define DCNT_MODE3 0x0003
#define DCNT_MODE4 0x0004
#define DCNT_BG0 0x0100
#define DCNT_BG1 0x0200
#define DCNT_BG2 0x0400
#define DCNT_BG3 0x0800
#define DCNT_OBJ 0x1000
#define DCNT_OBJ_1D 0x0040
#define DCNT_PAGE 0x0010

#define PAL_BG(i)  (((vu16 *)MEM_PAL)[i])
#define PAL_OBJ(i) (((vu16 *)(MEM_PAL + 0x200))[i])

void gba_init(void);        /* IRQ de VBlank + som (chame primeiro) */
void vsync(void);           /* espera o VBlank dormindo (economiza bateria) */
u32  frame_count(void);     /* VBlanks desde gba_init */

/* ---------------------------------------------------------------- input */
#define KEY_A 0x001
#define KEY_B 0x002
#define KEY_SELECT 0x004
#define KEY_START 0x008
#define KEY_RIGHT 0x010
#define KEY_LEFT 0x020
#define KEY_UP 0x040
#define KEY_DOWN 0x080
#define KEY_R 0x100
#define KEY_L 0x200
extern u16 key_cur, key_prev;
INLINE void key_poll(void) { key_prev = key_cur; key_cur = (u16)(~REG_KEYINPUT & 0x3FF); }
INLINE int  key_held(u16 k)     { return (key_cur & k) != 0; }
INLINE int  key_pressed(u16 k)  { return (key_cur & ~key_prev & k) != 0; }
INLINE int  key_released(u16 k) { return (~key_cur & key_prev & k) != 0; }
INLINE int  key_axis_x(void) { return ((key_cur >> 4) & 1) - ((key_cur >> 5) & 1); }
INLINE int  key_axis_y(void) { return ((key_cur >> 7) & 1) - ((key_cur >> 6) & 1); }

/* ------------------------------------------------------- matematica fixa */
#define FIX(x)      ((fixed)((x) * 256))
#define FIX_INT(f)  ((f) >> 8)
INLINE fixed fix_mul(fixed a, fixed b) { return (a * b) >> 8; }
extern const s16 gba_sin_lut[256];            /* sin(2*pi*i/256) em 8.8 */
INLINE fixed fsin(u32 a) { return gba_sin_lut[a & 255]; }   /* a: 0..255 = 0..360 */
INLINE fixed fcos(u32 a) { return gba_sin_lut[(a + 64) & 255]; }
u32 rand_u32(void);           /* xorshift32 */
void rand_seed(u32 s);
INLINE int rand_range(int lo, int hi) { return lo + (int)((rand_u32() >> 8) % (u32)(hi - lo + 1)); }
u32 isqrt32(u32 v);
#define ABS(x) ((x) < 0 ? -(x) : (x))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define CLAMP(v, lo, hi) ((v) < (lo) ? (lo) : ((v) > (hi) ? (hi) : (v)))

/* ------------------------------------------------------------- memoria */
#ifndef GBA_HOST
void *memcpy(void *d, const void *s, unsigned n);
void *memset(void *d, int c, unsigned n);
void *memmove(void *d, const void *s, unsigned n);
#else
#include <string.h>
#endif
void  cpu_copy32(void *dst, const void *src, u32 words);  /* ldmia/stmia, 8 palavras/iteracao */
void  cpu_fill32(void *dst, u32 value, u32 words);
void  dma_copy32(void *dst, const void *src, u32 words);   /* DMA3 (so se for > ~16 palavras) */
void  dma_fill32(void *dst, u32 value, u32 words);
void  lz77_decompress(const void *src, void *dst);         /* formato BIOS LZ77 (assets compactados) */

/* ----------------------------------------------------------- draw API */
/* Modo 3: 240x160, 15 bits, buffer unico (simples).
 * Modo 4: 240x160, paleta de 256, 2 paginas (gfx_flip) - metade da banda de VRAM. */
void gfx_init(int mode);                 /* 3 ou 4 */
void gfx_flip(void);                     /* modo 4: troca de pagina (chame apos vsync) */
void gfx_clear(u32 color);               /* modo 3: RGB15; modo 4: indice */
void gfx_pixel(int x, int y, u32 c);
u32  gfx_get(int x, int y);
void gfx_hline(int x, int y, int w, u32 c);
void gfx_vline(int x, int y, int h, u32 c);
void gfx_line(int x0, int y0, int x1, int y1, u32 c);
void gfx_rect(int x, int y, int w, int h, u32 c);       /* contorno */
void gfx_fill(int x, int y, int w, int h, u32 c);       /* preenchido */
void gfx_circle(int cx, int cy, int r, u32 c);
void gfx_fill_circle(int cx, int cy, int r, u32 c);
/* blit: img = u16 (modo 3) ou u8 (modo 4); transp = cor a ignorar, ou -1 para opaco */
void gfx_blit(const void *img, int x, int y, int w, int h, int transp);
void gfx_set_palette(int first, const u16 *pal, int count);   /* modo 4 */
extern u8 *gfx_buf;                       /* pagina de desenho atual */

/* texto: fonte 5x7 embutida em 8x8 (ASCII 32..126) */
void gfx_text(int x, int y, const char *s, u32 c);
void gfx_text_bg(int x, int y, const char *s, u32 c, u32 bg);
void gfx_int(int x, int y, int v, u32 c);
void gfx_hex(int x, int y, u32 v, int digits, u32 c);
int  str_len(const char *s);
char *int_to_str(int v, char *buf);       /* buf >= 12 bytes; devolve inicio */

/* ------------------------------------------------- modo 0 (tiles) + texto */
void bg_tiles_4bpp(int charblock, const void *tiles, u32 bytes);
void bg_map(int screenblock, const u16 *map, u32 entries);
void bg_config(int n, int charblock, int screenblock, int size, int prio);
void txt_init(int bg, int charblock, int screenblock);  /* carrega fonte como tiles */
void txt_print(int tx, int ty, const char *s);           /* escreve no mapa (tiles 8x8) */
void txt_clear(void);

/* ------------------------------------------------------------- sprites */
#define SPR_8x8   0x0000
#define SPR_16x16 0x4000
#define SPR_32x32 0x8000
#define SPR_64x64 0xC000
#define SPR_HFLIP 0x1000
#define SPR_VFLIP 0x2000
void spr_init(void);                                  /* esconde os 128, ativa OBJ 1D */
void spr_set(int id, int x, int y, int tile, int pal, u32 size_flags);
void spr_hide(int id);
void spr_flush(void);                                 /* copia o shadow-OAM (chame no VBlank) */
void spr_tiles(int first_tile, const void *data, u32 bytes);
void spr_palette(const u16 *pal, int count);

/* ----------------------------------------------------------------- som */
/* Musica: stream compacto gerado do .mid (tools: midi -> .gbm). Toca no ISR de VBlank. */
void snd_init(void);
void snd_play(const u8 *song);
void snd_stop(void);
void snd_pause(int paused);
int  snd_playing(void);
/* Efeitos PCM: 8-bit signed mono, DMA + Timer0, custo de CPU ~0 */
void snd_pcm_play(const s8 *data, u32 len, u32 hz, int loop);
void snd_pcm_stop(void);
/* Efeitos PSG de uma linha: canal 0..3 (pulse1, pulse2, wave, noise) */
void snd_beep(int ch, int midi_note, int vol, int frames);

#ifdef GBA_HOST
extern void (*gba_host_vsync_hook)(void);
#endif

#ifdef __cplusplus
}
#endif
#endif
