#!/usr/bin/env python3
"""Tiny terminal-to-GIF renderer (Pillow only). Used to build docs/demo.gif.

A scenario is a list of steps:
  ("type", "text")            typed after a prompt, character by character
  ("out", "text")             printed at once (may hold several lines)
  ("pause", seconds)
  ("clear",)
The commands in a scenario are really run (see the render_demo.py next to
this file) and their real output is passed in as "out" steps.
"""
from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont

BG = (22, 24, 30)
FG = (214, 218, 228)
DIM = (120, 128, 148)
RED = (255, 107, 107)
GREEN = (126, 217, 150)
YELLOW = (246, 201, 105)
BLUE = (122, 176, 255)
BAR = (36, 39, 48)
FONT_PATHS = ["/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def load_font(size):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


class Term:
    def __init__(self, cols=86, rows=19, size=17, title="demo"):
        self.cols, self.rows, self.title = cols, rows, title
        self.font = load_font(size)
        bbox = self.font.getbbox("M")
        self.cw = round(self.font.getlength("M"))
        self.lh = size + 8
        self.pad = 22
        self.bar = 34
        self.w = self.cols * self.cw + 2 * self.pad
        self.h = self.bar + self.rows * self.lh + 2 * self.pad - 6
        self.lines = [[]]  # list of lines; each line = list of (char, color)
        self.frames, self.durs = [], []

    # --- buffer ---
    def _wrap_push(self, ch, color):
        if ch == "\n":
            self.lines.append([])
            return
        if len(self.lines[-1]) >= self.cols:
            self.lines.append([])
        self.lines[-1].append((ch, color))
        while len(self.lines) > self.rows:
            self.lines.pop(0)

    def write(self, text, color=FG):
        for ch in text:
            self._wrap_push(ch, color)

    # --- drawing ---
    def snap(self, dur, cursor=True):
        img = Image.new("RGB", (self.w, self.h), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.w, self.bar], fill=BAR)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([14 + i * 22, 11, 26 + i * 22, 23], fill=c)
        tw = d.textlength(self.title, font=self.font)
        d.text(((self.w - tw) / 2, 7), self.title, font=self.font, fill=DIM)
        y0 = self.bar + self.pad - 8
        for r, line in enumerate(self.lines):
            for c, (ch, col) in enumerate(line):
                if ch != " ":
                    d.text((self.pad + c * self.cw, y0 + r * self.lh), ch, font=self.font, fill=col)
        if cursor:
            r, c = len(self.lines) - 1, len(self.lines[-1])
            x, y = self.pad + c * self.cw, y0 + r * self.lh
            d.rectangle([x, y + 3, x + self.cw - 2, y + self.lh - 4], fill=FG)
        self.frames.append(img)
        self.durs.append(int(dur * 1000))

    def _wrap(self, segs):
        """Word-wrap one coloured line to the terminal width, with a hanging indent."""
        chars = [(ch, c) for t, c in segs for ch in t]
        text = "".join(ch for ch, _ in chars)
        indent = len(text) - len(text.lstrip())
        lab = text.lstrip().split(" ")[0]
        hang = " " * (indent + 10) if lab.endswith(":") else " " * indent
        out, first = [], True
        while len(chars) > self.cols:
            cut = max(i for i in range(self.cols) if chars[i][0] == " ")
            out.append(chars[:cut])
            chars = [(" ", FG)] * 0 + [(ch, FG) for ch in hang] + chars[cut + 1:]
        out.append(chars)
        return [[(ch, c) for ch, c in line] for line in out]

    def prompt(self, p="$ "):
        if self.lines[-1]:
            self.write("\n")
        self.write(p, GREEN)

    # --- steps ---
    def run(self, steps, prompt="$ ", type_chunk=2, type_dt=0.05, line_dt=0.12):
        self.snap(0.5)
        for st in steps:
            kind = st[0]
            if kind == "type":
                self.prompt(prompt)
                text = st[1]
                for i in range(0, len(text), type_chunk):
                    self.write(text[i:i + type_chunk], FG)
                    self.snap(type_dt)
                self.snap(0.35)
                self.write("\n")
            elif kind == "out":
                for line in st[1].split("\n"):
                    self.write(line + "\n", st[2] if len(st) > 2 else FG)
                    self.snap(line_dt)
            elif kind == "outc":  # colored segments per line: list of (text,color) lists
                for segs in st[1]:
                    for chunk in self._wrap(segs):
                        for t, c in chunk:
                            self.write(t, c)
                        self.write("\n")
                        self.snap(line_dt)
            elif kind == "pause":
                self.snap(st[1])
            elif kind == "clear":
                self.lines = [[]]
                self.snap(0.2)
        self.prompt(prompt)
        self.snap(1.8)

    def save(self, path, colors=48):
        pal = [f.convert("P", palette=Image.ADAPTIVE, colors=colors) for f in self.frames]
        pal[0].save(path, save_all=True, append_images=pal[1:], duration=self.durs,
                    loop=0, optimize=True, disposal=1)


def colorize_block(text):
    """Colour the safe-vibe style message: header red, labels yellow."""
    out = []
    for line in text.rstrip("\n").split("\n"):
        s = line.lstrip()
        if line.endswith("blocked this command."):
            out.append([(line, RED)])
        else:
            for lab in ("What:", "Why:", "Instead:"):
                if s.startswith(lab):
                    ind = line[: len(line) - len(s)]
                    out.append([(ind, FG), (lab, YELLOW), (s[len(lab):], FG)])
                    break
            else:
                out.append([(line, FG)])
    return out
