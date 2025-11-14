import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os

st.set_page_config(
    page_title="FinPal - Finance Dashboard",
    page_icon="🪙",
    layout="wide"
)

category_file = "categories.json"

# ---------- CATEGORY STATE & PERSISTENCE ----------
if "categories" not in st.session_state:
    st.session_state.categories = {"Uncategorized": []}

if os.path.exists(category_file):
    with open(category_file, "r") as f:
        st.session_state.categories = json.load(f)


def save_categories():
    with open(category_file, "w") as f:
        json.dump(st.session_state.categories, f)


# ---------- HELPERS ----------
def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df["Category"] = "Uncategorized"

    for category, keywords in st.session_state.categories.items():
        if category == "Uncategorized" or not keywords:
            continue

        lowered_keywords = [keyword.lower().strip() for keyword in keywords]

        for idx, row in df.iterrows():
            details = str(row["Details"]).lower().strip()
            # Exact match on full details string; you can later improve to "contains"
            if details in lowered_keywords:
                df.at[idx, "Category"] = category

    return df


def load_transactions(file):
    try:
        df = pd.read_csv(file)
        df.columns = [col.strip() for col in df.columns]

        # Clean amount
        df["Amount"] = (
            df["Amount"].astype(str).str.replace(
                ",", "", regex=False).astype(float)
        )

        # Parse date
        df["Date"] = pd.to_datetime(
            df["Date"], format="%d %b %Y", errors="coerce")
        df = df.dropna(subset=["Date"])

        return categorize_transactions(df)

    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None


def add_keyword_to_category(category, keyword):
    keyword = keyword.strip()
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False


# ---------- MAIN APP ----------
def main():
    st.title("FinPal 💰 – Your Personal Finance Dashboard")

    uploaded_file = st.file_uploader(
        "Upload your Bank Statement Transaction CSV file here:",
        type=["csv"]
    )

    if uploaded_file is None:
        st.info("Please upload a CSV file to get started.")
        return

    df = load_transactions(uploaded_file)
    if df is None:
        return

    # Split debits and credits
    debits_df = df[df["Debit/Credit"] == "Debit"].copy()
    credits_df = df[df["Debit/Credit"] == "Credit"].copy()

    st.session_state.debits_df = debits_df.copy()
    st.session_state.credits_df = credits_df.copy()

    # ---------- GLOBAL SUMMARY ----------
    total_debits = debits_df["Amount"].sum()
    total_credits = credits_df["Amount"].sum()
    net_cash_flow = total_credits - total_debits

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Expenses (Debit)", f"{total_debits:,.2f} CAD")
    c2.metric("Total Payments (Credit)", f"{total_credits:,.2f} CAD")
    c3.metric(
        "Net Cash Flow",
        f"{net_cash_flow:,.2f} CAD",
        help="Credit - Debit"
    )

    st.markdown("---")

    tab1, tab2 = st.tabs(["💸 Expenses (Debit)", "💳 Payments (Credit)"])

    # ---------- EXPENSES TAB ----------
    with tab1:
        st.subheader("Categories & Rules")

        col_cat1, col_cat2 = st.columns([2, 3])

        with col_cat1:
            new_category = st.text_input("New Category Name:")
            add_button = st.button("Add Category")

            if add_button and new_category:
                if new_category not in st.session_state.categories:
                    st.session_state.categories[new_category] = []
                    save_categories()
                    st.rerun()

        # with col_cat2:
        #    st.write("Existing categories:", ", ".join(
        #        st.session_state.categories.keys()))'''

        st.subheader("Your Expenses")

        edited_df = st.data_editor(
            st.session_state.debits_df[[
                "Date", "Details", "Amount", "Category"]],
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f CAD"),
                "Category": st.column_config.SelectboxColumn(
                    "Category",
                    options=list(st.session_state.categories.keys())
                )
            },
            hide_index=True,
            use_container_width=True,
            key="category_editor"
        )

        save_button = st.button("Apply Changes", type="primary")
        if save_button:
            for idx, row in edited_df.iterrows():
                new_category_value = row["Category"]
                if new_category_value == st.session_state.debits_df.at[idx, "Category"]:
                    continue

                details = row["Details"]
                st.session_state.debits_df.at[idx,
                                              "Category"] = new_category_value
                add_keyword_to_category(new_category_value, details)

        # Recompute summary after edits
        debits_df = st.session_state.debits_df.copy()

        st.subheader("Expense Summary by Category")
        category_totals = debits_df.groupby(
            "Category")["Amount"].sum().reset_index()
        category_totals = category_totals.sort_values(
            "Amount", ascending=False)

        st.dataframe(
            category_totals,
            column_config={
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f CAD")
            },
            use_container_width=True,
            hide_index=True
        )

        col_pie, col_bar = st.columns(2)

        # Pie chart
        with col_pie:
            fig_pie = px.pie(
                category_totals,
                values="Amount",
                names="Category",
                title="Expenses by Category"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # 🔥 NEW: Top merchants bar chart
        with col_bar:
            top_merchants = (
                debits_df.groupby("Details")["Amount"]
                .sum()
                .reset_index()
                .sort_values("Amount", ascending=False)
                .head(10)
            )
            fig_merchants = px.bar(
                top_merchants,
                x="Details",
                y="Amount",
                title="Top 10 Expense Merchants",
            )
            fig_merchants.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_merchants, use_container_width=True)

        # 🔥 NEW: Expenses over time (line chart)
        st.subheader("Monthly Expenses Over Time")
        daily_spend = (
            debits_df.groupby("Date")["Amount"]
            .sum()
            .reset_index()
            .sort_values("Date")
        )
        fig_time = px.line(
            daily_spend,
            x="Date",
            y="Amount",
            title="Monthly Daily Total Expenses:"
        )
        st.plotly_chart(fig_time, use_container_width=True)

        # 🔥 NEW: Monthly expenses by category (stacked bar)
        st.subheader("Monthly Expenses by Category")
        debits_df["YearMonth"] = debits_df["Date"].dt.to_period(
            "M").astype(str)
        monthly_cat = (
            debits_df
            .groupby(["YearMonth", "Category"])["Amount"]
            .sum()
            .reset_index()
        )
        fig_monthly = px.bar(
            monthly_cat,
            x="YearMonth",
            y="Amount",
            color="Category",
            title="Expenses by Category Every Month:",
            barmode="stack"
        )
        fig_monthly.update_layout(xaxis_title="Month")
        st.plotly_chart(fig_monthly, use_container_width=True)

    # ---------- PAYMENTS TAB ----------
    with tab2:
        st.subheader("Payments Summary")

        total_payments = credits_df["Amount"].sum()
        st.metric("Total Payments", f"{total_payments:,.2f} CAD")

        edited_credit_df = st.data_editor(
            st.session_state.credits_df[[
                "Date", "Details", "Amount"]],
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f CAD")
                # "Category": st.column_config.SelectboxColumn(
                #    "Category",
                #    options=list(st.session_state.categories.keys())
                # )
            },
            hide_index=True,
            use_container_width=True,
            key="category_credit_editor"
        )

        # 🔥 NEW: Visuals for credits
        credits_df = edited_credit_df.copy()
        st.subheader("Payments Over Time")
        daily_income = (
            credits_df.groupby("Date")["Amount"]
            .sum()
            .reset_index()
            .sort_values("Date")
        )
        fig_income_time = px.line(
            daily_income,
            x="Date",
            y="Amount",
            title="Monthly Daily Total Payments:"
        )
        st.plotly_chart(fig_income_time, use_container_width=True)

        # st.subheader("Payments by Category")
        # income_cat = credits_df.groupby(
        #    "Category")["Amount"].sum().reset_index()
        # fig_income_cat = px.bar(
        #    income_cat,
        #    x="Category",
        #    y="Amount",
        #    title="Payments by Category"
        # )
        # st.plotly_chart(fig_income_cat, use_container_width=True)


main()
