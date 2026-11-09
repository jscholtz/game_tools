from html import escape

import streamlit as st
from pymongo.errors import PyMongoError

from .database import load_bestiary_display, load_bestiary_index

FRAME_PADDING = 50


def _render_creature(display: dict) -> None:
    html = display.get("inline")
    sizes = display.get("sizes")
    if (
        not isinstance(html, str)
        or "<head>" not in html
        or "</body>" not in html
        or not isinstance(sizes, list)
        or len(sizes) != 2
        or any(not isinstance(size, int) or isinstance(size, bool) or size <= 0 for size in sizes)
    ):
        st.error("Creature stat block has invalid HTML or dimensions.")
        return

    policy = (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "img-src data:; font-src data:; base-uri 'none'; form-action 'none'"
    )
    meta = f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
    html = html.replace("<head>", f"<head>{meta}", 1)
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
    height, width = sizes
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


def render_bestiary_tab() -> None:
    if st.session_state.get("logged_in_role") != "dm":
        st.error("Only the DM can access the bestiary.")
        return

    st.header("Bestiary")
    try:
        creatures = load_bestiary_index()
    except (KeyError, PyMongoError) as error:
        st.error(f"Could not load bestiary: {error}")
        return

    if not creatures:
        st.info("The bestiary is empty.")
        return

    creature_types = sorted({entry["type"] for entry in creatures})
    sizes = sorted({entry["size"] for entry in creatures})
    sources = sorted({entry["document__title"] for entry in creatures})
    rating_values = {entry["challenge_rating"]: entry["cr"] for entry in creatures}
    ratings = sorted(rating_values, key=rating_values.__getitem__)
    filters, results_column = st.columns([1, 2])
    with filters:
        name = st.text_input("Search by name").strip().casefold()
        selected_type = st.selectbox("Type", ["All", *creature_types])
        selected_rating = st.selectbox("Challenge rating", ["All", *ratings])
        selected_size = st.selectbox("Size", ["All", *sizes])
        selected_source = st.selectbox("Source", ["All", *sources])

    matches = sorted(
        (
            entry for entry in creatures
            if name in entry["name"].casefold()
            and (selected_type == "All" or entry["type"] == selected_type)
            and (selected_rating == "All" or entry["challenge_rating"] == selected_rating)
            and (selected_size == "All" or entry["size"] == selected_size)
            and (selected_source == "All" or entry["document__title"] == selected_source)
        ),
        key=lambda entry: (entry["name"].casefold(), entry["document__title"], entry["slug"]),
    )
    with results_column:
        st.caption(f"{len(matches)} creatures found.")
        if not matches:
            return
        labels = {
            entry["slug"]: (
                f"{entry['name']} · CR {entry['challenge_rating']} · "
                f"{entry['type']} · {entry['size']} · {entry['document__title']}"
            )
            for entry in matches
        }
        selected = st.selectbox(
            "Creature",
            list(labels),
            index=None,
            placeholder="Choose a creature",
            format_func=labels.__getitem__,
        )
        if selected is None:
            return

        try:
            display = load_bestiary_display(selected)
        except (FileNotFoundError, KeyError, PyMongoError) as error:
            st.error(f"Could not load creature: {error}")
            return
        _render_creature(display)
