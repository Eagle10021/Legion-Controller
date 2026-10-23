#!/usr/bin/env python3
"""
Rebuild legion_control/assets/mdi-subset.ttf with the Material Design Icons the app uses.

Usage:  python3 tools/make_icon_font.py [extra-icon-name ...]
Needs:  pip install fonttools   (only for this script, not for running the app)

Icon names are the ones on https://pictogrammers.com/library/mdi/ (e.g. "battery-50", "fire").
Already-used names are read from assets/mdi_codepoints.py, so passing new names adds to the set.
"""
import os
import re
import sys
import tempfile
import urllib.request

from fontTools import subset

VERSION = "7.4.47"
CDN = f"https://cdn.jsdelivr.net/npm/@mdi/font@{VERSION}"
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "legion_control", "assets")


def main():
    current = os.path.join(ASSETS, "mdi_codepoints.py")
    names = re.findall(r'^\s+"([a-z0-9-]+)":', open(current).read(), re.M) if os.path.exists(current) else []
    names += [n for n in sys.argv[1:] if n not in names]

    with tempfile.TemporaryDirectory() as tmp:
        ttf, css = os.path.join(tmp, "mdi.ttf"), os.path.join(tmp, "mdi.css")
        urllib.request.urlretrieve(f"{CDN}/fonts/materialdesignicons-webfont.ttf", ttf)
        urllib.request.urlretrieve(f"{CDN}/css/materialdesignicons.css", css)
        css_text = open(css).read()
        codepoints = {}
        for n in names:
            m = re.search(r'\.mdi-%s::before \{\s*content: "\\(F[0-9A-F]+)";' % re.escape(n), css_text)
            if not m:
                sys.exit(f"Unknown icon: {n}")
            codepoints[n] = int(m.group(1), 16)

        opts = subset.Options()
        opts.notdef_outline = True
        font = subset.load_font(ttf, opts)
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=list(codepoints.values()))
        sub.subset(font)
        subset.save_font(font, os.path.join(ASSETS, "mdi-subset.ttf"), opts)

    with open(current, "w") as f:
        f.write('"""Material Design Icons used by the app (name -> codepoint in mdi-subset.ttf).\n'
                'Regenerate with tools/make_icon_font.py after adding names."""\n\nCODEPOINTS = {\n')
        for n, cp in codepoints.items():
            f.write(f'    "{n}": 0x{cp:X},\n')
        f.write("}\n")
    print(f"{len(codepoints)} icons written to {ASSETS}")


if __name__ == "__main__":
    main()
