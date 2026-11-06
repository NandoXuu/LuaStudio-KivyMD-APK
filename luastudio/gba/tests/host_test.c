/* Teste no PC do runtime GBA (compilado com -DGBA_HOST): dumpa VRAM e eventos de som. */
#include <stdio.h>
#include <stdlib.h>
#include "gba.h"
extern const u8 test_song[];
extern const u8 test_lz[];
extern const unsigned test_lz_size;

static FILE *log_f;
static void hook(void) { fprintf(log_f, "%u %u %u %u\n", (unsigned)frame_count(), IO16(0x64) & 0x7FF, IO16(0x6C) & 0x7FF, IO16(0x62) >> 12); }

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "gfx3";
    if (mode[3] == '3' || mode[3] == '4') {
        int m = mode[3] - '0';
        gba_init(); gfx_init(m);
        if (m == 4) { u16 pal[8] = {0, WHITE, RED, GREEN, BLUE, YELLOW, RGB15(31,0,31), RGB15(0,31,31)}; gfx_set_palette(0, pal, 8); }
        u32 W = m == 3 ? WHITE : 1, R = m == 3 ? RED : 2, G = m == 3 ? GREEN : 3, B = m == 3 ? BLUE : 4, Y = m == 3 ? YELLOW : 5;
        gfx_clear(0);
        gfx_fill(10, 10, 41, 21, R);           /* x impar/par/larguras impares */
        gfx_fill(11, 40, 40, 20, G);
        gfx_rect(100, 10, 31, 21, W);
        gfx_line(0, 0, 239, 159, B);
        gfx_line(239, 0, 0, 159, Y);
        gfx_circle(180, 100, 30, W);
        gfx_fill_circle(60, 110, 20, R);
        gfx_hline(-20, 5, 300, G);              /* recorte */
        gfx_vline(5, -10, 500, G);
        gfx_text(8, 80, "GBA Draw 0123 @#%", W);
        gfx_text_bg(9, 92, "bg text", Y, B);
        gfx_int(120, 140, -12345, W);
        gfx_hex(120, 150, 0xBEEF, 4, W);
        gfx_text(236, 156, "clip", W);            /* parcialmente fora */
        static u16 img3[8 * 8]; static u8 img4[8 * 8];
        for (int i = 0; i < 64; i++) { img3[i] = (i % 9 == 0) ? 0 : RGB15(i % 32, 10, 31 - i % 32); img4[i] = (i % 9 == 0) ? 0 : 1 + i % 7; }
        gfx_blit(m == 3 ? (void *)img3 : (void *)img4, 200, 20, 8, 8, 0);
        gfx_blit(m == 3 ? (void *)img3 : (void *)img4, 233, 20, 8, 8, -1);   /* cortado a direita */
        gfx_blit(m == 3 ? (void *)img3 : (void *)img4, -4, 150, 8, 8, -1);
        FILE *f = fopen("vram.bin", "wb"); fwrite(gfx_buf, 1, 0x9600 * (m == 3 ? 2 : 1) / 1, f); fclose(f);
        return 0;
    }
    if (mode[0] == 's') {
        log_f = fopen("snd.log", "w"); gba_host_vsync_hook = hook;
        gba_init(); snd_play(test_song);
        for (int i = 0; i < 400 && snd_playing(); i++) vsync();
        fprintf(log_f, "playing=%d\n", snd_playing());
        fclose(log_f); return 0;
    }
    if (mode[0] == 'l') {
        static u8 out[4096]; lz77_decompress(test_lz, out);
        fwrite(out, 1, test_lz_size, stdout); return 0;
    }
    if (mode[0] == 'm') {
        char b1[12], b2[12], b3[12]; printf("%s %s %s %u %d\n", int_to_str(0, b1), int_to_str(-70000, b2), int_to_str(2147483647, b3), isqrt32(1000000), (int)(fix_mul(FIX(1.5), FIX(2.0)) == FIX(3)));
        printf("%d %d\n", fsin(64), fcos(0));
        return 0;
    }
    return 1;
}
