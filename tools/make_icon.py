#!/usr/bin/env python3
"""Render the integration's brand icons (stylized flat flames) from cubic-Bezier paths.
Writes the brand/ PNGs for Home Assistant plus assets/icon.svg for the README. Needs Pillow."""
import re
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "custom_components/in_flames/brand"
BOX = 512

# (gradient top colour, gradient bottom colour, path) - drawn back to front.
# Paths: "M x y" then "C x1 y1 x2 y2 x y" segments, closed automatically.
LAYERS = [
    ("#ff3d3d", "#b0122e", "M256 28 C292 104 396 160 404 290 C412 410 340 484 256 484 C172 484 100 410 108 300 "
                           "C114 220 164 186 176 112 C204 160 214 196 230 206 C238 140 232 84 256 28"),
    ("#ffb000", "#ff5a1f", "M262 128 C286 196 350 236 352 322 C354 404 306 446 256 446 C206 446 158 404 162 334 "
                           "C166 284 196 262 206 216 C222 250 232 266 246 270 C250 222 246 176 262 128"),
    ("#fff6b0", "#ffd23f", "M258 252 C276 294 314 322 312 372 C310 414 286 432 256 432 C226 432 200 414 200 380 "
                           "C200 346 226 330 236 300 C244 318 250 326 256 328 C258 304 252 280 258 252"),
]
# little flying embers: (cx, cy, r, colour)
EMBERS = [(150, 92, 9, "#ff8a1f"), (372, 74, 7, "#ffb000"), (404, 150, 5, "#ff5a1f")]


def parse(path: str) -> list[tuple[str, list[float]]]:
    toks, segs, cur = re.findall(r"[MC]|-?\d+(?:\.\d+)?", path), [], None
    for t in toks:
        if t in "MC":
            cur = (t, [])
            segs.append(cur)
        else:
            cur[1].append(float(t))
    return segs


def polygon(path: str, scale: float, steps: int = 40) -> list[tuple[float, float]]:
    pts, (x0, y0) = [], (0.0, 0.0)
    for cmd, v in parse(path):
        if cmd == "M":
            x0, y0 = v
            pts.append((x0, y0))
            continue
        for i in range(0, len(v), 6):
            x1, y1, x2, y2, x3, y3 = v[i:i + 6]
            for s in range(1, steps + 1):
                t = s / steps
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
                pts.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))
            x0, y0 = x3, y3
    return [(x * scale, y * scale) for x, y in pts]


def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def render(size: int) -> Image.Image:
    ss = 4  # supersample for smooth edges
    big = size * ss
    scale = big / BOX
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    for top, bottom, path in LAYERS:
        poly = polygon(path, scale)
        ys = [p[1] for p in poly]
        y_min, y_max = min(ys), max(ys)
        grad = Image.new("RGBA", (big, big))
        g = ImageDraw.Draw(grad)
        t_rgb, b_rgb = hex_rgb(top), hex_rgb(bottom)
        for y in range(big):
            f = min(max((y - y_min) / (y_max - y_min), 0), 1)
            g.line([(0, y), (big, y)], fill=tuple(round(t + (b - t) * f) for t, b in zip(t_rgb, b_rgb)) + (255,))
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).polygon(poly, fill=255)
        img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    for cx, cy, r, col in EMBERS:
        d.ellipse([(cx - r) * scale, (cy - r) * scale, (cx + r) * scale, (cy + r) * scale], fill=col)
    return img.resize((size, size), Image.LANCZOS)


def svg() -> str:
    defs, shapes = [], []
    for i, (top, bottom, path) in enumerate(LAYERS):
        defs.append(f'<linearGradient id="g{i}" x1="0" y1="0" x2="0" y2="1">'
                    f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>')
        shapes.append(f'<path d="{path} Z" fill="url(#g{i})"/>')
    for cx, cy, r, col in EMBERS:
        shapes.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BOX} {BOX}">'
            f'<defs>{"".join(defs)}</defs>{"".join(shapes)}</svg>\n')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT.parent.parent.parent / "assets/icon.svg").write_text(svg())
    render(256).save(OUT / "icon.png")
    render(512).save(OUT / "icon@2x.png")
    render(256).save(OUT / "logo.png")
    render(512).save(OUT / "logo@2x.png")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
