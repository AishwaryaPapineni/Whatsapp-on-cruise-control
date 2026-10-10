#!/usr/bin/env python3
"""Session 1.1 Part 5: build docs/architecture_diagram.excalidraw (editable) and .png.

Follows the brief's exercise exactly: 8 boxes left->right, colour by brain
(gray = rules/no AI, blue = history brain, green = persona brain, purple = generation,
white = plumbing), arrows, three side notes and the title. Open the .excalidraw file at
https://excalidraw.com (menu -> Open) to edit it by hand.
"""
import json
import random
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
STAGES = [
    ("Message In", "#ffffff", "plumbing"),
    ("Router", "#e9ecef", "rules - no AI"),
    ("Decision Engine", "#e9ecef", "rules - no AI"),
    ("Retrieval", "#a5d8ff", "HISTORY BRAIN"),
    ("Persona Injection", "#b2f2bb", "PERSONA BRAIN"),
    ("Generation", "#d0bfff", "both brains + LLM"),
    ("Human-like Delay", "#ffffff", "plumbing"),
    ("Send (Baileys)", "#ffffff", "plumbing"),
]
NOTES = {
    1: "looks up phone number in a\ntable I maintain - no AI",
    2: "cheap rules first, one AI call\nonly if truly ambiguous",
    3: "searches only the matching\nrelationship's memory\n(family/friend/professional/\nunknown) + last N messages\nof this chat (short-term)",
    4: "persona.json: identity, tone\nper relationship, hard rules",
    5: "Gemini 3.5 Flash (free tier)\n+ output guardrail",
}
W, H, GAP, X0, Y0 = 170, 80, 50, 40, 140


def _base(kind, x, y, w, h, **kw):
    el = {
        "id": f"{kind}-{random.randrange(10**9)}", "type": kind, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [],
        "frameId": None, "roundness": {"type": 3}, "seed": random.randrange(10**9), "version": 1,
        "versionNonce": random.randrange(10**9), "isDeleted": False, "boundElements": [], "updated": 1,
        "link": None, "locked": False,
    }
    el.update(kw)
    return el


def _text(x, y, w, h, text, size=18, container=None, align="center"):
    return _base("text", x, y, w, h, text=text, originalText=text, fontSize=size, fontFamily=1,
                 textAlign=align, verticalAlign="middle", containerId=container, lineHeight=1.25,
                 autoResize=True, roundness=None, strokeWidth=1)


def excalidraw() -> dict:
    random.seed(42)
    els = [_text(X0, 40, 1500, 40, "WhatsApp Cruise Control - Two-Brain Pipeline", size=32, align="left")]
    boxes = []
    for i, (name, color, _) in enumerate(STAGES):
        x = X0 + i * (W + GAP)
        box = _base("rectangle", x, Y0, W, H, backgroundColor=color)
        txt = _text(x + 5, Y0 + 20, W - 10, 40, name, container=box["id"])
        box["boundElements"] = [{"type": "text", "id": txt["id"]}]
        els += [box, txt]
        boxes.append(box)
    for a, b in zip(boxes, boxes[1:]):
        x1, x2, y = a["x"] + W, b["x"], Y0 + H / 2
        arrow = _base("arrow", x1 + 4, y, x2 - x1 - 8, 0, points=[[0, 0], [x2 - x1 - 8, 0]], roundness={"type": 2},
                      startBinding={"elementId": a["id"], "focus": 0, "gap": 4},
                      endBinding={"elementId": b["id"], "focus": 0, "gap": 4}, startArrowhead=None, endArrowhead="arrow")
        a["boundElements"].append({"type": "arrow", "id": arrow["id"]})
        b["boundElements"].append({"type": "arrow", "id": arrow["id"]})
        els.append(arrow)
    for i, note in NOTES.items():
        x = X0 + i * (W + GAP)
        els.append(_text(x, Y0 + H + 25, W + 30, 100, note, size=14, align="left"))
    legend = "gray = rule-based, no AI   blue = history brain (RAG)   green = persona brain   purple = generation   white = plumbing"
    els.append(_text(X0, Y0 + H + 160, 1500, 24, legend, size=16, align="left"))
    return {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": els,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}


def svg() -> str:
    tot_w = X0 * 2 + len(STAGES) * W + (len(STAGES) - 1) * GAP
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{tot_w}" height="400" font-family="Segoe UI, Helvetica, Arial, sans-serif">',
             '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#1e1e1e"/></marker></defs>',
             f'<rect width="{tot_w}" height="400" fill="#ffffff"/>',
             f'<text x="{X0}" y="70" font-size="30" font-weight="700" fill="#1e1e1e">WhatsApp Cruise Control — Two-Brain Pipeline</text>']
    for i, (name, color, tag) in enumerate(STAGES):
        x = X0 + i * (W + GAP)
        parts.append(f'<rect x="{x}" y="{Y0}" width="{W}" height="{H}" rx="12" fill="{color}" stroke="#1e1e1e" stroke-width="2"/>')
        parts.append(f'<text x="{x + W/2}" y="{Y0 + H/2 + 6}" font-size="17" font-weight="600" text-anchor="middle" fill="#1e1e1e">{name}</text>')
        parts.append(f'<text x="{x + W/2}" y="{Y0 - 10}" font-size="12" text-anchor="middle" fill="#555">{tag}</text>')
        if i < len(STAGES) - 1:
            parts.append(f'<line x1="{x + W + 4}" y1="{Y0 + H/2}" x2="{x + W + GAP - 6}" y2="{Y0 + H/2}" stroke="#1e1e1e" stroke-width="2" marker-end="url(#a)"/>')
    for i, note in NOTES.items():
        x = X0 + i * (W + GAP)
        for j, line in enumerate(note.split("\n")):
            parts.append(f'<text x="{x}" y="{Y0 + H + 35 + j*18}" font-size="13" fill="#333">{line}</text>')
    legend = [("#e9ecef", "rule-based, no AI"), ("#a5d8ff", "history brain (RAG)"), ("#b2f2bb", "persona brain"), ("#d0bfff", "generation (LLM)"), ("#ffffff", "plumbing")]
    lx = X0
    for color, label in legend:
        parts.append(f'<rect x="{lx}" y="350" width="22" height="16" fill="{color}" stroke="#1e1e1e"/><text x="{lx + 30}" y="363" font-size="14" fill="#1e1e1e">{label}</text>')
        lx += 230
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    (DOCS / "architecture_diagram.excalidraw").write_text(json.dumps(excalidraw(), indent=1), encoding="utf-8")
    (DOCS / "architecture_diagram.svg").write_text(svg(), encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(device_scale_factor=2)
            pg.set_content(f"<html><body style='margin:0'>{svg()}</body></html>")
            pg.locator("svg").screenshot(path=str(DOCS / "architecture_diagram.png"))
            b.close()
        print("wrote .excalidraw, .svg, .png")
    except Exception as e:  # noqa: BLE001
        print(f"wrote .excalidraw and .svg (png needs playwright: {e})")
