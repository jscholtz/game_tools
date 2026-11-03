import streamlit as st
from pymongo.errors import PyMongoError

from .database import load_private_data


def render_character_tab(username: str):
    try:
        user_data = load_private_data(username)
    except FileNotFoundError:
        st.error(f"User data not found for {username}.")
    except PyMongoError as error:
        st.error(f"Could not load character data: {error}")
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
