from datetime import datetime
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

def render(db_path: str, dept_list: list):
    st.subheader("💬 Share Your Experience & Patient Feedback")
    fb_left, fb_right = st.columns((1, 1.1), gap="large")
    with fb_left:
        with st.form("patient_feedback_form", clear_on_submit=True):
            fb_name = st.text_input("Your Name", placeholder="e.g. Ananya Verma")
            fb_dept = st.selectbox("Department / Service Visited", ["General / Tele-Health Experience", "In-Hospital Surgical & Nursing Care"] + dept_list)
            fb_rating = st.slider("Overall Satisfaction Rating (1 = Poor, 5 = Excellent)", min_value=1, max_value=5, value=5)
            fb_comments = st.text_area("Your Comments or Suggestions", placeholder="Tell us about your OPD, online consultation, surgical care, or nursing support...", height=110)
            if st.form_submit_button("📩 Submit Feedback", type="primary"):
                if not fb_name.strip() or not fb_comments.strip():
                    st.error("Please enter your name and feedback comments.")
                else:
                    conn = sqlite3.connect(db_path)
                    conn.execute(
                        "INSERT INTO feedback (patient_name, department, rating, comments, submitted_at) VALUES (?, ?, ?, ?, ?)",
                        (fb_name.strip(), fb_dept, int(fb_rating), fb_comments.strip(), datetime.now().strftime("%Y-%m-%d %H:%M"))
                    )
                    conn.commit()
                    conn.close()
                    st.success("🙏 Thank you! Your feedback has been recorded for our Quality Assurance team.")
                    st.rerun()

    with fb_right:
        st.markdown("#### ⭐ Recent Patient Testimonials")
        conn = sqlite3.connect(db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                department TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comments TEXT NOT NULL,
                submitted_at TEXT NOT NULL
            )
        ''')
        conn.commit()
        fb_df = pd.read_sql_query("SELECT patient_name, department, rating, comments, submitted_at FROM feedback ORDER BY id DESC LIMIT 6", conn)
        conn.close()
        if fb_df.empty:
            st.info("Be the first to share feedback about your consultation experience!")
        else:
            rating_counts = fb_df["rating"].value_counts().reset_index()
            rating_counts.columns = ["Rating", "Count"]
            rating_counts["Rating"] = rating_counts["Rating"].astype(str) + " ⭐"
            fig_ratings = px.pie(
                rating_counts,
                names="Rating",
                values="Count",
                hole=0.5,
                title="Patient Satisfaction Distribution",
                color_discrete_sequence=px.colors.sequential.Tealgrn
            )
            fig_ratings.update_layout(height=260, margin=dict(t=40, b=10, l=10, r=10))
            st.plotly_chart(fig_ratings, use_container_width=True)

            for row in fb_df.to_dict("records"):
                stars = "⭐" * int(row["rating"])
                with st.container(border=True):
                    st.markdown(f"**{row['patient_name']}** • *{row['department']}* — {stars}")
                    st.write(row["comments"])
                    st.caption(f"Submitted on {row['submitted_at']}")
