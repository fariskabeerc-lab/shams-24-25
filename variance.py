import streamlit as st
import pandas as pd
import numpy as np
import os 
import re 
from io import BytesIO

# ====================================================================
# ⚠️ ACTION REQUIRED: SET YOUR FILE PATHS HERE ⚠️
# Define the paths for your two files.
SALES_2024_PATH = "shams 24(2).Xlsx" 
SALES_2025_PATH = "shams 25.Xlsx" 
# ====================================================================

# --- Configuration (MUST BE THE FIRST STREAMLIT COMMAND) ---
st.set_page_config(page_title="Year-over-Year Sales Analysis", layout="wide")
st.title("📈 Year-over-Year Item Sales Analysis (2024 vs 2025)")
st.caption("This report compares item performance, identifying **Lost**, **New**, and **Retained** items, along with sales and quantity changes.")

# Helper function for aggressive Item Code cleaning
def clean_item_code(code_series):
    """Aggressively cleans the Item Code for consistent matching."""
    if code_series.empty:
        return code_series
    # Convert to string, strip spaces, convert to uppercase, remove non-alphanumeric chars
    code_series = code_series.astype(str).str.strip().str.upper()
    code_series = code_series.str.replace(r'[^A-Z0-9]', '', regex=True)
    return code_series

# New helper function for aggressive Sales column cleaning
def clean_sales_column(sales_series):
    """Aggressively cleans sales column by removing formatting and ensuring numeric type."""
    # Convert to string, strip spaces
    sales_series = sales_series.astype(str).str.strip()
    
    # Remove common non-numeric characters that interfere with pd.to_numeric
    # Specifically removing commas (thousands separator) and common currency symbols
    sales_series = sales_series.str.replace(r'[^\d\.\-]', '', regex=True)
    
    # Convert to numeric, coerce errors to NaN, fill NaN with 0, then cast to float
    cleaned_sales = pd.to_numeric(sales_series, errors='coerce').fillna(0).astype(float)
    return cleaned_sales

# --- Load and Prepare Data ---
@st.cache_data(show_spinner="Loading and comparing item data...")
def load_and_compare_data(path_2024, path_2025):
    """
    Loads two files, renames columns to a standard format, and performs set comparison on Item Code.
    """
    
    # --- 1. Load 2024 Data ---
    if not os.path.exists(path_2024):
        st.error(f"2024 Sales file not found at: {path_2024}")
        return None, None
    try:
        df_2024 = pd.read_excel(path_2024, engine='openpyxl')
        df_2024.rename(columns={
            'Item Code': 'Item_Code', 
            'Items': 'Item_Name', 
            'Qty Sold': 'Qty_Sold',
            'Total Sales': 'Total_Sales',
            'Category': 'Category' 
        }, inplace=True)
        if 'Category' not in df_2024.columns:
             df_2024['Category'] = 'Uncategorized (2024 Missing)'
    except Exception as e:
        st.error(f"Error reading 2024 Sales file: {e}")
        return None, None

    # --- 2. Load 2025 Data ---
    if not os.path.exists(path_2025):
        st.error(f"2025 Sales file not found at: {path_2025}")
        return None, None
    try:
        df_2025 = pd.read_excel(path_2025, engine='openpyxl')
        df_2025.rename(columns={
            'Item Code': 'Item_Code', 
            'Items': 'Item_Name', 
            'Qty Sold': 'Qty_Sold', 
            'Category': 'Category',
            'Total Sales': 'Total_Sales'
        }, inplace=True)
        if 'Category4' in df_2025.columns and 'Category' not in df_2025.columns:
            df_2025.rename(columns={'Category4': 'Category'}, inplace=True)
            
    except Exception as e:
        st.error(f"Error reading 2025 Sales file: {e}")
        return None, None

    # --- Data Cleaning and Validation ---
    
    # 1. AGGRESSIVE Item Code CLEANUP
    df_2024['Item_Code'] = clean_item_code(df_2024['Item_Code'])
    df_2025['Item_Code'] = clean_item_code(df_2025['Item_Code'])
    
    df_2024.dropna(subset=['Item_Code'], inplace=True)
    df_2025.dropna(subset=['Item_Code'], inplace=True)
    
    # 2. AGGRESSIVE SALES AND QTY CLEANUP (NEW STEP)
    for df_temp in [df_2024, df_2025]:
        # Clean Sales Column
        if 'Total_Sales' in df_temp.columns:
            df_temp['Total_Sales'] = clean_sales_column(df_temp['Total_Sales'])
        
        # Ensure Qty Sold is numeric (less aggressive cleaning needed here, usually just float conversion)
        if 'Qty_Sold' in df_temp.columns:
            df_temp['Qty_Sold'] = pd.to_numeric(df_temp['Qty_Sold'], errors='coerce').fillna(0).astype(float)


    # Other Cleanups
    df_2024['Item_Name'].fillna('Unknown Item', inplace=True)
    df_2025['Item_Name'].fillna('Unknown Item', inplace=True)
    df_2024['Category'].fillna('Uncategorized (Missing)', inplace=True) 
    df_2025['Category'].fillna('Uncategorized (Missing)', inplace=True) 
    

    # 3. Create Item Code Sets for comparison
    codes_2024 = set(df_2024['Item_Code'].unique())
    codes_2025 = set(df_2025['Item_Code'].unique())

    # --- Set Comparison Logic ---
    lost_codes = list(codes_2024 - codes_2025)
    new_codes = list(codes_2025 - codes_2024)
    retained_codes = list(codes_2024.intersection(codes_2025))

    # --- Category Lookup from 2024 for Lost Items ---
    category_lookup_2024 = df_2024[['Item_Code', 'Category']].drop_duplicates(subset=['Item_Code'])
    
    
    # 1. LOST items (from 2024)
    df_lost_base = df_2024[df_2024['Item_Code'].isin(lost_codes)].groupby(['Item_Code']).agg(
        Item_Name=('Item_Name', 'first'), 
        Total_Sales=('Total_Sales', 'sum'),
        Total_Qty=('Qty_Sold', 'sum')
    ).reset_index()
    
    df_lost = pd.merge(df_lost_base, category_lookup_2024, on='Item_Code', how='left')


    # 2. NEW items (in 2025)
    df_new_base = df_2025[df_2025['Item_Code'].isin(new_codes)].groupby(['Item_Code', 'Item_Name', 'Category']).agg(
        Total_Sales=('Total_Sales', 'sum'),
        Total_Qty=('Qty_Sold', 'sum')
    ).reset_index()
    df_new = df_new_base


    # 3. RETAINED items (in 2024/2025)
    
    # 2024 Aggregation 
    temp_df_2024_agg = df_2024[df_2024['Item_Code'].isin(retained_codes)].groupby(['Item_Code']).agg(
        Total_Sales_2024=('Total_Sales', 'sum'), 
        Total_Qty_2024=('Qty_Sold', 'sum')
    ).reset_index()
    
    # 2025 Aggregation (and Category pull)
    temp_df_2025_agg = df_2025[df_2025['Item_Code'].isin(retained_codes)].groupby('Item_Code').agg(
        Total_Sales_2025=('Total_Sales', 'sum'), 
        Total_Qty_2025=('Qty_Sold', 'sum'),
        Category=('Category', 'first')
    ).reset_index()

    # Final variables assigned correctly
    df_retained_2024 = temp_df_2024_agg 
    df_retained_2025 = temp_df_2025_agg 

    # Final Merge 
    df_retained = pd.merge(df_retained_2024, df_retained_2025, on='Item_Code', how='inner')
    
    # Get Item Name (using 2025 name is generally safer for consistency)
    df_name_lookup = df_2025[['Item_Code', 'Item_Name']].drop_duplicates(subset=['Item_Code'])
    df_retained = pd.merge(df_retained, df_name_lookup, on='Item_Code', how='left')

    # Calculate YOY Differences for Retained Items
    df_retained['Sales_Change_AED'] = df_retained['Total_Sales_2025'] - df_retained['Total_Sales_2024']
    df_retained['Sales_Change_%'] = np.where(
        df_retained['Total_Sales_2024'] > 0,
        (df_retained['Sales_Change_AED'] / df_retained['Total_Sales_2024']) * 100,
        np.where(df_retained['Total_Sales_2025'] > 0, 100.0, 0.0)
    )
    
    return df_lost, df_new, df_retained

# Run the data loading and comparison
df_lost, df_new, df_retained = load_and_compare_data(SALES_2024_PATH, SALES_2025_PATH)

if df_lost is None:
    st.stop()


# ---------------------------
## Sidebar Filters
# ---------------------------
st.sidebar.header("Filter Results")

# --- 1. Category Filter (Standard Select Box Filter) ---
all_categories = pd.concat([df_new['Category'], df_retained['Category'], df_lost['Category']]).unique()
all_categories = [c for c in all_categories if pd.notna(c)] 
all_categories.sort()

selected_category = st.sidebar.selectbox(
    "1. Filter by Category",
    options=["-- ALL --"] + list(all_categories),
    index=0 
)

# --- Apply Filters ---
if selected_category == "-- ALL --":
    category_filter_list = all_categories
else:
    category_filter_list = [selected_category] 

# Apply Category Filter
filtered_lost = df_lost[df_lost['Category'].isin(category_filter_list)]
filtered_new = df_new[df_new['Category'].isin(category_filter_list)]
filtered_retained = df_retained[df_retained['Category'].isin(category_filter_list)] 

filtered_total_lost = filtered_lost 
total_lost = len(filtered_total_lost)
total_new = len(filtered_new)
total_retained = len(filtered_retained)
total_sales_lost_value = filtered_total_lost['Total_Sales'].sum()

# ---------------------------
## Dashboard Presentation
# ---------------------------
st.markdown("---")

# KPIs based on filtered data
st.subheader("High-Level Insights (Filtered Data)")
col1, col2, col3, col4 = st.columns(4)

col1.metric("Items Retained", f"{total_retained:,}")
col2.metric("Total Items Lost (Absence in 2025)", f"{total_lost:,}", delta=f"{-total_lost:,}")
col3.metric("Items New in 2025", f"{total_new:,}", delta=f"{total_new:,}")
col4.metric("Total Lost Sales Value (AED)", f"AED {total_sales_lost_value:,.2f}", delta_color="inverse")

st.markdown("---")

# --- Tabbed Results ---
tab1, tab2, tab3 = st.tabs(["🔴 Lost Items (Focus)", "🟢 Items That Had Sales Now (NEW)", "🟡 Retained (Active) Items"])

# ====================================================================
# TAB 1: LOST ITEMS
# ====================================================================
with tab1:
    st.header(f"🔴 {total_lost:,} Lost Items (Absence in 2025)")
    st.error(f"These items contributed **AED {total_sales_lost_value:,.2f}** to 2024 revenue but are now completely **absent in 2025**. This list is sorted by highest lost sales value.")
    
    if not filtered_total_lost.empty:
        df_lost_sorted = filtered_total_lost.sort_values('Total_Sales', ascending=False)
        st.subheader("Lost Items ranked by their 2024 Sales Value")
        
        display_lost_df = df_lost_sorted[['Item_Code', 'Item_Name', 'Category', 'Total_Qty', 'Total_Sales']].rename(
            columns={'Total_Qty': 'Qty Sold (2024)', 'Total_Sales': 'Sales Value (2024)'}
        )
        st.dataframe(display_lost_df.style.format({
            'Sales Value (2024)': 'AED {:,.2f}',
            'Qty Sold (2024)': '{:,.0f}'
        }), use_container_width=True)

    else:
        st.success("No lost items found in the selected category.")

# ====================================================================
# TAB 2: NEW ITEMS
# ====================================================================
with tab2:
    st.header(f"🟢 {total_new:,} Items New in 2025 (Had Sales Now)")
    st.success("These are successful launches or reactivations. Analyze their 2025 performance.")
    
    if not filtered_new.empty:
        df_new_sorted = filtered_new.sort_values('Total_Sales', ascending=False)
        st.subheader("Items ranked by their 2025 Sales Value")

        display_new_df = df_new_sorted[['Item_Code', 'Item_Name', 'Category', 'Total_Qty', 'Total_Sales']].rename(
            columns={'Total_Qty': 'Qty Sold (2025)', 'Total_Sales': 'Sales Value (2025)'}
        )
        st.dataframe(display_new_df.style.format({
            'Sales Value (2025)': 'AED {:,.2f}',
            'Qty Sold (2025)': '{:,.0f}'
        }), use_container_width=True)

    else:
        st.info("No new items were introduced or reactivated in the selected category.")

# ====================================================================
# TAB 3: RETAINED ITEMS (FIXED DISPLAY AND AGGREGATION)
# ====================================================================
with tab3:
    st.header(f"🟡 {total_retained:,} Items Retained (Active in both 2024 and 2025)")
    st.info("Core items. Showing all items in the selected category.")

    # Set the view to show all filtered retained items by default
    filtered_retained_view = filtered_retained
    selected_view = "All Retained Items"

    # --- Display Metrics for the Selected View ---
    total_view_sales_diff = filtered_retained_view['Sales_Change_AED'].sum()
    total_view_items = len(filtered_retained_view)
    
    st.metric(
        label=f"Total Sales Difference for {selected_view}",
        value=f"AED {total_view_sales_diff:+,.2f}", 
        delta=f"Total Items: {total_view_items:,}"
    )
    
    st.markdown("---")


    if not filtered_retained_view.empty:
        
        # Sort column is set to sales change to give a quick overview of performance
        sort_column = 'Sales_Change_AED'
        sort_ascending = False # Sort by biggest growth/decline first
        
        st.subheader(f"Items Sorted by Sales Change (AED)")

        display_df = filtered_retained_view[[
            'Item_Code', 'Item_Name', 'Category', 
            'Total_Sales_2024', 'Total_Sales_2025', 
            'Sales_Change_AED', 'Sales_Change_%',
            'Total_Qty_2024', 'Total_Qty_2025'
        ]].sort_values(sort_column, ascending=sort_ascending)
        
        # Rename columns for display
        display_df = display_df.rename(columns={
            'Total_Sales_2024': 'Sales Value (2024)',
            'Total_Sales_2025': 'Sales Value (2025)',
            'Sales_Change_AED': 'Sales Diff. (AED)',
            'Sales_Change_%': 'Sales Change (%)',
            'Total_Qty_2024': 'Qty Sold (2024)',
            'Total_Qty_2025': 'Qty Sold (2025)',
        })

        st.dataframe(display_df.style.format({
            'Sales Value (2024)': 'AED {:,.2f}',
            'Sales Value (2025)': 'AED {:,.2f}',
            'Sales Diff. (AED)': 'AED {:+,.2f}', 
            'Sales Change (%)': '{:+.2f}%',       
            'Qty Sold (2024)': '{:,.0f}',
            'Qty Sold (2025)': '{:,.0f}'
        }), use_container_width=True)

    else:
        st.info("No items match the selected criteria in the chosen category.")

if __name__ == "__main__":
    pass
