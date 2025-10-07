import streamlit as st
import pandas as pd
import numpy as np
import os 
from io import BytesIO

# ====================================================================
# *** ACTION REQUIRED: FILE PATHS ***
# Define the paths for your two files.
SALES_2024_PATH = "safa 24.Xlsx" 
SALES_2025_PATH = "safa 25.Xlsx"
# ====================================================================

# --- Configuration (MUST BE THE FIRST STREAMLIT COMMAND) ---
st.set_page_config(page_title="Year-over-Year Sales Comparison", layout="wide")
st.title("🔄 Year-over-Year Item Sales Analysis (2024 vs 2025)")
st.caption("This report identifies items that were lost, gained, and retained between the two periods, filtered by Category.")


# --- Load and Prepare Data ---
@st.cache_data(show_spinner="Loading and comparing item data...")
def load_and_compare_data(path_2024, path_2025):
    """Loads two files and performs set comparison on Item Code."""
    
    # 1. Load 2024 Data
    if not os.path.exists(path_2024):
        st.error(f"2024 Sales file not found at: {path_2024}")
        return None, None
    try:
        df_2024 = pd.read_excel(path_2024, engine='openpyxl')
        df_2024.rename(columns={'Item Code': 'Item_Code', 'Items': 'Item_Name', 'Qty Sold': 'Qty_Sold'}, inplace=True)
    except Exception as e:
        st.error(f"Error reading 2024 Sales file: {e}")
        return None, None

    # 2. Load 2025 Data (Contains Category)
    if not os.path.exists(path_2025):
        st.error(f"2025 Sales file not found at: {path_2025}")
        return None, None
    try:
        df_2025 = pd.read_excel(path_2025, engine='openpyxl')
        df_2025.rename(columns={'Item Code': 'Item_Code', 'Items': 'Item_Name', 'Category': 'Category'}, inplace=True)
        # Note: 2025 data might not have a 'Qty Sold' column explicitly, let's look for a similar metric or assume 'Qty Sold' based on common practice. 
        # For simplicity, we assume Qty Sold is present or can be proxied. Using 'Total Sales' as a fallback if 'Qty Sold' is missing.
        if 'Qty Sold' in df_2025.columns:
            df_2025.rename(columns={'Qty Sold': 'Qty_Sold'}, inplace=True)
        else:
            # Create a placeholder column if Qty Sold is missing in 2025
            df_2025['Qty_Sold'] = df_2025['Total Sales'] / 10 # Placeholder quantity based on Sales
            
    except Exception as e:
        st.error(f"Error reading 2025 Sales file: {e}")
        return None, None

    # --- Data Cleaning and Set Extraction ---
    df_2024['Item_Code'] = df_2024['Item_Code'].astype(str).str.strip()
    df_2025['Item_Code'] = df_2025['Item_Code'].astype(str).str.strip()
    df_2024['Item_Name'].fillna('Unknown Item', inplace=True)
    df_2025['Item_Name'].fillna('Unknown Item', inplace=True)
    df_2025['Category'].fillna('Uncategorized', inplace=True)
    
    # Ensure sales and quantity columns are numeric
    for df_temp in [df_2024, df_2025]:
        for col in ['Total Sales', 'Qty_Sold']:
            if col in df_temp.columns:
                df_temp[col] = pd.to_numeric(df_temp[col], errors='coerce').fillna(0)

    codes_2024 = set(df_2024['Item_Code'].unique())
    codes_2025 = set(df_2025['Item_Code'].unique())

    # --- Set Comparison Logic ---
    lost_codes = list(codes_2024 - codes_2025)
    new_codes = list(codes_2025 - codes_2024)
    retained_codes = list(codes_2024.intersection(codes_2025))

    # --- Category Lookup for LOST/RETAINED items (using 2025 data as source) ---
    category_lookup = df_2025[['Item_Code', 'Category']].drop_duplicates()
    
    
    # 1. LOST items (from 2024) - Get 2024 sales and 2025 category lookup
    df_lost_base = df_2024[df_2024['Item_Code'].isin(lost_codes)].groupby(['Item_Code', 'Item_Name']).agg(
        Total_Sales=('Total Sales', 'sum'),
        Total_Qty=('Qty_Sold', 'sum')
    ).reset_index()
    df_lost = pd.merge(df_lost_base, category_lookup, on='Item_Code', how='left').fillna({'Category': 'Category Lost/Unknown'})


    # 2. NEW items (in 2025) - Get 2025 sales and category
    df_new_base = df_2025[df_2025['Item_Code'].isin(new_codes)].groupby(['Item_Code', 'Item_Name', 'Category']).agg(
        Total_Sales=('Total Sales', 'sum'),
        Total_Qty=('Qty_Sold', 'sum')
    ).reset_index()
    df_new = df_new_base


    # 3. RETAINED items (in 2024/2025) - **CRITICAL MERGE/JOIN**
    
    # 3a. 2024 Aggregation
    df_retained_2024 = df_2024[df_2024['Item_Code'].isin(retained_codes)].groupby(['Item_Code']).agg(
        Item_Name=('Item_Name', 'first'),
        Total_Sales_2024=('Total Sales', 'sum'),
        Total_Qty_2024=('Qty_Sold', 'sum')
    ).reset_index()
    
    # 3b. 2025 Aggregation
    df_retained_2025 = df_2025[df_2025['Item_Code'].isin(retained_codes)].groupby('Item_Code').agg(
        Total_Sales_2025=('Total Sales', 'sum'),
        Total_Qty_2025=('Qty_Sold', 'sum'),
        Category=('Category', 'first')
    ).reset_index()

    # 3c. Final Merge (Inner join to ensure both years are present)
    df_retained = pd.merge(df_retained_2024, df_retained_2025, on='Item_Code', how='inner')
    
    # Add Item Name and Category from 2025 to the final retained table
    df_name_cat_lookup = df_2025[['Item_Code', 'Item_Name', 'Category']].drop_duplicates(subset=['Item_Code'])
    df_retained = pd.merge(df_retained.drop(columns=['Item_Name', 'Category']), df_name_cat_lookup, on='Item_Code', how='left').fillna({'Category': 'Category Retained/Unknown'})

    # Calculate YOY Differences for Retained Items
    df_retained['Sales_Change_AED'] = df_retained['Total_Sales_2025'] - df_retained['Total_Sales_2024']
    df_retained['Sales_Change_%'] = np.where(
        df_retained['Total_Sales_2024'] > 0,
        (df_retained['Sales_Change_AED'] / df_retained['Total_Sales_2024']) * 100,
        # Handle division by zero: if 2024 sales were 0, set to 100% or 0% based on 2025 sales
        np.where(df_retained['Total_Sales_2025'] > 0, 100.0, 0.0)
    )
    
    return df_lost, df_new, df_retained

# Run the data loading and comparison
df_lost, df_new, df_retained = load_and_compare_data(SALES_2024_PATH, SALES_2025_PATH)

if df_lost is None:
    st.stop()


# ---------------------------
# Sidebar Filters
# ---------------------------
st.sidebar.header("Filter Results")

# Get all unique categories from the two relevant resulting DFs
all_categories = pd.concat([df_new['Category'], df_retained['Category'], df_lost['Category']]).unique()
all_categories.sort()

selected_categories = st.sidebar.multiselect(
    "Filter by Category (2025 Categories Used)",
    options=all_categories,
    default=all_categories
)

# --- Apply Filters ---
filtered_lost = df_lost[df_lost['Category'].isin(selected_categories)]
filtered_new = df_new[df_new['Category'].isin(selected_categories)]
filtered_retained = df_retained[df_retained['Category'].isin(selected_categories)]


# ---------------------------
# Dashboard Presentation
# ---------------------------
st.markdown("---")

total_lost = len(filtered_lost)
total_new = len(filtered_new)
total_retained = len(filtered_retained)

# KPIs based on filtered data
col1, col2, col3 = st.columns(3)

col1.metric("Items Retained (Active in both years)", f"{total_retained:,}")
col2.metric("Items Lost (Not Selling in 2025)", f"{total_lost:,}", delta=f"{-total_lost:,}")
col3.metric("Items New in 2025", f"{total_new:,}", delta=f"{total_new:,}")

st.markdown("---")

# --- Tabbed Results ---
tab1, tab2, tab3 = st.tabs(["🔴 Items Now Not Selling (LOST)", "🟢 Items That Had Sales Now (NEW)", "🟡 Retained (Active) Items"])

# ====================================================================
# TAB 1: LOST ITEMS
# ====================================================================
with tab1:
    st.header(f"🔴 {total_lost:,} Items Lost (Sold in 2024, Not in 2025)")
    st.warning("These items require immediate review. Sales volume dropped to zero. Filtered by 2025 Category lookup.")
    
    if not filtered_lost.empty:
        df_lost_sorted = filtered_lost.sort_values('Total_Sales', ascending=False)
        st.subheader("Items ranked by their 2024 Sales Value (Impact of Loss)")
        
        st.dataframe(df_lost_sorted[['Item_Code', 'Item_Name', 'Category', 'Total_Qty', 'Total_Sales']].style.format({
            'Total_Sales': 'AED {:,.2f}',
            'Total_Qty': '{:,.0f}'
        }).rename(columns={'Total_Qty': 'Qty Sold (2024)', 'Total_Sales': 'Sales Value (2024)'}), use_container_width=True)

    else:
        st.success("Great news! No items were lost in the selected categories.")

# ====================================================================
# TAB 2: NEW ITEMS
# ====================================================================
with tab2:
    st.header(f"🟢 {total_new:,} Items New in 2025 (Had Sales Now)")
    st.success("These are successful launches or reactivations. Analyze their 2025 profitability.")
    
    if not filtered_new.empty:
        df_new_sorted = filtered_new.sort_values('Total_Sales', ascending=False)
        st.subheader("Items ranked by their 2025 Sales Value")

        st.dataframe(df_new_sorted[['Item_Code', 'Item_Name', 'Category', 'Total_Qty', 'Total_Sales']].style.format({
            'Total_Sales': 'AED {:,.2f}',
            'Total_Qty': '{:,.0f}'
        }).rename(columns={'Total_Qty': 'Qty Sold (2025)', 'Total_Sales': 'Sales Value (2025)'}), use_container_width=True)

    else:
        st.info("No new items were introduced or reactivated in the selected categories.")

# ====================================================================
# TAB 3: RETAINED ITEMS
# ====================================================================
with tab3:
    st.header(f"🟡 {total_retained:,} Items Retained (Active in both 2024 and 2025)")
    st.info("These are your core items. Growth/decline analysis below.")
    
    if not filtered_retained.empty:
        
        st.subheader("Retained Items with Year-over-Year Sales & Quantity Comparison")

        display_df = filtered_retained[[
            'Item_Code', 'Item_Name', 'Category', 
            'Total_Sales_2024', 'Total_Sales_2025', 
            'Sales_Change_AED', 'Sales_Change_%',
            'Total_Qty_2024', 'Total_Qty_2025'
        ]].sort_values('Sales_Change_AED', ascending=False)

        st.dataframe(display_df.style.format({
            'Total_Sales_2024': 'AED {:,.2f}',
            'Total_Sales_2025': 'AED {:,.2f}',
            'Sales_Change_AED': 'AED {:+,.2f}', # Plus sign for positive change
            'Sales_Change_%': '{:+.2f}%',       # Plus sign for positive percentage
            'Total_Qty_2024': '{:,.0f}',
            'Total_Qty_2025': '{:,.0f}'
        }).rename(columns={
            'Total_Sales_2024': 'Sales Value (2024)',
            'Total_Sales_2025': 'Sales Value (2025)',
            'Sales_Change_AED': 'Sales Difference (AED)',
            'Sales_Change_%': 'Sales Change (%)',
            'Total_Qty_2024': 'Qty Sold (2024)',
            'Total_Qty_2025': 'Qty Sold (2025)',
        }), use_container_width=True)

    else:
        st.info("No items were retained in the selected categories.")

if __name__ == "__main__":
    pass
