import re
from pathlib import Path

import streamlit as st


PUBLIC_DATA_DIR = Path(__file__).parent.parent / "public_data"


@st.fragment(run_every=10)
def render_public_tab():
    public_page_file = PUBLIC_DATA_DIR / "public.md"
    try:
        public_page = public_page_file.read_text(encoding="utf-8")
    except OSError as error:
        st.error(f"Could not read {public_page_file.name}: {error}")
        return

    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    for line in public_page.splitlines():
        image_match = image_pattern.fullmatch(line.strip())
        if image_match is None:
            st.markdown(line)
            continue

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
