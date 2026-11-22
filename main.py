#!/usr/bin/env python3
"""makefun-news-20261122: the world news of Sunday 22 November 2026 on
one newspaper page, drawn at run time with pure Python stdlib.

Nothing here touches the network, the clock or a random source, so every
run paints the same 1024x1024 PNG byte for byte. It writes
$MAKEFUN_OUTPUT_DIR/entry.png (or --out DIR/entry.png).

Stories on the page, each first reported on 22 November 2026 (any
timezone) or on the night of 21 November and reported that morning:
  * LEAD - Iran fires missiles and drones at US positions in Bahrain:
    the IRGC claims two Patriot radars hit at Al-Riffa and Awali; Bahrain
    says a civilian industrial facility was hit and caught fire, with no
    casualties; Bahrain's air defences intercepted several attacks.
    (Xinhua / People's Daily, Al Jazeera, 21-22 Nov.)
  * NATO chief Mark Rutte visits Warsaw and vows the alliance will
    defend every inch of Polish territory, a day after two Russian
    missiles and a drone came down in Poland; the North Atlantic Council
    meets on Monday. (Reuters, 21 Nov.)
  * The EU and Indonesia sign the CEPA trade deal and an investment
    protection agreement in Brussels after ten years of talks; 98.5% of
    tariffs go, saving EU exporters about 650 million euro a year.
    (Reuters / European Commission, 21 Nov.)
  * COP31 in Antalya runs deep into overtime, deadlocked over fossil
    fuels: the draft drops every fossil-fuel mention and a $120bn
    adaptation-finance target; the EU says a good deal or no deal.
    (Reuters, 21 Nov.)
  * Cyclone Akvan fades to a low after crossing Odisha: heavy rain and
    flooding, more than 300,000 people evacuated, no deaths reported.
    (IMD via The Watchers / ITDC, 21 Nov.)
  * France seeks Security Council action after Myanmar rejects the ICJ
    ruling on the Rohingya. (Homevo, 22 Nov.)
Ticker: magnitude 6.8 quake in the Banda Sea near Timor-Leste (GFZ);
Hong Kong votes for 723 Election Committee seats; Bolsonaro in intensive
care; drones hit a Russian cargo ship in the Baltic; two killed in a
strike on Lviv.
"""

import argparse
import math
import os
import struct
import sys
import zlib

SIDE = 1024

# Newsprint palette: cream sheet, navy ink, crimson, teal, ochre, slate.
CREAM = (244, 238, 224)
SHEET = (255, 251, 240)
NAVY = (13, 32, 61)
CRIMSON = (178, 24, 24)
TEAL = (13, 110, 102)
OCHRE = (196, 128, 12)
SLATE = (98, 102, 108)
PAPERWHITE = (255, 255, 255)
SOOT = (22, 22, 22)
SKYBLUE = (168, 205, 235)
LEAF = (34, 139, 68)
MAROON = (120, 20, 44)

# ---------------------------------------------------------------------------
# 5x7 bitmap type. One glyph is a 14-character hex string: seven bytes,
# one byte per row, bit 4 the leftmost column and bit 0 the rightmost.
# Uppercase only: every string is upper-cased before it is drawn.
# ---------------------------------------------------------------------------
GLYPHS = {
    " ": "00000000000000",
    "!": "04040404040004",
    "$": "040f140e051e04",
    "%": "19190204081313",
    "&": "0c12140815120d",
    "'": "04040800000000",
    "(": "02040808080402",
    ")": "08040202020408",
    "+": "0004041f040400",
    ",": "000000000c0408",
    "-": "0000001f000000",
    ".": "00000000000c0c",
    "/": "01020204080810",
    "0": "0e11131519110e",
    "1": "040c040404040e",
    "2": "0e11010608101f",
    "3": "1f02040201110e",
    "4": "02060a121f0202",
    "5": "1f101e0101110e",
    "6": "0608101e11110e",
    "7": "1f010204080808",
    "8": "0e11110e11110e",
    "9": "0e11110f01020c",
    ":": "000c0c000c0c00",
    "?": "0e110106040004",
    "A": "0e11111f111111",
    "B": "1e11111e11111e",
    "C": "0e11101010110e",
    "D": "1e11111111111e",
    "E": "1f10101e10101f",
    "F": "1f10101e101010",
    "G": "0e11101711110f",
    "H": "1111111f111111",
    "I": "0e04040404040e",
    "J": "0702020202120c",
    "K": "11121418141211",
    "L": "1010101010101f",
    "M": "111b1515111111",
    "N": "11191513111111",
    "O": "0e11111111110e",
    "P": "1e11111e101010",
    "Q": "0e11111115120d",
    "R": "1e11111e141211",
    "S": "0f10100e01011e",
    "T": "1f040404040404",
    "U": "1111111111110e",
    "V": "11111111110a04",
    "W": "1111111515150a",
    "X": "11110a040a1111",
    "Y": "11110a04040404",
    "Z": "1f01020408101f",
    "\u2022": "0000000c0c0000",
}

ADVANCE = 6   # font units per glyph cell, including the gap column
ROWS = 7      # rows per glyph


def glyph_rows(ch):
    """The seven row bytes of a glyph, decoded from its hex string."""
    return bytes.fromhex(GLYPHS[ch])


def measure(text, scale):
    """Pixel width of a string at the given scale."""
    return max(0, len(text) * ADVANCE * scale - scale)


def wrap_words(text, scale, max_px):
    """Greedy word wrap; returns a list of upper-cased lines."""
    out = []
    line = ""
    for word in text.upper().split(" "):
        trial = word if line == "" else line + " " + word
        if measure(trial, scale) <= max_px or line == "":
            line = trial
        else:
            out.append(line)
            line = word
    if line != "":
        out.append(line)
    return out


class Sheet:
    """An RGB picture held as one flat bytearray, row after row.

    A flat buffer keeps every horizontal run a single slice assignment,
    and the PNG writer can stream the rows straight out of it.
    """

    def __init__(self, size, bg):
        self.size = size
        self.px = bytearray(bytes(bg) * size * size)

    def _span(self, x, w):
        lo = max(0, x)
        hi = min(self.size, x + w)
        return (lo, hi - lo) if hi > lo else None

    def blot(self, x, y, w, h, colour):
        """Paint a filled rectangle, clipped to the sheet."""
        paint = bytes(colour)
        for yy in range(max(0, y), min(self.size, y + h)):
            span = self._span(x, w)
            if span:
                start, length = span
                base = (yy * self.size + start) * 3
                self.px[base:base + length * 3] = paint * length

    def edge(self, x, y, w, h, colour, t=2):
        self.blot(x, y, w, t, colour)
        self.blot(x, y + h - t, w, t, colour)
        self.blot(x, y, t, h, colour)
        self.blot(x + w - t, y, t, h, colour)

    def stripe_h(self, x, y, w, colour, t=1):
        self.blot(x, y, w, t, colour)

    def stripe_v(self, x, y, h, colour, t=1):
        self.blot(x, y, t, h, colour)

    def seg(self, x0, y0, x1, y1, colour, t=1):
        """Bresenham segment, each step a t-by-t square."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.blot(x0, y0, t, t, colour)
            if x0 == x1 and y0 == y1:
                return
            step = 2 * err
            if step >= dy:
                err += dy
                x0 += sx
            if step <= dx:
                err += dx
                y0 += sy

    def blob(self, cx, cy, r, colour):
        """Filled disc, one horizontal run per row."""
        for dy in range(-r, r + 1):
            half = int(math.sqrt(r * r - dy * dy))
            self.blot(cx - half, cy + dy, 2 * half + 1, 1, colour)

    def hoop(self, cx, cy, r, colour, t=3):
        for deg in range(360):
            rad = math.radians(deg)
            self.blot(int(cx + r * math.cos(rad)),
                      int(cy + r * math.sin(rad)), t, t, colour)

    def poly(self, pts, colour):
        """Filled polygon, scanline even-odd fill from an edge table.

        Each row collects the x where an edge crosses it (upper vertex
        excluded, so shared vertices are counted once), sorts the
        crossings and paints between them in pairs.
        """
        top = max(0, min(p[1] for p in pts))
        bottom = min(self.size - 1, max(p[1] for p in pts))
        count = len(pts)
        for y in range(top, bottom + 1):
            hits = []
            for i in range(count):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % count]
                if ay == by:
                    continue
                if min(ay, by) <= y < max(ay, by):
                    hits.append(ax + (y - ay) * (bx - ax) / (by - ay))
            hits.sort()
            for j in range(0, len(hits) - 1, 2):
                left = int(math.ceil(hits[j]))
                right = int(hits[j + 1])
                self.blot(left, y, right - left + 1, 1, colour)

    def mark(self, x, y, ch, scale, colour):
        rows = glyph_rows(ch) if ch in GLYPHS else None
        if rows is None:
            return
        for row_i, bits in enumerate(rows):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    self.blot(x + col * scale, y + row_i * scale,
                              scale, scale, colour)

    def write(self, x, y, string, scale, colour):
        pen = x
        for ch in string.upper():
            self.mark(pen, y, ch, scale, colour)
            pen += ADVANCE * scale
        return pen

    def write_centre(self, y, string, scale, colour, x0=0, x1=SIDE):
        w = measure(string, scale)
        self.write(x0 + (x1 - x0 - w) // 2, y, string, scale, colour)

    def block(self, x, y, string, scale, colour, max_px, gap=4):
        """Wrapped paragraph; returns the y just below its last line."""
        lines = wrap_words(string, scale, max_px)
        step = ROWS * scale + gap
        for i, line in enumerate(lines):
            self.write(x, y + i * step, line, scale, colour)
        return y + len(lines) * step

    def ink_share(self):
        """Share of pixels that differ from the cream background."""
        bg = bytes(CREAM)
        hit = 0
        row_len = self.size * 3
        for r in range(self.size):
            row = self.px[r * row_len:(r + 1) * row_len]
            for i in range(0, row_len, 3):
                if row[i:i + 3] != bg:
                    hit += 1
        return hit / (self.size * self.size)


# ---------------------------------------------------------------------------
# Pictograms, each drawn inside an 84x84 panel at (x, y).
# ---------------------------------------------------------------------------
def pic_burst(sh, x, y):
    sh.blot(x, y, 84, 84, PAPERWHITE)
    sh.edge(x, y, 84, 84, SOOT, 2)
    cx, cy = x + 42, y + 42
    for i in range(8):
        a0 = 2 * math.pi * i / 8
        a1 = 2 * math.pi * (i + 0.5) / 8
        tip = (int(cx + 34 * math.cos(a0)), int(cy + 34 * math.sin(a0)))
        valley = (int(cx + 13 * math.cos(a1)), int(cy + 13 * math.sin(a1)))
        base = (int(cx + 34 * math.cos(a0 + 2 * math.pi / 8)),
                int(cy + 34 * math.sin(a0 + 2 * math.pi / 8)))
        sh.poly((tip, valley, base), CRIMSON)
    sh.blob(cx, cy, 12, OCHRE)
    sh.blob(cx, cy, 5, PAPERWHITE)


def pic_shield(sh, x, y):
    sh.blot(x, y, 84, 84, PAPERWHITE)
    sh.edge(x, y, 84, 84, SOOT, 2)
    cx = x + 42
    sh.poly(((cx, y + 8), (x + 70, y + 20), (x + 70, y + 44),
             (cx, y + 76), (x + 14, y + 44), (x + 14, y + 20)), NAVY)
    sh.poly(((cx, y + 16), (x + 62, y + 25), (x + 62, y + 43),
             (cx, y + 66), (x + 22, y + 43), (x + 22, y + 25)), SHEET)
    sh.seg(cx - 12, y + 40, cx - 2, y + 52, CRIMSON, 4)
    sh.seg(cx - 2, y + 52, cx + 14, y + 30, CRIMSON, 4)


def pic_arcs(sh, x, y):
    sh.blot(x, y, 84, 84, PAPERWHITE)
    sh.edge(x, y, 84, 84, SOOT, 2)
    sh.hoop(x + 32, y + 42, 20, TEAL, 3)
    sh.hoop(x + 52, y + 42, 20, NAVY, 3)
    sh.blob(x + 32, y + 22, 4, TEAL)
    sh.blob(x + 52, y + 62, 4, NAVY)
    sh.blob(x + 42, y + 42, 4, CRIMSON)


def pic_thermo(sh, x, y):
    sh.blot(x, y, 84, 84, PAPERWHITE)
    sh.edge(x, y, 84, 84, SOOT, 2)
    cx = x + 42
    sh.blot(cx - 6, y + 12, 12, 44, SHEET)
    sh.edge(cx - 6, y + 12, 12, 44, SOOT, 2)
    sh.blob(cx, y + 62, 13, SHEET)
    sh.hoop(cx, y + 62, 13, SOOT, 2)
    sh.blot(cx - 3, y + 26, 6, 30, CRIMSON)
    sh.blob(cx, y + 62, 8, CRIMSON)
    for i, yy in enumerate((16, 28, 40, 52)):
        sh.stripe_h(cx + 6, y + yy, 8 if i % 2 == 0 else 5, SOOT, 2)


def pic_wave(sh, x, y):
    sh.blot(x, y, 84, 84, PAPERWHITE)
    sh.edge(x, y, 84, 84, SOOT, 2)
    sh.blob(x + 62, y + 22, 10, OCHRE)
    prev = None
    for step in range(61):
        px = x + 12 + step
        py = y + 48 + int(7 * math.sin(step / 9.0))
        if prev is not None:
            sh.seg(prev[0], prev[1], px, py, TEAL, 3)
        prev = (px, py)
    prev = None
    for step in range(61):
        px = x + 12 + step
        py = y + 64 + int(7 * math.sin(step / 9.0 + 1.5))
        if prev is not None:
            sh.seg(prev[0], prev[1], px, py, NAVY, 3)
        prev = (px, py)


def pic_scales(sh, x, y):
    sh.blot(x, y, 84, 84, PAPERWHITE)
    sh.edge(x, y, 84, 84, SOOT, 2)
    cx = x + 42
    sh.stripe_v(cx - 1, y + 10, 54, SOOT, 3)
    sh.stripe_h(x + 14, y + 14, 56, SOOT, 3)
    sh.blob(cx, y + 10, 4, OCHRE)
    for side in (-1, 1):
        px = cx + side * 26
        sh.seg(px, y + 14, px - 9, y + 34, SOOT, 2)
        sh.seg(px, y + 14, px + 9, y + 34, SOOT, 2)
        sh.poly(((px - 11, y + 34), (px + 11, y + 34), (px, y + 52)),
                CRIMSON if side < 0 else NAVY)
    sh.stripe_h(x + 16, y + 66, 52, SOOT, 3)


# ---------------------------------------------------------------------------
# Story furniture: a card with a pictogram at the top right, and a wide
# band with a pictogram at the right end.
# ---------------------------------------------------------------------------
def side_card(sh, x, y, w, h, tint, kicker, headline, body, pic):
    sh.blot(x, y, w, h, SHEET)
    sh.edge(x, y, w, h, SOOT, 2)
    sh.blot(x, y, w, 8, tint)
    sh.write(x + 14, y + 20, kicker, 2, tint)
    pic(sh, x + w - 98, y + 34)
    end = sh.block(x + 14, y + 36, headline, 3, SOOT, w - 128, gap=4)
    # Body starts below the pictogram so no line runs under its panel.
    body_y = end + 8
    if body_y < y + 126:
        body_y = y + 126
    sh.block(x + 14, body_y, body, 2, SOOT, w - 28, gap=3)


def wide_band(sh, x, y, w, h, tint, kicker, headline, body, pic):
    sh.blot(x, y, w, h, SHEET)
    sh.edge(x, y, w, h, SOOT, 2)
    sh.blot(x, y, w, 8, tint)
    sh.write(x + 14, y + 20, kicker, 2, tint)
    pic(sh, x + w - 98, y + 24)
    end = sh.block(x + 14, y + 44, headline, 3, SOOT, w - 128, gap=4)
    sh.block(x + 14, end + 6, body, 2, SOOT, w - 128, gap=3)


def narrow_card(sh, x, y, w, h, tint, kicker, headline, body, pic):
    """Small card where the pictogram owns the right strip outright:
    headline and body both wrap in the space left of it."""
    sh.blot(x, y, w, h, SHEET)
    sh.edge(x, y, w, h, SOOT, 2)
    sh.blot(x, y, w, 8, tint)
    sh.write(x + 14, y + 20, kicker, 2, tint)
    pic(sh, x + w - 98, y + 30)
    end = sh.block(x + 14, y + 36, headline, 3, SOOT, w - 128, gap=4)
    sh.block(x + 14, end + 6, body, 2, SOOT, w - 128, gap=3)


def build_page():
    sh = Sheet(SIDE, CREAM)

    # Date strip.
    sh.blot(0, 0, SIDE, 30, NAVY)
    sh.write_centre(8, "SUNDAY 22 NOVEMBER 2026", 2, PAPERWHITE)
    sh.write(24, 8, "NO. 326", 2, SKYBLUE)
    sh.write(SIDE - 24 - measure("PRICE: ONE PAGE", 2), 8,
             "PRICE: ONE PAGE", 2, SKYBLUE)

    # Masthead.
    sh.write_centre(44, "THE DAILY WORLD", 9, SOOT)
    sh.write_centre(116, "ONE DAY  -  ONE IMAGE  -  THE WORLD'S NEWS", 2,
                    CRIMSON)
    sh.stripe_h(24, 138, 976, CRIMSON, 5)
    sh.stripe_h(24, 146, 976, SOOT, 2)

    # Lead story: Iran strikes US bases in Bahrain. Graphic on the left,
    # words on the right.
    sh.blot(24, 158, 976, 256, SHEET)
    sh.edge(24, 158, 976, 256, SOOT, 3)
    gx, gy = 40, 174
    sh.blot(gx, gy, 260, 224, PAPERWHITE)
    sh.edge(gx, gy, 260, 224, SOOT, 2)
    bx, by = gx + 130, gy + 92
    sh.hoop(bx, by, 66, MAROON, 3)
    sh.hoop(bx, by, 48, OCHRE, 3)
    for i in range(10):
        a0 = 2 * math.pi * i / 10
        a1 = 2 * math.pi * (i + 0.5) / 10
        tip = (int(bx + 58 * math.cos(a0)), int(by + 58 * math.sin(a0)))
        valley = (int(bx + 24 * math.cos(a1)), int(by + 24 * math.sin(a1)))
        base = (int(bx + 58 * math.cos(a0 + 2 * math.pi / 10)),
                int(by + 58 * math.sin(a0 + 2 * math.pi / 10)))
        sh.poly((tip, valley, base), CRIMSON)
    sh.blob(bx, by, 16, OCHRE)
    sh.blob(bx, by, 7, PAPERWHITE)
    sh.write_centre(gy + 176, "IRGC CLAIMS", 2, SOOT, gx, gx + 260)
    sh.write_centre(gy + 196, "2 RADARS HIT", 2, CRIMSON, gx, gx + 260)
    tx = 316
    sh.write(tx, 174, "LEAD STORY - MANAMA / TEHRAN", 2, CRIMSON)
    sh.write(tx, 198, "IRAN STRIKES", 5, SOOT)
    sh.write(tx, 240, "US BASES IN", 5, SOOT)
    sh.write(tx, 282, "BAHRAIN", 5, SOOT)
    sh.write(tx, 326, "PATRIOT RADARS CLAIMED HIT", 3, CRIMSON)
    sh.block(tx, 354,
             "IRAN FIRED MISSILES AND DRONES AT US POSITIONS AT AL-RIFFA "
             "AND AWALI IN BAHRAIN. A CIVILIAN PLANT WAS HIT AND CAUGHT "
             "FIRE. NO ONE WAS HURT.",
             2, SOOT, 684, gap=4)

    # Two half-width cards: NATO in Warsaw, EU-Indonesia trade deal.
    side_card(sh, 24, 426, 480, 200, NAVY, "SECURITY - WARSAW",
              "NATO VOWS TO DEFEND EVERY INCH OF POLAND",
              "RUTTE VISITS WARSAW A DAY AFTER THE MISSILES LANDED. "
              "ALLIES MEET ON MONDAY. POLAND ASKS FOR MORE JETS AND "
              "EARLY WARNING PLANES.",
              pic_shield)
    side_card(sh, 520, 426, 480, 200, TEAL, "TRADE - BRUSSELS",
              "EU AND INDONESIA SIGN LANDMARK TRADE DEAL",
              "CEPA AND INVESTMENT PACT SIGNED AFTER 10 YEARS OF TALKS. "
              "98.5% OF TARIFFS TO GO. EU EXPORTERS TO SAVE 650M EURO "
              "A YEAR.",
              pic_arcs)

    # Wide band: COP31 deadlocked in overtime.
    wide_band(sh, 24, 638, 976, 132, OCHRE, "CLIMATE - ANTALYA",
              "COP31 TALKS DEADLOCK IN OVERTIME",
              "DRAFT DROPS EVERY FOSSIL FUEL MENTION AND A $120BN "
              "ADAPTATION TARGET. EU: A GOOD DEAL OR NO DEAL AT ALL.",
              pic_thermo)

    # Two small boxes: Cyclone Akvan fades, France on Myanmar.
    narrow_card(sh, 24, 782, 480, 128, TEAL, "WEATHER - INDIA",
                "AKVAN FADES AFTER 300,000 MOVED",
                "HEAVY RAIN AND FLOODING IN ODISHA. NO DEATHS REPORTED.",
                pic_wave)
    narrow_card(sh, 520, 782, 480, 128, NAVY, "JUSTICE - NEW YORK",
                "FRANCE SEEKS UN ACTION ON MYANMAR",
                "MYANMAR REJECTED THE ICJ RULING ON THE ROHINGYA.",
                pic_scales)

    # Ticker.
    sh.blot(24, 920, 976, 72, NAVY)
    sh.block(40, 928,
             "QUAKE 6.8 HITS BANDA SEA NEAR TIMOR-LESTE \u2022 HONG KONG "
             "VOTES FOR 723 ELECTION COMMITTEE SEATS \u2022 BOLSONARO IN "
             "ICU \u2022 DRONES HIT RUSSIAN SHIP IN THE BALTIC \u2022 2 "
             "KILLED IN LVIV STRIKE",
             2, PAPERWHITE, 944, gap=4)

    # Footer.
    sh.write_centre(1002, "SOURCES: REUTERS, XINHUA, EUROPEAN COMMISSION, "
                    "AP - 22 NOV 2026", 2, SLATE)
    return sh


# ---------------------------------------------------------------------------
# PNG writer: RGB, 8-bit, zlib level 9, filter byte 0 on every row.
# No time or text chunks, so the bytes are fully determined by the page.
# ---------------------------------------------------------------------------
def _frame(tag, payload):
    framed = tag + payload
    return (struct.pack(">I", len(payload)) + framed +
            struct.pack(">I", zlib.crc32(framed) & 0xFFFFFFFF))


def encode(sh):
    header = struct.pack(">IIBBBBB", SIDE, SIDE, 8, 2, 0, 0, 0)
    rows = b"".join(
        b"\x00" + bytes(sh.px[r * SIDE * 3:(r + 1) * SIDE * 3])
        for r in range(SIDE))
    return (b"\x89PNG\r\n\x1a\n" + _frame(b"IHDR", header) +
            _frame(b"IDAT", zlib.compress(rows, 9)) + _frame(b"IEND", b""))


def save(sh, path):
    with open(path, "wb") as handle:
        handle.write(encode(sh))


def check_png(path):
    """Check a finished entry.png and report each check on its own line."""
    with open(path, "rb") as handle:
        data = handle.read()
    found = []
    found.append(("signature",
                  data[:8] == b"\x89PNG\r\n\x1a\n"))
    width, height = struct.unpack(">II", data[16:24])
    found.append(("dimensions", (width, height) == (SIDE, SIDE)))
    found.append(("size_under_1mib", 1000 < len(data) < 1048576))
    found.append(("iend_present", data.endswith(_frame(b"IEND", b""))))
    for name, passed in found:
        print("%s: %s" % (name, "OK" if passed else "BAD"))
    return all(passed for _, passed in found)


def report(sh, path):
    """Facts about the finished page, for the build log."""
    print("glyphs in font: %d" % len(GLYPHS))
    print("ink coverage: %.3f" % sh.ink_share())
    print("entry.png: %d bytes" % os.path.getsize(path))
    print("sheet bytes: %d" % len(sh.px))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Draw the 22 Nov 2026 front page as entry.png.")
    parser.add_argument("--out", metavar="DIR",
                        help="directory to write entry.png into")
    parser.add_argument("--verify", action="store_true",
                        help="only check an existing entry.png")
    return parser.parse_args(argv)


def run():
    args = main()
    out_dir = args.out or os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    if args.verify:
        if not os.path.exists(path):
            print("missing: %s" % path)
            sys.exit(1)
        sys.exit(0 if check_png(path) else 1)
    page = build_page()
    save(page, path)
    if not check_png(path):
        sys.exit(1)
    report(page, path)


if __name__ == "__main__":
    run()
