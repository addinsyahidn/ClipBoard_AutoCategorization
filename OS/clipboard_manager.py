"""
Segmented Clipboard Manager
============================
- Monitoring clipboard otomatis (polling setiap 0.5 detik)
- Setiap teks baru otomatis dikategorikan & disimpan ke clipboard_data.json
- GUI pygame dengan mode Normal (1000x660) dan PiP / always-on-top (320x500)
- Data persisten antar sesi (tersimpan di file JSON)
"""

import pygame
import sys
import json
import os
import re
import threading
import time
import platform
import subprocess
from datetime import datetime
from pathlib import Path

# ── pyperclip ───────────────────────────────────────────────────────────────
try:
    import pyperclip
    CLIPBOARD_OK = True
except ImportError:
    CLIPBOARD_OK = False

# ── pywhatkit ───────────────────────────────────────────────────────────────
try:
    import pywhatkit as kit
    PYWHATKIT_OK = True
except ImportError:
    PYWHATKIT_OK = False

# ═══════════════════════════════════════════════════════════════════════════════
# KONFIGURASI
# ═══════════════════════════════════════════════════════════════════════════════
DATA_FILE     = Path("clipboard_data.json")
NOMOR_TARGET  = "+62xxxxxxxxxxxx"   # ← ganti nomor WA tujuan
MAX_SLOT      = 10
POLL_INTERVAL = 0.5

# Ukuran window
W_NORMAL, H_NORMAL = 1000, 660
W_PIP,    H_PIP    = 320,  500

# ── Kategori & kata kunci ────────────────────────────────────────────────────
KATEGORI_RULES = {
    "💻 CODING/TEKNIS": {
        "exact": ["def ", "import ", "print(", "int(", "str(", "len(",
                  "else:", "try:", "except:", "class ", "return ", "while "],
        "word":  ["sql", "api", "html", "css", "git", "json",
                  "debug", "variable", "array", "dict", "function", "error", "code"],
    },
    "📚 TUGAS/KULIAH": {
        "exact": [],
        "word":  ["jurnal", "tugas", "kuliah", "dosen", "makalah",
                  "sistem operasi", "algoritma", "struktur data", "laporan",
                  "abstrak", "referensi", "kesimpulan", "pendahuluan",
                  "analisis", "penelitian", "skripsi", "semester", "ujian", "soal"],
    },
    "🌐 LINK/URL": {
        "exact": ["http://", "https://", "www."],
        "word":  ["youtube", "github", "google", "instagram", "twitter", "tiktok"],
    },
    "📱 NOMOR/KONTAK": {
        "exact": ["+62", "wa:", "no hp"],
        "word":  ["telp", "whatsapp", "phone"],
    },
    "🛒 UMUM/BELANJA": {"exact": [], "word": []},
}

# ── Warna ────────────────────────────────────────────────────────────────────
C = {
    "bg":         (15, 15, 22),
    "panel":      (25, 25, 38),
    "card":       (32, 32, 48),
    "card_hover": (42, 42, 62),
    "border":     (55, 55, 80),
    "accent":     (0, 210, 160),
    "accent2":    (100, 120, 255),
    "text":       (230, 230, 240),
    "text_dim":   (120, 120, 140),
    "green":      (0, 200, 100),
    "red":        (255, 80, 80),
    "yellow":     (255, 200, 60),
    "btn_wa":     (37, 211, 102),
    "btn_wa_h":   (50, 235, 120),
    "btn_del":    (200, 60, 60),
    "btn_del_h":  (230, 80, 80),
    "pip_btn":    (60, 60, 90),
    "pip_btn_h":  (80, 80, 120),
    "pip_active": (0, 180, 130),
}

# ═══════════════════════════════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════════════════════════════
def load_data() -> dict:
    base = {k: [] for k in KATEGORI_RULES}
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k in base:
                if k in saved and isinstance(saved[k], list):
                    base[k] = saved[k]
        except Exception:
            pass
    return base

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# KATEGORISASI
# ═══════════════════════════════════════════════════════════════════════════════
def kategorikan(teks: str) -> str:
    t = teks.lower()
    for nama, rules in KATEGORI_RULES.items():
        if any(kw in t for kw in rules.get("exact", [])):
            return nama
        for kw in rules.get("word", []):
            if re.search(r'\b' + re.escape(kw) + r'\b', t):
                return nama
    return "🛒 UMUM/BELANJA"

# ═══════════════════════════════════════════════════════════════════════════════
# ALWAYS-ON-TOP helper (Windows / macOS / Linux)
# ═══════════════════════════════════════════════════════════════════════════════
def set_always_on_top(enabled: bool):
    """Coba set always-on-top via OS API. Tidak crash kalau tidak didukung."""
    try:
        plat = platform.system()
        if plat == "Windows":
            import ctypes
            hwnd = pygame.display.get_wm_info()["window"]
            HWND_TOPMOST    = -1
            HWND_NOTOPMOST  = -2
            SWP_FLAGS       = 0x0001 | 0x0002  # NOSIZE | NOMOVE
            target = HWND_TOPMOST if enabled else HWND_NOTOPMOST
            ctypes.windll.user32.SetWindowPos(hwnd, target, 0, 0, 0, 0, SWP_FLAGS)
        elif plat == "Darwin":
            # macOS: pakai wmctrl tidak tersedia, tapi SDL hint bisa diset sebelum init
            pass  # macOS support lewat SDL_VIDEO_WINDOW_ALWAYS_ON_TOP env var
        elif plat == "Linux":
            # Linux: gunakan xdotool / wmctrl jika tersedia
            wm_info = pygame.display.get_wm_info()
            wid = wm_info.get("window")
            if wid:
                prop = "add" if enabled else "remove"
                subprocess.Popen(
                    ["wmctrl", "-i", "-r", hex(wid), "-b", f"{prop},above"],
                    stderr=subprocess.DEVNULL
                )
    except Exception:
        pass  # Silent fail — PiP mode tetap jalan tanpa always-on-top

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

    def start_monitor(self):
        def loop():
            while self.monitoring:
                try:
                    clip = pyperclip.paste()
                    if clip and clip != self.last_clip and clip.strip():
                        self.last_clip = clip
                        self.tambah(clip.strip())
                except Exception:
                    pass
                time.sleep(POLL_INTERVAL)
        threading.Thread(target=loop, daemon=True).start()

    def tambah(self, teks: str):
        kategori = kategorikan(teks)
        with self._lock:
            lst = self.data.setdefault(kategori, [])
            lst[:] = [e for e in lst if e["teks"] != teks]
            if len(lst) >= MAX_SLOT:
                evicted = lst.pop(0)
                print(f"⚠️  Evict: {evicted['teks'][:50]}")
            lst.append({
                "teks":    teks,
                "waktu":   datetime.now().strftime("%d/%m %H:%M"),
                "panjang": len(teks),
            })
            save_data(self.data)
            self.log = "📥 " + kategori + "  |  \"" + teks[:40] + ("..." if len(teks) > 40 else "") + "\""
            self.log_color = C["accent"]

    def hapus(self, kategori: str, idx: int):
        with self._lock:
            lst = self.data.get(kategori, [])
            if 0 <= idx < len(lst):
                lst.pop(idx)
                save_data(self.data)
                self.log = "🗑️ Dihapus dari " + kategori
                self.log_color = C["yellow"]

    def salin(self, kategori: str, idx: int):
        if not CLIPBOARD_OK:
            self.log = "❌ pyperclip tidak tersedia"
            self.log_color = C["red"]
            return
        lst = self.data.get(kategori, [])
        if not (0 <= idx < len(lst)):
            return
        teks = lst[idx]["teks"]
        try:
            pyperclip.copy(teks)
            self.log = "📋 Disalin: \"" + teks[:50] + ("..." if len(teks) > 50 else "") + "\""
            self.log_color = C["accent2"]
        except Exception as e:
            self.log = "❌ Gagal salin: " + str(e)[:60]
            self.log_color = C["red"]

    def kirim_wa(self, kategori: str, idx: int):
        if not PYWHATKIT_OK:
            self.log = "❌ pywhatkit tidak ada. pip install pywhatkit"
            self.log_color = C["red"]
            return
        lst = self.data.get(kategori, [])
        if not (0 <= idx < len(lst)):
            return
        teks = lst[idx]["teks"]
        def send():
            try:
                self.log = "🚀 Mengirim ke " + NOMOR_TARGET + "..."
                self.log_color = C["yellow"]
                kit.sendwhatmsg_instantly(NOMOR_TARGET, teks, wait_time=15, tab_close=True)
                self.log = "🟢 Pesan berhasil dikirim!"
                self.log_color = C["green"]
            except Exception as e:
                self.log = "❌ Gagal kirim: " + str(e)[:60]
                self.log_color = C["red"]
        threading.Thread(target=send, daemon=True).start()

    def total(self):
        return sum(len(v) for v in self.data.values())

    def current_list(self):
        return self.data.get(self.selected_tab, [])

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS GAMBAR
# ═══════════════════════════════════════════════════════════════════════════════
def draw_rounded_rect(surf, color, rect, r=8, border=0, border_color=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border and border_color:
        pygame.draw.rect(surf, border_color, rect, width=border, border_radius=r)

def truncate(s, n):
    return s[:n] + "..." if len(s) > n else s

# ═══════════════════════════════════════════════════════════════════════════════
# GUI — MODE NORMAL
# ═══════════════════════════════════════════════════════════════════════════════
class GUINormal:
    def __init__(self, app: ClipboardApp, surf):
        self.app          = app
        self.surf         = surf
        self.tab_rects    = []
        self.card_actions = []
        self.btn_pip_rect = None

        self.fnt_title = pygame.font.SysFont("Segoe UI", 22, bold=True)
        self.fnt_sub   = pygame.font.SysFont("Segoe UI", 15, bold=True)
        self.fnt_reg   = pygame.font.SysFont("Segoe UI", 13)
        self.fnt_small = pygame.font.SysFont("Segoe UI", 11)
        self.fnt_mono  = pygame.font.SysFont("Courier New", 12)

    def render(self):
        surf  = self.surf
        W, H  = surf.get_size()
        mouse = pygame.mouse.get_pos()
        surf.fill(C["bg"])
        self.tab_rects    = []
        self.card_actions = []

        # ── Header ──────────────────────────────────────────────────────────
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 56))
        pygame.draw.line(surf, C["border"], (0, 56), (W, 56), 1)

        ttl = self.fnt_title.render("🧠 Clipboard Manager", True, C["accent"])
        surf.blit(ttl, (20, 14))

        # Tombol PiP di kanan header
        pip_lbl = self.fnt_small.render("[ ] PiP", True, C["text_dim"])
        pw = pip_lbl.get_width() + 20
        pip_rect = pygame.Rect(W - pw - 12, 14, pw, 28)
        hp = pip_rect.collidepoint(mouse)
        draw_rounded_rect(surf, C["pip_btn_h"] if hp else C["pip_btn"], pip_rect, r=6,
                          border=1, border_color=C["accent2"])
        surf.blit(self.fnt_small.render("⊞ PiP Mode", True, C["accent2"] if hp else C["text_dim"]),
                  (pip_rect.x + 8, pip_rect.y + 7))
        self.btn_pip_rect = pip_rect

        total_txt = self.fnt_reg.render(
            f"Total: {self.app.total()} entri  |  "
            f"{'🟢 Monitoring' if CLIPBOARD_OK else '🔴 No pyperclip'}",
            True, C["text_dim"])
        surf.blit(total_txt, (W - total_txt.get_width() - pip_rect.width - 28, 18))

        # ── Tabs ─────────────────────────────────────────────────────────────
        tx = 20
        for nama in KATEGORI_RULES:
            count = len(self.app.data.get(nama, []))
            label = f"{nama}  ({count})"
            tw    = self.fnt_sub.size(label)[0] + 24
            rect  = pygame.Rect(tx, 66, tw, 34)
            aktif = nama == self.app.selected_tab
            draw_rounded_rect(surf, C["accent"] if aktif else C["card"], rect, r=6,
                              border=0 if aktif else 1,
                              border_color=C["border"])
            surf.blit(self.fnt_sub.render(label, True,
                      C["bg"] if aktif else C["text_dim"]), (tx + 12, 74))
            self.tab_rects.append({"rect": rect, "nama": nama})
            tx += tw + 8

        # ── Cards ────────────────────────────────────────────────────────────
        content_top = 110
        lst = self.app.current_list()

        if not lst:
            em = self.fnt_sub.render("Belum ada data. Coba copy sesuatu!", True, C["text_dim"])
            surf.blit(em, (W // 2 - em.get_width() // 2, H // 2 - 20))
        else:
            max_scroll = max(0, len(lst) * 84 - (H - content_top - 70))
            self.app.scroll_y = max(0, min(self.app.scroll_y, max_scroll))

            clip_h = H - content_top - 70
            clip_surf = pygame.Surface((W, clip_h), pygame.SRCALPHA)
            clip_surf.fill((0, 0, 0, 0))

            for i, entri in enumerate(reversed(lst)):
                real_idx = len(lst) - 1 - i
                y = i * 84 - self.app.scroll_y
                if y > clip_h: break
                if y < -84:   continue

                card = pygame.Rect(10, y + 4, W - 20, 76)
                hov  = card.collidepoint(mouse[0], mouse[1] - content_top)
                draw_rounded_rect(clip_surf,
                    C["card_hover"] if hov else C["card"], card, r=8,
                    border=1, border_color=C["accent"] if hov else C["border"])

                clip_surf.blit(self.fnt_small.render(f"#{real_idx+1}", True, C["text_dim"]), (24, y + 10))
                clip_surf.blit(self.fnt_mono.render(truncate(entri["teks"], 90), True, C["text"]), (60, y + 12))
                meta = f"⏱ {entri['waktu']}  ·  {entri['panjang']} karakter"
                clip_surf.blit(self.fnt_small.render(meta, True, C["text_dim"]), (60, y + 34))

                # Tombol
                btn_copy = pygame.Rect(W - 305, y + 20, 80, 24)
                btn_wa   = pygame.Rect(W - 215, y + 20, 88, 24)
                btn_del  = pygame.Rect(W - 118, y + 20, 76, 24)

                hc = btn_copy.collidepoint(mouse[0], mouse[1] - content_top)
                hw = btn_wa.collidepoint(mouse[0], mouse[1] - content_top)
                hd = btn_del.collidepoint(mouse[0], mouse[1] - content_top)

                draw_rounded_rect(clip_surf, C["accent2"] if hc else (55, 65, 150), btn_copy, r=5)
                draw_rounded_rect(clip_surf, C["btn_wa_h"] if hw else C["btn_wa"],   btn_wa,   r=5)
                draw_rounded_rect(clip_surf, C["btn_del_h"] if hd else C["btn_del"], btn_del,  r=5)

                clip_surf.blit(self.fnt_small.render("📋 Salin",    True, C["text"]),        (btn_copy.x + 8,  btn_copy.y + 5))
                clip_surf.blit(self.fnt_small.render("📤 Kirim WA", True, (10, 10, 10)),     (btn_wa.x + 6,    btn_wa.y + 5))
                clip_surf.blit(self.fnt_small.render("🗑 Hapus",    True, C["text"]),        (btn_del.x + 10,  btn_del.y + 5))

                self.card_actions.append({
                    "rect_copy": pygame.Rect(btn_copy.x, btn_copy.y + content_top, btn_copy.w, btn_copy.h),
                    "rect_wa":   pygame.Rect(btn_wa.x,   btn_wa.y   + content_top, btn_wa.w,   btn_wa.h),
                    "rect_del":  pygame.Rect(btn_del.x,  btn_del.y  + content_top, btn_del.w,  btn_del.h),
                    "kategori":  self.app.selected_tab,
                    "idx":       real_idx,
                })

            surf.blit(clip_surf, (0, content_top))

        # ── Status bar ───────────────────────────────────────────────────────
        pygame.draw.rect(surf, C["panel"], (0, H - 60, W, 60))
        pygame.draw.line(surf, C["border"], (0, H - 60), (W, H - 60), 1)
        surf.blit(self.fnt_reg.render("Log: " + self.app.log, True, self.app.log_color), (20, H - 42))
        surf.blit(self.fnt_small.render(
            "Scroll: mouse wheel  ·  Klik ⊞ PiP untuk mode mini always-on-top",
            True, C["text_dim"]), (20, H - 20))

        pygame.display.flip()

    def handle(self, event):
        if event.type == pygame.QUIT:
            return False, None

        if event.type == pygame.MOUSEWHEEL:
            self.app.scroll_y -= event.y * 30

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.btn_pip_rect and self.btn_pip_rect.collidepoint(pos):
                return True, "pip"
            for t in self.tab_rects:
                if t["rect"].collidepoint(pos):
                    self.app.selected_tab = t["nama"]
                    self.app.scroll_y = 0
            for act in self.card_actions:
                if act["rect_copy"].collidepoint(pos):
                    self.app.salin(act["kategori"], act["idx"])
                if act["rect_wa"].collidepoint(pos):
                    self.app.kirim_wa(act["kategori"], act["idx"])
                if act["rect_del"].collidepoint(pos):
                    self.app.hapus(act["kategori"], act["idx"])
                    self.app.scroll_y = max(0, self.app.scroll_y - 84)

        return True, None

# ═══════════════════════════════════════════════════════════════════════════════
# GUI — MODE PiP (mini, always-on-top)
# ═══════════════════════════════════════════════════════════════════════════════
class GUIPip:
    """
    Window kecil 320×500 always-on-top.
    Layout:
      - Header tipis (judul + tombol Exit PiP)
      - Tab selector (scroll horizontal, icons only di mode sempit)
      - Daftar entri compact (1 baris per item)
      - Tap entri → salin otomatis ke clipboard
      - Tombol hapus kecil di kanan
    """
    def __init__(self, app: ClipboardApp, surf):
        self.app          = app
        self.surf         = surf
        self.card_actions = []
        self.tab_rects    = []
        self.btn_exit_rect= None
        self.scroll_y     = 0

        self.fnt_head  = pygame.font.SysFont("Segoe UI", 13, bold=True)
        self.fnt_item  = pygame.font.SysFont("Segoe UI", 12)
        self.fnt_small = pygame.font.SysFont("Segoe UI", 10)
        self.fnt_tab   = pygame.font.SysFont("Segoe UI", 11, bold=True)

    def render(self):
        surf  = self.surf
        W, H  = surf.get_size()   # 320 × 500
        mouse = pygame.mouse.get_pos()
        surf.fill(C["bg"])
        self.card_actions = []
        self.tab_rects    = []

        # ── Header (30px) ────────────────────────────────────────────────────
        pygame.draw.rect(surf, C["panel"], (0, 0, W, 30))
        pygame.draw.line(surf, C["pip_active"], (0, 30), (W, 30), 2)

        surf.blit(self.fnt_head.render("🧠 Clipboard  [PiP]", True, C["pip_active"]), (8, 7))

        # Tombol Exit PiP
        exit_r = pygame.Rect(W - 72, 4, 66, 22)
        he = exit_r.collidepoint(mouse)
        draw_rounded_rect(surf, (80, 40, 40) if he else (55, 30, 30), exit_r, r=5,
                          border=1, border_color=C["red"])
        surf.blit(self.fnt_small.render("✕ Exit PiP", True, C["red"]), (exit_r.x + 6, exit_r.y + 5))
        self.btn_exit_rect = exit_r

        # ── Tab bar (28px) ───────────────────────────────────────────────────
        tab_y = 34
        emoji_map = {
            "💻 CODING/TEKNIS":  "💻",
            "📚 TUGAS/KULIAH":   "📚",
            "🌐 LINK/URL":       "🌐",
            "📱 NOMOR/KONTAK":  "📱",
            "🛒 UMUM/BELANJA":  "🛒",
        }
        tab_w = W // len(KATEGORI_RULES)
        for i, nama in enumerate(KATEGORI_RULES):
            count = len(self.app.data.get(nama, []))
            aktif = nama == self.app.selected_tab
            r = pygame.Rect(i * tab_w, tab_y, tab_w, 28)
            draw_rounded_rect(surf, C["pip_active"] if aktif else C["card"], r, r=0)
            if aktif:
                pygame.draw.line(surf, C["accent"], (r.x, r.bottom), (r.right, r.bottom), 2)
            lbl = emoji_map.get(nama, "?") + (f" {count}" if count else "")
            ls  = self.fnt_tab.render(lbl, True, C["bg"] if aktif else C["text_dim"])
            surf.blit(ls, (r.x + r.w // 2 - ls.get_width() // 2, r.y + 5))
            self.tab_rects.append({"rect": r, "nama": nama})

        # ── Items (compact, 1 baris tiap item = 36px) ────────────────────────
        content_top = tab_y + 28 + 4
        lst = self.app.current_list()

        if not lst:
            em = self.fnt_item.render("Belum ada — copy sesuatu!", True, C["text_dim"])
            surf.blit(em, (W // 2 - em.get_width() // 2, H // 2))
        else:
            row_h = 40
            max_scroll = max(0, len(lst) * row_h - (H - content_top - 28))
            self.scroll_y = max(0, min(self.scroll_y, max_scroll))
            clip_h = H - content_top - 28

            clip_surf = pygame.Surface((W, clip_h), pygame.SRCALPHA)
            clip_surf.fill((0, 0, 0, 0))

            for i, entri in enumerate(reversed(lst)):
                real_idx = len(lst) - 1 - i
                y = i * row_h - self.scroll_y
                if y > clip_h: break
                if y < -row_h: continue

                row = pygame.Rect(4, y + 2, W - 8, row_h - 4)
                hov = row.collidepoint(mouse[0], mouse[1] - content_top)
                draw_rounded_rect(clip_surf,
                    C["card_hover"] if hov else C["card"], row, r=6,
                    border=1, border_color=C["accent"] if hov else C["border"])

                # Teks + meta
                clip_surf.blit(
                    self.fnt_item.render(truncate(entri["teks"], 30), True, C["text"]),
                    (10, y + 6))
                clip_surf.blit(
                    self.fnt_small.render(entri["waktu"] + " · " + str(entri["panjang"]) + "ch",
                                          True, C["text_dim"]),
                    (10, y + 22))

                # Tombol hapus kecil
                btn_del = pygame.Rect(W - 32, y + 8, 24, 24)
                hd = btn_del.collidepoint(mouse[0], mouse[1] - content_top)
                draw_rounded_rect(clip_surf,
                    C["btn_del_h"] if hd else (80, 35, 35), btn_del, r=4)
                clip_surf.blit(self.fnt_small.render("✕", True, C["text"]),
                               (btn_del.x + 6, btn_del.y + 6))

                # Klik area utama (bukan tombol hapus) → salin
                click_area = pygame.Rect(row.x, row.y, row.w - 34, row.h)
                self.card_actions.append({
                    "rect_click": pygame.Rect(click_area.x, click_area.y + content_top,
                                              click_area.w, click_area.h),
                    "rect_del":   pygame.Rect(btn_del.x, btn_del.y + content_top,
                                              btn_del.w, btn_del.h),
                    "kategori":   self.app.selected_tab,
                    "idx":        real_idx,
                })

            surf.blit(clip_surf, (0, content_top))

        # ── Footer status (28px) ─────────────────────────────────────────────
        pygame.draw.rect(surf, C["panel"], (0, H - 28, W, 28))
        pygame.draw.line(surf, C["border"], (0, H - 28), (W, H - 28), 1)
        log_short = truncate(self.app.log, 38)
        surf.blit(self.fnt_small.render(log_short, True, self.app.log_color), (6, H - 18))

        pygame.display.flip()

    def handle(self, event):
        if event.type == pygame.QUIT:
            return False, None

        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y -= event.y * 20

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.btn_exit_rect and self.btn_exit_rect.collidepoint(pos):
                return True, "normal"
            for t in self.tab_rects:
                if t["rect"].collidepoint(pos):
                    self.app.selected_tab = t["nama"]
                    self.scroll_y = 0
            for act in self.card_actions:
                if act["rect_del"].collidepoint(pos):
                    self.app.hapus(act["kategori"], act["idx"])
                    self.scroll_y = max(0, self.scroll_y - 40)
                elif act["rect_click"].collidepoint(pos):
                    # klik item = salin otomatis
                    self.app.salin(act["kategori"], act["idx"])

        return True, None

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    if not CLIPBOARD_OK:
        print("⚠️  pyperclip tidak ditemukan. pip install pyperclip")

    # Set env var untuk macOS always-on-top via SDL sebelum pygame.init()
    os.environ.setdefault("SDL_VIDEO_WINDOW_ALWAYS_ON_TOP", "0")

    pygame.init()
    pygame.font.init()

    app = ClipboardApp()
    if CLIPBOARD_OK:
        app.start_monitor()

    # Mulai dalam mode Normal
    mode  = "normal"
    surf  = pygame.display.set_mode((W_NORMAL, H_NORMAL), pygame.RESIZABLE)
    pygame.display.set_caption("🧠 Segmented Clipboard Manager")

    gui_normal = GUINormal(app, surf)
    gui_pip    = None
    clock      = pygame.time.Clock()

    running = True
    while running:
        events = pygame.event.get()
        for event in events:
            if mode == "normal":
                ok, action = gui_normal.handle(event)
            else:
                ok, action = gui_pip.handle(event)

            if not ok:
                running = False
                break

            if action == "pip" and mode == "normal":
                # Beralih ke PiP
                mode = "pip"
                surf = pygame.display.set_mode((W_PIP, H_PIP))
                pygame.display.set_caption("Clipboard [PiP]")
                set_always_on_top(True)
                gui_pip = GUIPip(app, surf)

            elif action == "normal" and mode == "pip":
                # Kembali ke Normal
                mode = "normal"
                set_always_on_top(False)
                surf = pygame.display.set_mode((W_NORMAL, H_NORMAL), pygame.RESIZABLE)
                pygame.display.set_caption("🧠 Segmented Clipboard Manager")
                gui_normal = GUINormal(app, surf)

        if not running:
            break

        if mode == "normal":
            gui_normal.surf = surf
            gui_normal.render()
        else:
            gui_pip.surf = surf
            gui_pip.render()

        clock.tick(30)

    app.monitoring = False
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
