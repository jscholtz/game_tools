import re
from pathlib import Path

import streamlit as st


PUBLIC_DATA_DIR = Path(__file__).parent.parent / "public_data"
SECTION_HEADING = re.compile(r"^#\s+(.+?)\s*$")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def render_markdown_content(lines: list[str]) -> None:
    markdown_lines = []

    def flush_markdown() -> None:
        if markdown_lines:
            st.markdown("\n".join(markdown_lines))
            markdown_lines.clear()

    for line in lines:
        image_match = IMAGE.fullmatch(line.strip())
        if image_match is None:
            markdown_lines.append(line)
            continue

        flush_markdown()
        alt_text, image_name = image_match.groups()
        image_file = (PUBLIC_DATA_DIR / image_name).resolve()
        if image_file.parent != PUBLIC_DATA_DIR.resolve():
            st.error(f"Image path must stay inside {PUBLIC_DATA_DIR.name}.")
            continue
        try:
            image = image_file.read_bytes()
        except OSError as error:
            st.error(f"Could not read {image_file.name}: {error}")
        else:
            st.image(image, caption=alt_text, width=600)

    flush_markdown()


@st.fragment(run_every=10)
def render_public_tab():
    public_page_file = PUBLIC_DATA_DIR / "public.md"
    try:
        public_page = public_page_file.read_text(encoding="utf-8")
    except OSError as error:
        st.error(f"Could not read {public_page_file.name}: {error}")
        return

    lines = public_page.splitlines()
    sections = []
    current_title = None
    current_lines = []
    for line in lines:
        heading = SECTION_HEADING.match(line)
        if heading:
            if current_title is None:
                render_markdown_content(current_lines)
            else:
                sections.append((current_title, current_lines))
            current_title = heading.group(1)
            current_lines = []
        else:
            current_lines.append(line)

    if current_title is None:
        render_markdown_content(current_lines)
    else:
        sections.append((current_title, current_lines))

    for title, section_lines in sections:
        with st.expander(title, expanded=False):
            render_markdown_content(section_lines)
