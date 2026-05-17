import streamlit as st
import pandas as pd
import plotly.express as px

from openai import OpenAI
from dotenv import load_dotenv
import json
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -----------------------------
# SESSION STATE INIT
# -----------------------------
if "df" not in st.session_state:
    st.session_state.df = None

if "raw_df" not in st.session_state:
    st.session_state.raw_df = None


# -----------------------------
# UTILITY FUNCTIONS
# -----------------------------

def urgency_color(urgency):
    """Only call this on raw urgency strings (Low / Medium / High)."""
    if urgency == "High":
        return "🔴 High"
    elif urgency == "Medium":
        return "🟡 Medium"
    else:
        return "🟢 Low"


def assign_action(category, urgency):
    """Rule engine — separated into its own function for clarity."""
    if category == "Complaint" and urgency == "High":
        return "ESCALATE TO MANAGER"
    elif category == "Payment" and urgency == "High":
        return "URGENT FINANCE REVIEW"
    elif category == "Booking":
        return "SEND TO FRONT DESK"
    elif category == "Praise":
        return "NO ACTION REQUIRED - OPTIONAL RESPONSE"
    else:
        return "STANDARD PROCESSING"


# -----------------------------
# AI PROCESSING FUNCTION
# -----------------------------

def process_emails(df):
    results = []
    progress_bar = st.progress(0)                          # FIX: progress feedback
    total = len(df)

    for i, (index, row) in enumerate(df.iterrows()):
        email_body = row["body"]

        # FIX: wrap API call in try/except — malformed JSON won't crash the whole run
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",                       # FIX: correct model name (was gpt-4.1-mini)
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": f"""
                            You are an email classification system.

                            You MUST return ONLY raw JSON.

                            STRICT RULES:
                            - Do NOT use markdown
                            - Do NOT use ``` or ```json
                            - Do NOT add explanations
                            - Do NOT add any extra text
                            - Output must start with {{ and end with }}

                        FORMAT:
                        {{
                        "category": "Complaint | Booking | Payment | Praise | Other",
                        "urgency": "Low | Medium | High",
                        "summary": "one sentence only"
                        }}

                        Email:
                        {email_body}
                        """
                    }
                ]
            )

            raw_content = response.choices[0].message.content.strip()
            result = json.loads(raw_content)

            # Validate expected keys exist
            category = result.get("category", "Other")
            urgency = result.get("urgency", "Low")
            summary = result.get("summary", "No summary returned.")

        except json.JSONDecodeError:
            # FIX: graceful fallback if JSON is malformed
            category = "Other"
            urgency = "Low"
            summary = "⚠️ AI returned unparseable response — manual review needed."

        except Exception as e:
            # FIX: catch any other API errors (rate limits, network, etc.)
            category = "Other"
            urgency = "Low"
            summary = f"⚠️ API error: {str(e)}"

        action = assign_action(category, urgency)

        results.append({
            "email": email_body,
            "category": category,
            "urgency": urgency,              # stored as raw string (Low/Medium/High)
            "summary": summary,
            "action": action,
            "status": "Open",
            "notes": ""
        })

        progress_bar.progress((i + 1) / total)

    progress_bar.empty()
    return pd.DataFrame(results)


# -----------------------------
# UI HEADER
# -----------------------------
st.title("📧 AI Email Organizer Dashboard")


# -----------------------------
# FILE UPLOAD
# -----------------------------
uploaded_file = st.file_uploader(
    "Upload Email CSV",
    type=["csv"],
    key="file_uploader"
)

if uploaded_file is not None:

    raw_df = pd.read_csv(uploaded_file)

    # FIX: validate CSV has required column before doing anything
    if "body" not in raw_df.columns:
        st.error("❌ Your CSV must contain a 'body' column. Please check the file and re-upload.")
        st.stop()

    st.session_state.raw_df = raw_df
    st.success("CSV uploaded successfully!")
    st.dataframe(raw_df)

    # -----------------------------
    # FIX: single process button — removed duplicate "Re-run" button
    # The button now always re-runs, so it serves both purposes
    # -----------------------------
    if st.button("⚡ Process Emails with AI"):
        with st.spinner("Processing emails..."):
            st.session_state.df = process_emails(st.session_state.raw_df)
        st.success("AI processing complete!")

else:
    st.warning("Please upload a CSV file.")


# -----------------------------
# FIX: early exit BEFORE tabs are defined, not inside nested blocks.
# This prevents st.stop() from killing partially-rendered UI.
# -----------------------------
if st.session_state.df is None:
    if uploaded_file is not None:
        st.info("Click 'Process Emails with AI' to begin.")
    st.stop()


# -----------------------------
# LOAD DATA FROM SESSION
# -----------------------------
df = st.session_state.df


# -----------------------------
# SIDEBAR FILTERS
# -----------------------------
st.sidebar.header("Filters")

category_filter = st.sidebar.selectbox(
    "Category",
    ["All"] + sorted(df["category"].unique())
)

urgency_filter = st.sidebar.selectbox(
    "Urgency",
    ["All"] + sorted(df["urgency"].unique())
)


# -----------------------------
# SEARCH + FILTERS
# -----------------------------
search_query = st.text_input("🔍 Search emails")

filtered_df = df.copy()

if search_query.strip():
    filtered_df = filtered_df[
        filtered_df["email"].fillna("").str.contains(search_query, case=False, na=False)
        | filtered_df["summary"].fillna("").str.contains(search_query, case=False, na=False)
    ]

if category_filter != "All":
    filtered_df = filtered_df[filtered_df["category"] == category_filter]

if urgency_filter != "All":
    filtered_df = filtered_df[filtered_df["urgency"] == urgency_filter]


# FIX: define ONE display_df for rendering with emoji urgency.
# All logic (filtering, comparisons) uses filtered_df with raw string values.
# urgency_color() is only applied here — never again inside tabs.
display_df = filtered_df.copy()
display_df["urgency"] = display_df["urgency"].apply(urgency_color)


# -----------------------------
# TABS
# -----------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📥 Emails",
    "🚨 High Priority",
    "📊 Overview",
    "📂 Case View"
])


# -----------------------------
# TAB 1 — MAIN TABLE
# -----------------------------
with tab1:
        st.subheader("All Emails")
 
        render_df = display_df.copy()
    
        st.dataframe(
            render_df,
            use_container_width=True,
            column_config={
                "email": st.column_config.TextColumn(
                    "Email",
                    width="large",
                    help="Full email body"
                ),
                "summary": st.column_config.TextColumn(
                    "Summary",
                    width="medium"
                ),
                "action": st.column_config.TextColumn(
                    "Action",
                    width="medium"
                ),
                "category": st.column_config.TextColumn(
                    "Category",
                    width="small"
                ),
                "urgency": st.column_config.TextColumn(
                    "Urgency",
                    width="small"
                ),
                "status": st.column_config.TextColumn(
                    "Status",
                    width="small"
                ),
                "notes": st.column_config.TextColumn(
                    "Notes",
                    width="medium"
                ),
            }
        )
 
        csv = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Filtered Results",
            data=csv,
            file_name="filtered_emails.csv",
            mime="text/csv"
        )



# -----------------------------
# TAB 2 — HIGH PRIORITY
# FIX: use raw df with raw urgency string for filtering
# -----------------------------
with tab2:
    st.subheader("🚨 High Priority Emails")

    high_priority_raw = df[df["urgency"] == "High"].copy()

    if high_priority_raw.empty:
        st.info("No high priority emails found.")
    else:
        high_priority_display = high_priority_raw.copy()
        high_priority_display["urgency"] = high_priority_display["urgency"].apply(urgency_color)
        st.dataframe(high_priority_display, use_container_width=True)


# -----------------------------
# TAB 3 — OVERVIEW
# -----------------------------
with tab3:
    st.subheader("📊 Overview")

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Emails", len(df))
    col2.metric("High Urgency", len(df[df["urgency"] == "High"]))
    col3.metric("Complaints", len(df[df["category"] == "Complaint"]))

    st.subheader("📊 Category Breakdown")
    category_counts = filtered_df["category"].value_counts().reset_index()
    category_counts.columns = ["category", "count"]
    fig1 = px.bar(category_counts, x="category", y="count", title="Emails by Category")
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("🚨 Urgency Breakdown")
    urgency_counts = filtered_df["urgency"].value_counts().reset_index()
    urgency_counts.columns = ["urgency", "count"]
    fig2 = px.pie(urgency_counts, names="urgency", values="count", title="Email Urgency Distribution")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("📌 Live Insight")

    if filtered_df.empty:
        st.info("No emails match the current filters.")
    else:
        st.info(
            f"""
            Showing {len(filtered_df)} filtered emails  
            - Top category: {filtered_df['category'].value_counts().idxmax()}  
            - High urgency: {len(filtered_df[filtered_df['urgency'] == 'High'])}  
            - Complaints: {len(filtered_df[filtered_df['category'] == 'Complaint'])}
            """
        )

    st.subheader("🧠 Smart Insights")
    most_common_category = df["category"].value_counts().idxmax()
    most_common_urgency = df["urgency"].value_counts().idxmax()
    high_count = len(df[df["urgency"] == "High"])

    st.success(f"""
    📌 Most common issue: {most_common_category}  
    ⚠️ Most frequent urgency level: {most_common_urgency}  
    🚨 Total high urgency emails: {high_count}
    """)


# -----------------------------
# TAB 4 — CASE VIEW
# FIX: use filtered_df (raw values) for all logic here.
# urgency_color() called once at display time only — not on already-emoji strings.
# -----------------------------
with tab4:
    st.subheader("📂 Email Case View")

    if filtered_df.empty:
        st.info("No emails match the current filters.")
    else:
        selected_email = st.selectbox(
            "Select an email to inspect",
            filtered_df["email"]
        )

        selected_row = filtered_df[filtered_df["email"] == selected_email].iloc[0]

        st.write("### Email Content")
        st.write(selected_row["email"])

        st.write("### AI Classification")
        st.write("Category:", selected_row["category"])
        st.write("Urgency:", urgency_color(selected_row["urgency"]))   # raw string → safe to call here

        st.write("### Summary")
        st.write(selected_row["summary"])

        st.write("### Recommended Action")
        st.success(selected_row["action"])

        st.write("### Update Status")
        new_status = st.selectbox(
            "Change status",
            ["Open", "In Progress", "Resolved"],
            index=["Open", "In Progress", "Resolved"].index(selected_row["status"])
        )

        if st.button("Update Status"):
            df.loc[df["email"] == selected_row["email"], "status"] = new_status
            st.session_state.df = df
            st.success(f"Status updated to: {new_status}")
            st.rerun()

        st.write("### Notes")
        new_note = st.text_area("Add or update notes", value=selected_row["notes"])

        if st.button("Save Notes"):
            df.loc[df["email"] == selected_row["email"], "notes"] = new_note
            st.session_state.df = df
            st.success("Notes updated successfully!")
            st.rerun()