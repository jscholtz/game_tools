import json
from html import escape
import streamlit as st

from .data_models import BestiaryDisplay

FRAME_PADDING = 50


def _prepare_stat_block(display: BestiaryDisplay) -> tuple[str, int, int]:
    html = display.inline
    sizes = display.sizes
    policy = (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "img-src data:; font-src data:; base-uri 'none'; form-action 'none'"
    )
    meta = f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
    return html.replace("<head>", f"<head>{meta}", 1), sizes[0], sizes[1]


def render_stat_block(display: BestiaryDisplay) -> None:
    try:
        html, height, width = _prepare_stat_block(display)
    except ValueError as error:
        st.error(str(error))
        return
    resize_script = """
<script>
(() => {
    const block = document.querySelector("stat-block");
    if (!block) return;
    const reportSize = () => {
        const height = Math.ceil(block.getBoundingClientRect().bottom + window.scrollY);
        window.parent.postMessage({type: "bestiary-height", height}, "*");
    };
    new ResizeObserver(reportSize).observe(block);
    window.addEventListener("load", reportSize);
    window.addEventListener("resize", reportSize);
    reportSize();
})();
</script>
"""
    html = html.replace("</body>", f"{resize_script}</body>", 1)
    height += 2 * FRAME_PADDING
    width += 2 * FRAME_PADDING
    st.iframe(
        '<style>body { margin: 0; }</style>'
        '<iframe id="stat-block" title="Creature stat block" sandbox="allow-scripts" '
        f'srcdoc="{escape(html, quote=True)}" '
        f'style="display: block; width: {width}px; height: {height}px; border: 0;"></iframe>'
        '<script>'
        'const frame = document.getElementById("stat-block");'
        'window.addEventListener("message", (event) => {'
        '  if (event.source !== frame.contentWindow || '
        '      event.data?.type !== "bestiary-height" || '
        '      !Number.isFinite(event.data.height) || event.data.height <= 0 || '
        '      event.data.height > 100000) return;'
        f'  frame.style.height = (Math.ceil(event.data.height) + {FRAME_PADDING}) + "px";'
        '});'
        '</script>',
        width=width,
        height="content",
        alt="Creature stat block",
    )


def render_stat_block_tab_link(display: BestiaryDisplay, creature_name: str) -> None:
    try:
        html, height, width = _prepare_stat_block(display)
    except ValueError as error:
        st.error(str(error))
        return

    popup = (
        '<!doctype html><html><head><meta charset="utf-8">'
        f'<title>{escape(creature_name)}</title>'
        '<style>body { margin: 0; } iframe { border: 0; display: block; }</style>'
        '</head><body><iframe title="Creature stat block" sandbox="allow-scripts" '
        f'srcdoc="{escape(html, quote=True)}" '
        f'width="{width + 2 * FRAME_PADDING}" height="{height + 2 * FRAME_PADDING}">'
        '</iframe></body></html>'
    )
    payload = json.dumps(popup).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    st.iframe(
        '<style>body { margin: 0; font: 14px sans-serif; } '
        'a { color: #0068c9; cursor: pointer; display: inline-flex; } '
        '#error { color: #b42318; font-size: 14px; }</style>'
        '<a id="open" href="#" aria-label="Open stat block in new tab" '
        'title="Open stat block in new tab">'
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" '
        'aria-hidden="true"><path d="M19 19H5V5h7V3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14'
        'c1.1 0 2-.9 2-2v-7h-2v7zm-5-16v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/>'
        '</svg></a>'
        '<div id="error" role="alert"></div>'
        '<script>'
        f'const page = {payload};'
        'document.getElementById("open").addEventListener("click", (event) => {'
        ' event.preventDefault();'
        ' const tab = window.open("", "_blank");'
        ' if (!tab) { const error = document.getElementById("error");'
        ' error.textContent = "⚠"; error.title = "Could not open tab. Allow popups and try again.";'
        ' error.setAttribute("aria-label", error.title); return; }'
        ' tab.opener = null;'
        ' tab.document.open(); tab.document.write(page); tab.document.close();'
        '});'
        '</script>',
        width=32,
        height=40,
        alt="Open creature stat block",
    )
