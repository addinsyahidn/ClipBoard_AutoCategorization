"""
Segmented Clipboard Manager
============================
- Monitoring clipboard otomatis (polling setiap 0.5 detik, tanpa perlu Ctrl+C hook)
- Setiap teks baru otomatis dikategorikan & disimpan ke clipboard_data.json
- GUI pygame untuk melihat riwayat & kirim ke WhatsApp
- Data persisten antar sesi (tersimpan di file JSON)
"""

import pygame
import sys
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

# ── pyperclip (clipboard access) ────────────────────────────────────────────
try:
    import pyperclip
    CLIPBOARD_OK = True
except ImportError:
    CLIPBOARD_OK = False

# ── pywhatkit (opsional, untuk kirim WA) ────────────────────────────────────
try:
    import pywhatkit as kit
    PYWHATKIT_OK = True
except ImportError:
    PYWHATKIT_OK = False

# ═══════════════════════════════════════════════════════════════════════════════
# KONFIGURASI
# ═══════════════════════════════════════════════════════════════════════════════
DATA_FILE     = Path("clipboard_data.json")
NOMOR_TARGET  = "+6285262880669"   # ← ganti nomor WA tujuan
MAX_SLOT      = 10                 # maksimum entri per kategori
POLL_INTERVAL = 0.5               # detik antar cek clipboard

# ── Kategori & kata kunci ────────────────────────────────────────────────────
KATEGORI_RULES = {
    "💻 CODING/TEKNIS": [
        "def ", "import ", "print(", "sql", "api", "code", "function",
        "class ", "return ", "http", "json", "html", "css", "git",
        "error", "debug", "variable", "array", "list", "dict", "int(",
        "str(", "for ", "while ", "if ", "else:", "try:", "except",
    ],
    "📚 TUGAS/KULIAH": [
        "jurnal", "tugas", "kuliah", "dosen", "makalah", "os", "sistem",
        "operasi", "algoritma", "struktur data", "laporan", "bab ",
        "abstrak", "referensi", "kesimpulan", "pendahuluan", "analisis",
        "penelitian", "skripsi", "semester", "ujian", "soal",
    ],
    "🌐 LINK/URL": [
        "http://", "https://", "www.", ".com", ".id", ".net", ".org",
        "youtube", "github", "google", "instagram", "twitter", "tiktok",
    ],
    "📱 NOMOR/KONTAK": [
        "+62", "08", "081", "082", "083", "085", "089",
        "telp", "wa:", "whatsapp", "phone", "no hp",
    ],
    "🛒 UMUM/BELANJA": [],  # fallback, semua yang tidak cocok
}

# ═══════════════════════════════════════════════════════════════════════════════
# WARNA & FONT
# ═══════════════════════════════════════════════════════════════════════════════
W, H = 1000, 660

C = {
    "bg":          (15, 15, 22),
    "panel":       (25, 25, 38),
    "card":        (32, 32, 48),
    "card_hover":  (42, 42, 62),
    "border":      (55, 55, 80),
    "accent":      (0, 210, 160),
    "accent2":     (100, 120, 255),
    "text":        (230, 230, 240),
    "text_dim":    (120, 120, 140),
    "green":       (0, 200, 100),
    "red":         (255, 80, 80),
    "yellow":      (255, 200, 60),
    "btn_wa":      (37, 211, 102),   # hijau WA
    "btn_wa_h":    (50, 235, 120),
    "btn_del":     (200, 60, 60),
    "btn_del_h":   (230, 80, 80),
}

# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE (JSON)
# ═══════════════════════════════════════════════════════════════════════════════
def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {k: [] for k in KATEGORI_RULES}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# KATEGORISASI
# ═══════════════════════════════════════════════════════════════════════════════
def kategorikan(teks: str) -> str:
    teks_lower = teks.lower()
    for nama_kategori, keywords in KATEGORI_RULES.items():
        if any(kw in teks_lower for kw in keywords):
            return nama_kategori
    return "🛒 UMUM/BELANJA"

# ═══════════════════════════════════════════════════════════════════════════════
# APP STATE
# ═══════════════════════════════════════════════════════════════════════════════
class ClipboardApp:
    def __init__(self):
        self.data         = load_data()
        self.log          = "✅ Sistem aktif — clipboard dipantau otomatis."
        self.log_color    = C["accent"]
        self.last_clip    = ""
        self.selected_tab = list(KATEGORI_RULES.keys())[0]
        self.scroll_y     = 0
        self.monitoring   = True
        self._lock        = threading.Lock()

    # ── clipboard polling ────────────────────────────────────────────────────
    def start_monitor(self):
        def loop():
            while self.monitoring:
                try:
                    clip = pyperclip.paste()
                    if clip and clip != self.last_clip and len(clip.strip()) > 0:
                        self.last_clip = clip
                        self.tambah(clip.strip())
                except Exception:
                    pass
                time.sleep(POLL_INTERVAL)
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    # ── tambah entri ─────────────────────────────────────────────────────────
    def tambah(self, teks: str):
        kategori = kategorikan(teks)
        with self._lock:
            lst = self.data.setdefault(kategori, [])
            # hapus duplikat lama
            lst[:] = [e for e in lst if e["teks"] != teks]
            # evict jika penuh
            if len(lst) >= MAX_SLOT:
                lst.pop(0)
            lst.append({
                "teks":   teks,
                "waktu":  datetime.now().strftime("%d/%m %H:%M"),
                "panjang": len(teks),
            })
            save_data(self.data)
            self.log = f"📥 Disimpan → {kategori}  |  \"{teks[:40]}{'...' if len(teks)>40 else ''}\""
            self.log_color = C["accent"]

    # ── hapus entri ──────────────────────────────────────────────────────────
    def hapus(self, kategori: str, idx: int):
        with self._lock:
            lst = self.data.get(kategori, [])
            if 0 <= idx < len(lst):
                lst.pop(idx)
                save_data(self.data)
                self.log = f"🗑️ Dihapus dari {kategori}"
                self.log_color = C["yellow"]

    # ── kirim WA ─────────────────────────────────────────────────────────────
    def kirim_wa(self, kategori: str, idx: int):
        if not PYWHATKIT_OK:
            self.log = "❌ pywhatkit tidak terinstall. Jalankan: pip install pywhatkit"
            self.log_color = C["red"]
            return
        lst = self.data.get(kategori, [])
        if not (0 <= idx < len(lst)):
            return
        teks = lst[idx]["teks"]
        def send():
            try:
                self.log = f"🚀 Mengirim ke {NOMOR_TARGET}..."
                self.log_color = C["yellow"]
                kit.sendwhatmsg_instantly(NOMOR_TARGET, teks, wait_time=15, tab_close=True)
                self.log = "🟢 Pesan berhasil dikirim!"
                self.log_color = C["green"]
            except Exception as e:
                self.log = f"❌ Gagal kirim: {str(e)[:60]}"
                self.log_color = C["red"]
        threading.Thread(target=send, daemon=True).start()

    # ── jumlah total entri ───────────────────────────────────────────────────
    def total(self):
        return sum(len(v) for v in self.data.values())


# ═══════════════════════════════════════════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════════════════════════════════════════
def draw_rounded_rect(surf, color, rect, r=8, border=0, border_color=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, width=border, border_radius=r)

def truncate(s, n):
    return s[:n] + "…" if len(s) > n else s

class GUI:
    def __init__(self, app: ClipboardApp):
        pygame.init()
        pygame.font.init()
        self.app    = app
        self.surf   = pygame.display.set_mode((W, H))
        pygame.display.set_caption("🧠 Segmented Clipboard Manager")

        self.fnt_title  = pygame.font.SysFont("Segoe UI", 22, bold=True)
        self.fnt_sub    = pygame.font.SysFont("Segoe UI", 15, bold=True)
        self.fnt_reg    = pygame.font.SysFont("Segoe UI", 13)
        self.fnt_small  = pygame.font.SysFont("Segoe UI", 11)
        self.fnt_mono   = pygame.font.SysFont("Courier New", 12)

        self.tab_rects   : list[dict] = []
        self.card_actions: list[dict] = []  # {rect, action}

    # ── render frame ─────────────────────────────────────────────────────────
    def render(self):
        surf = self.surf
        surf.fill(C["bg"])
        self.tab_rects    = []
        self.card_actions = []
        mouse = pygame.mouse.get_pos()

        # ── Header ──────────────────────────────────────────────────────────
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 56))
        pygame.draw.line(surf, C["border"], (0, 56), (W, 56), 1)

        ttl = self.fnt_title.render("🧠 Segmented Clipboard Manager", True, C["accent"])
        surf.blit(ttl, (20, 14))

        total_txt = self.fnt_reg.render(
            f"Total tersimpan: {self.app.total()} entri  |  "
            f"{'🟢 Monitoring aktif' if CLIPBOARD_OK else '🔴 pyperclip tidak ada'}",
            True, C["text_dim"]
        )
        surf.blit(total_txt, (W - total_txt.get_width() - 20, 18))

        # ── Tabs ─────────────────────────────────────────────────────────────
        tx = 20
        for nama in KATEGORI_RULES:
            count = len(self.app.data.get(nama, []))
            label = f"{nama}  ({count})"
            tw    = self.fnt_sub.size(label)[0] + 24
            rect  = pygame.Rect(tx, 66, tw, 34)
            aktif = nama == self.app.selected_tab
            pygame.draw.rect(surf, C["accent"] if aktif else C["card"],
                             rect, border_radius=6)
            if not aktif:
                pygame.draw.rect(surf, C["border"], rect, width=1, border_radius=6)
            surf.blit(self.fnt_sub.render(label, True,
                      C["bg"] if aktif else C["text_dim"]), (tx + 12, 74))
            self.tab_rects.append({"rect": rect, "nama": nama})
            tx += tw + 8

        # ── Content area ─────────────────────────────────────────────────────
        content_top = 110
        lst = self.app.data.get(self.app.selected_tab, [])

        if not lst:
            empty = self.fnt_sub.render(
                "Belum ada data di kategori ini. Coba copy sesuatu!", True, C["text_dim"])
            surf.blit(empty, (W // 2 - empty.get_width() // 2, H // 2 - 20))
        else:
            # scroll clip
            max_scroll = max(0, len(lst) * 84 - (H - content_top - 80))
            self.app.scroll_y = max(0, min(self.app.scroll_y, max_scroll))

            clip_surf = pygame.Surface((W, H - content_top - 70), pygame.SRCALPHA)
            clip_surf.fill((0, 0, 0, 0))

            for i, entri in enumerate(reversed(lst)):  # terbaru di atas
                real_idx = len(lst) - 1 - i
                y = i * 84 - self.app.scroll_y
                if y > H - content_top - 70:
                    break
                if y < -84:
                    continue

                card = pygame.Rect(10, y + 4, W - 20, 76)
                hover_card = card.collidepoint(
                    mouse[0], mouse[1] - content_top)
                draw_rounded_rect(clip_surf,
                    C["card_hover"] if hover_card else C["card"], card, r=8,
                    border=1, border_color=C["accent"] if hover_card else C["border"])

                # nomor urut
                n_surf = self.fnt_small.render(f"#{real_idx+1}", True, C["text_dim"])
                clip_surf.blit(n_surf, (24, y + 10))

                # teks utama
                teks_surf = self.fnt_mono.render(
                    truncate(entri["teks"], 90), True, C["text"])
                clip_surf.blit(teks_surf, (60, y + 12))

                # metadata
                meta = f"⏱ {entri['waktu']}  ·  {entri['panjang']} karakter"
                meta_surf = self.fnt_small.render(meta, True, C["text_dim"])
                clip_surf.blit(meta_surf, (60, y + 34))

                # tombol WA
                btn_wa = pygame.Rect(W - 200, y + 18, 90, 26)
                hw = btn_wa.collidepoint(mouse[0], mouse[1] - content_top)
                draw_rounded_rect(clip_surf,
                    C["btn_wa_h"] if hw else C["btn_wa"], btn_wa, r=5)
                wa_t = self.fnt_small.render("📤 Kirim WA", True, (10, 10, 10))
                clip_surf.blit(wa_t, (btn_wa.x + 8, btn_wa.y + 6))

                # tombol Hapus
                btn_del = pygame.Rect(W - 100, y + 18, 76, 26)
                hd = btn_del.collidepoint(mouse[0], mouse[1] - content_top)
                draw_rounded_rect(clip_surf,
                    C["btn_del_h"] if hd else C["btn_del"], btn_del, r=5)
                del_t = self.fnt_small.render("🗑 Hapus", True, C["text"])
                clip_surf.blit(del_t, (btn_del.x + 10, btn_del.y + 6))

                # daftarkan ke card_actions (koordinat absolut)
                self.card_actions.append({
                    "rect_wa":  pygame.Rect(btn_wa.x, btn_wa.y + content_top, btn_wa.w, btn_wa.h),
                    "rect_del": pygame.Rect(btn_del.x, btn_del.y + content_top, btn_del.w, btn_del.h),
                    "kategori": self.app.selected_tab,
                    "idx":      real_idx,
                })

            surf.blit(clip_surf, (0, content_top))

        # ── Status log bar ────────────────────────────────────────────────────
        log_rect = pygame.Rect(0, H - 60, W, 60)
        pygame.draw.rect(surf, C["panel"], log_rect)
        pygame.draw.line(surf, C["border"], (0, H - 60), (W, H - 60), 1)
        log_surf = self.fnt_reg.render(
            f"Log: {self.app.log}", True, self.app.log_color)
        surf.blit(log_surf, (20, H - 40))

        hint = self.fnt_small.render(
            "Scroll: mouse wheel  ·  Clipboard dipantau otomatis (tanpa perlu tekan Ctrl+C di sini)",
            True, C["text_dim"])
        surf.blit(hint, (20, H - 20))

        pygame.display.flip()

    # ── event handling ────────────────────────────────────────────────────────
    def handle(self, event):
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.MOUSEWHEEL:
            self.app.scroll_y -= event.y * 30

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos

            # tab klik
            for t in self.tab_rects:
                if t["rect"].collidepoint(pos):
                    self.app.selected_tab = t["nama"]
                    self.app.scroll_y = 0

            # tombol kartu
            for act in self.card_actions:
                if act["rect_wa"].collidepoint(pos):
                    self.app.kirim_wa(act["kategori"], act["idx"])
                if act["rect_del"].collidepoint(pos):
                    self.app.hapus(act["kategori"], act["idx"])
                    self.app.scroll_y = max(0, self.app.scroll_y - 84)

        return True

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    if not CLIPBOARD_OK:
        print("⚠️  pyperclip tidak ditemukan. Install dengan: pip install pyperclip")
        print("   Monitoring clipboard tidak aktif, tapi GUI tetap bisa digunakan.")

    app = ClipboardApp()
    if CLIPBOARD_OK:
        app.start_monitor()

    gui   = GUI(app)
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            running = gui.handle(event)
        gui.render()
        clock.tick(30)

    app.monitoring = False
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
