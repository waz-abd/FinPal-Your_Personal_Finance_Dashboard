import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os

# Configure the Streamlit page (title, icon, layout)
st.set_page_config(
    page_title="FinPal - Finance Dashboard",
    page_icon="🪙",
    layout="wide"
)

# File used to persist category rules between sessions
category_file = "categories.json"

# Initialize category dictionary in session state
# This will hold category names and their associated keyword lists
if "categories" not in st.session_state:
    st.session_state.categories = {"Uncategorized": []}

# Load saved category configuration from disk, if it exists
if os.path.exists(category_file):
    with open(category_file, "r") as f:
        st.session_state.categories = json.load(f)


def save_categories():
    """
    Persist the current category configuration to disk.
    This allows category rules to be reused across app sessions.
    """
    with open(category_file, "w") as f:
        json.dump(st.session_state.categories, f)


def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign a category to each transaction based on user-defined keyword rules.

    The function looks at the 'Details' field and checks if it matches
    any of the stored keywords for each category. If a match is found,
    the transaction is assigned to that category; otherwise it defaults
    to 'Uncategorized'.
    """
    df["Category"] = "Uncategorized"

    for category, keywords in st.session_state.categories.items():
        # Skip the default bucket or categories without any keywords defined
        if category == "Uncategorized" or not keywords:
            continue

        lowered_keywords = [keyword.lower().strip() for keyword in keywords]

        # Match each row's Details against the keyword list for this category
        for idx, row in df.iterrows():
            details = str(row["Details"]).lower().strip()
            # Currently uses exact string matches; could be extended to "contains" logic
            if details in lowered_keywords:
                df.at[idx, "Category"] = category

    return df


def load_transactions(file):
    """
    Read, clean, and prepare the uploaded CSV file for analysis.

    Steps:
    - Read the CSV into a DataFrame
    - Standardize column names
    - Convert the Amount column to numeric
    - Parse the Date column to datetime
    - Drop rows with invalid dates
    - Apply transaction categorization rules
    """
    try:
        df = pd.read_csv(file)
        df.columns = [col.strip() for col in df.columns]

        # Remove thousands separators and convert Amount to float
        df["Amount"] = (
            df["Amount"].astype(str).str.replace(
                ",", "", regex=False).astype(float)
        )

        # Convert Date column to datetime and drop rows where parsing fails
        df["Date"] = pd.to_datetime(
            df["Date"], format="%d %b %Y", errors="coerce"
        )
        df = df.dropna(subset=["Date"])

        return categorize_transactions(df)

    except Exception as e:
        # Provide a clear error message to the user if parsing fails
        st.error(f"Error processing file: {str(e)}")
        return None


def add_keyword_to_category(category, keyword):
    """
    Add a new keyword to a given category and persist the update.

    This function supports the "teach the system" workflow:
    when a user assigns a category to a transaction, its Details
    can be stored as a keyword for automatic future categorization.
    """
    keyword = keyword.strip()
    if keyword and keyword not in st.session_state.categories[category]:
        st.session_state.categories[category].append(keyword)
        save_categories()
        return True
    return False


def main():
    """
    Main entry point for the FinPal dashboard.

    Provides:
    - File upload for transaction CSVs
    - High-level summary metrics
    - Detailed views and visualizations for expenses and payments
    - Interactive tools to manage and refine category rules
    """
    st.title("FinPal 💰 – Your Personal Finance Dashboard")

    # File upload component for bank statement CSV
    uploaded_file = st.file_uploader(
        "Upload your Bank Statement Transaction CSV file here:",
        type=["csv"]
    )

    # If no file is uploaded, show an informational message and end execution
    if uploaded_file is None:
        st.info("Please upload a CSV file to get started.")
        return

    # Load and preprocess the data
    df = load_transactions(uploaded_file)
    if df is None:
        return

    # Split the data into expenses (Debits) and payments/income (Credits)
    debits_df = df[df["Debit/Credit"] == "Debit"].copy()
    credits_df = df[df["Debit/Credit"] == "Credit"].copy()

    # Store DataFrames in session state so they remain accessible after edits
    st.session_state.debits_df = debits_df.copy()
    st.session_state.credits_df = credits_df.copy()

    # Calculate headline financial metrics
    total_debits = debits_df["Amount"].sum()
    total_credits = credits_df["Amount"].sum()
    net_cash_flow = total_credits - total_debits

    # Display high-level metrics in three columns
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Expenses (Debit)", f"{total_debits:,.2f} CAD")
    c2.metric("Total Payments (Credit)", f"{total_credits:,.2f} CAD")
    c3.metric(
        "Net Cash Flow",
        f"{net_cash_flow:,.2f} CAD",
        help="Calculated as Credit - Debit"
    )

    st.markdown("---")

    # Create two tabs: one focused on expenses, one on payments
    tab1, tab2 = st.tabs(["💸 Expenses (Debit)", "💳 Payments (Credit)"])

    # Expenses tab: category management, transaction editing, and expense analytics
    with tab1:
        st.subheader("Categories and Rules")

        col_cat1, col_cat2 = st.columns([2, 3])

        # Left column: define new categories
        with col_cat1:
            new_category = st.text_input("New Category Name:")
            add_button = st.button("Add Category")

            if add_button and new_category:
                if new_category not in st.session_state.categories:
                    st.session_state.categories[new_category] = []
                    save_categories()
                    # Rerun to refresh dropdowns and state after adding a new category
                    st.rerun()

        # Main expense table with editable categories
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

        # Apply user edits and update category rules based on their changes
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

        # Refresh the local debits DataFrame after applying changes
        debits_df = st.session_state.debits_df.copy()

        # Aggregate expenses by category
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

        # Pie chart showing distribution of expenses across categories
        with col_pie:
            fig_pie = px.pie(
                category_totals,
                values="Amount",
                names="Category",
                title="Expenses by Category"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # Bar chart showing top merchants by total spend
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

        # Line chart of expenses over time, aggregated by date
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

        # Stacked bar chart of monthly expenses by category
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

    # Payments tab: focus on credits and inflows
    with tab2:
        st.subheader("Payments Summary")

        total_payments = credits_df["Amount"].sum()
        st.metric("Total Payments", f"{total_payments:,.2f} CAD")

        # Allow users to inspect and clean payment records
        edited_credit_df = st.data_editor(
            st.session_state.credits_df[["Date", "Details", "Amount"]],
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f CAD")
            },
            hide_index=True,
            use_container_width=True,
            key="category_credit_editor"
        )

        # Line chart of payments over time
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


# Run the application
main()
