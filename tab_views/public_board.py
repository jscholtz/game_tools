import re

import streamlit as st
from pymongo.errors import PyMongoError

from .database import (
    load_public_file,
    load_publication_settings,
    save_publication_settings as persist_publication_settings,
)

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
        try:
            image = load_public_file(image_name)
        except (FileNotFoundError, PyMongoError, ValueError) as error:
            st.error(f"Could not load {image_name}: {error}")
        else:
            if not isinstance(image, bytes):
                st.error(f"Image content for {image_name} must be binary.")
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


@st.fragment(run_every=10)
def render_public_tab(is_dm: bool = False):
    try:
        public_page = load_public_file("public.md")
    except (FileNotFoundError, PyMongoError, ValueError) as error:
        st.error(f"Could not load public.md: {error}")
        return
    if not isinstance(public_page, str):
        st.error("Public board content must be text.")
        return

    preamble, sections = parse_sections(public_page.splitlines())
    render_markdown_content(preamble)

    try:
        publication_settings = load_publication_settings()
    except (PyMongoError, ValueError) as error:
        st.error(f"Could not load publication settings: {error}")
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
            persist_publication_settings(updated_settings)
        except PyMongoError as error:
            st.error(f"Could not save publication settings: {error}")
        else:
            st.success("Publication settings saved.")
