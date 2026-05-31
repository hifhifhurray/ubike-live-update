import streamlit as st
import pandas as pd
import requests

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(layout="wide", page_title="Live Dispatch System")

st.title("Live Fleet Dispatch Dashboard")
st.markdown("This system connects to the government open data API in real-time with automated fallback and dynamic column mapping features.")

# ==========================================
# 2. PURE DATA FETCHING
# ==========================================
@st.cache_data(ttl=60)
def fetch_realtime_data():
    url = "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
    except Exception as e:
        return pd.DataFrame(), f"Unable to connect to the government database: {str(e)}"
    
    if isinstance(data, dict):
        if 'retVal' in data:
            data = data['retVal']
        elif isinstance(data, dict):
            data = list(data.values())
            
    df = pd.DataFrame(data)
    
    if df.empty:
        return df, "The government API returned empty data."
        
    # --- DYNAMIC COLUMN MAPPER ---
    col_map = {
        'Available': ['available_rent_bikes', 'AvailableRentBikes', 'sbi', 'rent_bikes', 'Available'],
        'Empty': ['available_return_bikes', 'AvailableReturnBikes', 'bemp', 'return_bikes', 'emp', 'Empty'],
        'Total': ['total', 'Total', 'tot', 'capacity', 'Quantity'], 
        'Station': ['sna', 'name_tw', 'StationName', 'name', 'sna_tw', 'Station'],
        'District': ['sarea', 'area', 'district', 'sarea_tw', 'District'],
        'Status': ['act', 'active', 'status', 'Status'],
        'Lat': ['lat', 'latitude', 'Latitude', 'Lat'],
        'Lng': ['lng', 'lon', 'longitude', 'Longitude', 'Lng'],
        'Time': ['mday', 'updateTime', 'srcUpdateTime', 'infoTime', 'Time']
    }

    rename_dict = {}
    for standard_name, possible_names in col_map.items():
        for p_name in possible_names:
            if p_name in df.columns:
                rename_dict[p_name] = standard_name
                break 
                
    df = df.rename(columns=rename_dict)
    return df, None

# --- UI and Error Handling Outside Cache ---
with st.spinner("Fetching live data from the real-time database..."):
    df, error_msg = fetch_realtime_data()

if error_msg:
    st.error(error_msg)
    if st.button("Retry Connection"):
        fetch_realtime_data.clear()
        st.rerun()
    st.stop()

required = ['Available', 'Empty', 'Total', 'Station', 'Lat', 'Lng']
missing = [r for r in required if r not in df.columns]

if missing:
    st.error(f"Government open data schema anomaly! Missing core dispatch columns: {missing}")
    st.write("All raw columns currently returned by the server:", df.columns.tolist())
    st.info("This is typically due to temporary server maintenance or rate-limiting. Click the button below to refresh.")
    if st.button("Refresh Cache Immediately"):
        fetch_realtime_data.clear()
        st.rerun()
    st.stop()

# --- Data Cleaning and Numeric Conversions ---
num_cols = ['Total', 'Available', 'Empty', 'Status', 'Lat', 'Lng']
for col in num_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# ==========================================
# 3. TOP KPI METRICS
# ==========================================
st.subheader("City Overview")

total_stations = len(df)
total_bikes_available = int(df['Available'].sum())
stations_empty = len(df[df['Available'] == 0]) 
stations_full = len(df[df['Empty'] == 0]) 

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Stations", total_stations)
col2.metric("Available Bikes", f"{total_bikes_available:,}")
col3.metric("Empty Stations", stations_empty, delta="Needs Re-stocking", delta_color="inverse")
col4.metric("Full Stations", stations_full, delta="Needs Removal", delta_color="inverse")

# ==========================================
# 4. SEARCH & FILTER WITH LIVE SUGGESTIONS
# ==========================================
st.markdown("---")
st.subheader("Station Search")

col_search, col_filter = st.columns([2, 1])
with col_search:
    search_query = st.text_input(
        "Search by partial keyword in Chinese or English (e.g., MRT, Park, 捷運, 公園):", 
        placeholder="Type any part of the name to see all matching results instantly..."
    )
with col_filter:
    status_filter = st.selectbox("Quick Filter:", ["Show All", "Empty Stations Only", "Full Stations Only"])

filtered_df = df.copy()
if search_query:
    clean_query = search_query.strip()
    # Case-insensitive partial matching to catch any instance of the keyword
    filtered_df = filtered_df[filtered_df['Station'].astype(str).str.contains(clean_query, case=False, na=False)]
    
    # --- LIVE SUGGESTIONS HELPER ---
    suggestions = filtered_df['Station'].unique().tolist()
    total_matches = len(suggestions)
    if total_matches > 0:
        # Display up to 8 matching full names as suggestions to guide the client
        truncated_suggestions = suggestions[:8]
        suggestions_text = ", ".join(truncated_suggestions)
        if total_matches > 8:
            suggestions_text += "..."
        st.markdown(f"**Found {total_matches} matching stations.** Suggestions: *{suggestions_text}*")
    else:
        st.markdown("No matching stations found. Try another keyword.")

if status_filter == "Empty Stations Only":
    filtered_df = filtered_df[filtered_df['Available'] == 0]
elif status_filter == "Full Stations Only":
    filtered_df = filtered_df[filtered_df['Empty'] == 0]

# ==========================================
# 5. MAP & DISPLAY
# ==========================================
st.markdown("**Live Station Map**")
if not filtered_df.empty:
    map_df = filtered_df.rename(columns={'Lat': 'latitude', 'Lng': 'longitude'})
    st.map(map_df[['latitude', 'longitude']])
else:
    st.warning("No stations found matching the filter criteria.")

st.markdown("**Detailed Station Data**")
display_cols = ['Station', 'District', 'Total', 'Available', 'Empty', 'Status', 'Time']
display_cols = [c for c in display_cols if c in filtered_df.columns]

display_df = filtered_df[display_cols].copy()

if 'Status' in display_df.columns:
    display_df['Status'] = display_df['Status'].apply(lambda x: 'Normal' if x == 1 else 'Suspended/Maintenance')
if 'Station' in display_df.columns:
    display_df['Station'] = display_df['Station'].astype(str).str.replace('YouBike2.0_', '')

display_df.columns = [c + " (Live)" for c in display_cols]
st.dataframe(display_df, use_container_width=True, hide_index=True)

if st.button("Force Refresh Data"):
    fetch_realtime_data.clear()
    st.rerun()