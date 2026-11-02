import json
import re
from pathlib import Path

import streamlit as st

from .user_data import read_user_data

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


def parse_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    preamble = []
    sections = []
    current_title = None
    current_lines = []

    for line in lines:
        heading = SECTION_HEADING.match(line)
        if heading is None:
            current_lines.append(line)
            continue
        if current_title is None:
            preamble = current_lines
        else:
            sections.append((current_title, current_lines))
        current_title = heading.group(1)
        current_lines = []

    if current_title is None:
        preamble = current_lines
    else:
        sections.append((current_title, current_lines))
    return preamble, sections


def save_publication_settings(settings: dict[str, bool]) -> None:
    dm_file, dm_data = read_user_data("dm")
    dm_data["public_sections"] = settings
    dm_file.write_text(
        json.dumps(dm_data, indent=2) + "\n",
        encoding="utf-8",
    )


@st.fragment(run_every=10)
def render_public_tab(is_dm: bool = False):
    public_page_file = PUBLIC_DATA_DIR / "public.md"
    try:
        public_page = public_page_file.read_text(encoding="utf-8")
    except OSError as error:
        st.error(f"Could not read {public_page_file.name}: {error}")
        return

    preamble, sections = parse_sections(public_page.splitlines())
    render_markdown_content(preamble)

    try:
        _, dm_data = read_user_data("dm")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        st.error(f"Could not load publication settings: {error}")
        return
    publication_settings = dm_data.get("public_sections", {})
    if not isinstance(publication_settings, dict) or not all(
        isinstance(key, str) and isinstance(value, bool)
        for key, value in publication_settings.items()
    ):
        st.error("DM publication settings must map section names to true/false.")
        return

    for title, section_lines in sections:
        visible = publication_settings.get(title, True)
        if is_dm:
            key = f"publish_section_{title}"
            if key not in st.session_state:
                st.session_state[key] = visible
            visible = st.checkbox(
                f"Show “{title}” to players",
                key=key,
            )
        if not is_dm and not visible:
            continue
        with st.expander(title, expanded=False):
            render_markdown_content(section_lines)

    if is_dm and st.button("Save publication settings"):
        updated_settings = {
            title: st.session_state[f"publish_section_{title}"]
            for title, _ in sections
        }
        try:
            save_publication_settings(updated_settings)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            st.error(f"Could not save publication settings: {error}")
        else:
            st.success("Publication settings saved.")
