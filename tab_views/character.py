import json

import streamlit as st

from .user_data import DATA_DIR


def render_character_tab(username: str):
    user_data_file = DATA_DIR / f"{username}.json"
    try:
        with user_data_file.open(encoding="utf-8") as file:
            user_data = json.load(file)
    except FileNotFoundError:
        st.error(f"User data file not found: {user_data_file.name}")
    except json.JSONDecodeError as error:
        st.error(f"Invalid JSON in {user_data_file.name}: {error}")
    except OSError as error:
        st.error(f"Could not read {user_data_file.name}: {error}")
    else:
        if "character" in user_data:
            with st.container(border=True):
                st.subheader("Character Data")
                st.title(user_data["character"])
                st.markdown(
                    f"**Level {user_data['level']} {user_data['race']} "
                    f"{user_data['class']}**"
                )
                if "gender" in user_data:
                    st.caption(user_data["gender"])

                stats = []
                if "passive_perception" in user_data:
                    stats.append(("Passive Perception", user_data["passive_perception"]))
                if "insight" in user_data:
                    stats.append(("Insight", f"{user_data['insight']:+}"))
                if stats:
                    stat_columns = st.columns(len(stats))
                    for column, (label, value) in zip(stat_columns, stats):
                        column.metric(label, value)
        elif "text" in user_data:
            with st.container(border=True):
                st.subheader("Character Data")
                st.write(user_data["text"])
