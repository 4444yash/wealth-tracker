import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import datetime
import requests

# --- Page Config ---
st.set_page_config(page_title="Wealth Tracker", page_icon="📈", layout="wide")

st.title("📈 Wealth Tracker")
st.markdown("Track your Stocks, Crypto, and Mutual Fund investments using Lumpsum or SIP strategies.")

# --- Data Fetching ---
@st.cache_data(show_spinner="Fetching Asset Data...")
def get_yfinance_data(ticker, start, end):
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(start=start, end=end)
        if not df.empty:
            df = df[['Close']].rename(columns={'Close': 'Price'})
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
    return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=300)
def search_yahoo_finance(query, asset_type):
    if not query or len(query) < 2:
        return {}
    
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            quotes = data.get('quotes', [])
            
            # Filter based on category
            results = {}
            for q in quotes:
                quote_type = q.get('quoteType', '')
                symbol = q.get('symbol', '')
                short_name = q.get('shortname', '') or q.get('longname', '') or symbol
                
                if asset_type == "Stocks" and quote_type == "EQUITY":
                    results[f"{short_name} ({symbol})"] = symbol
                elif asset_type == "Crypto" and quote_type == "CRYPTOCURRENCY":
                    results[f"{short_name} ({symbol})"] = symbol
                    
            return results
    except Exception as e:
        st.sidebar.error(f"Search API Error: {e}")
    
    return {}

@st.cache_resource
def get_mftool_instance():
    return Mftool()

@st.cache_data(show_spinner="Loading Mutual Funds Catalog...", ttl=3600*24)
def get_mutual_funds():
    try:
        mf = get_mftool_instance()
        # Returns a dict of {scheme_code: scheme_name}
        return mf.get_scheme_codes()
    except Exception as e:
        st.error(f"Error fetching Mutual Funds catalog: {e}")
        return {}

@st.cache_data(show_spinner="Fetching Mutual Fund Data...")
def get_mf_data(schema_code, start, end):
    try:
        mf = get_mftool_instance()
        data_json = mf.get_scheme_historical_nav(schema_code)
        if data_json and 'data' in data_json:
            df = pd.DataFrame(data_json['data'])
            df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
            df['nav'] = pd.to_numeric(df['nav'], errors='coerce')
            df = df.set_index('date').sort_index()
            df = df.rename(columns={'nav': 'Price'})
            
            mask = (df.index.date >= start) & (df.index.date <= end)
            return df.loc[mask]
    except Exception as e:
        st.error(f"Error fetching MF data: {e}")
    return pd.DataFrame()

# --- Sidebar ---
st.sidebar.header("Investment Parameters")
category = st.sidebar.selectbox("Instrument Category", ["Stocks", "Crypto", "Mutual Fund"])

asset_name = ""
asset_id = ""

if category in ["Stocks", "Crypto"]:
    st.sidebar.markdown(f"**Search for {category}**")
    
    # Store search query in session state to prevent infinite reloads when typing
    if 'search_query' not in st.session_state:
        st.session_state.search_query = 'Reliance' if category == 'Stocks' else 'Bitcoin'
        
    search_input = st.sidebar.text_input("Type to search...", st.session_state.search_query)
    st.session_state.search_query = search_input
    
    search_results = search_yahoo_finance(search_input, category)
    
    if search_results:
        selected_display = st.sidebar.selectbox("Select Asset", list(search_results.keys()))
        asset_id = search_results[selected_display]
        asset_name = selected_display
    elif len(search_input) >= 2:
        st.sidebar.warning(f"No {category.lower()} found matching '{search_input}'.")

elif category == "Mutual Fund":
    mf_catalog = get_mutual_funds()
    if mf_catalog:
        # Create a reverse mapping of name -> code for the searchable selectbox
        mf_options = {name: code for code, name in mf_catalog.items()}
        # Default to Parag Parikh Flexi Cap Fund Direct Growth (122639) if available
        default_idx = 0
        search_names = list(mf_options.keys())
        
        # Simple lookup for default fund index
        for i, name in enumerate(search_names):
            if "Parag Parikh Flexi Cap" in name and "Direct" in name and "Growth" in name:
                default_idx = i
                break

        selected_mf_name = st.sidebar.selectbox("Search Mutual Fund", search_names, index=default_idx)
        asset_id = mf_options[selected_mf_name]
        asset_name = selected_mf_name
    else:
        st.sidebar.error("Failed to load Mutual Fund list.")

invest_type = st.sidebar.selectbox("Investment Type", ["Lumpsum", "SIP"])

today = datetime.date.today()
five_years_ago = today - datetime.timedelta(days=5*365)
start_date = st.sidebar.date_input("Start Date", five_years_ago)
end_date = st.sidebar.date_input("End Date", today)
amount = st.sidebar.number_input("Investment Amount", min_value=100.0, value=10000.0, step=100.0)

# --- Main App Logic ---
if start_date > end_date:
    st.sidebar.error("Error: End date must fall after start date.")
elif asset_id:
    data = pd.DataFrame()
    
    st.subheader(asset_name)

    if category in ["Stocks", "Crypto"]:
        data = get_yfinance_data(asset_id, start_date, end_date)
    elif category == "Mutual Fund":
        data = get_mf_data(asset_id, start_date, end_date)

    if not data.empty:
        # Display Chart
        st.line_chart(data['Price'], use_container_width=True)

        # Calculations
        if invest_type == "Lumpsum":
            first_price = float(data.iloc[0]['Price'])
            last_price = float(data.iloc[-1]['Price'])
            
            units = amount / first_price
            current_value = units * last_price
            total_invested = amount

        elif invest_type == "SIP":
            monthly_data = data.groupby([data.index.year, data.index.month]).first()
            
            total_units = sum(amount / float(price) for price in monthly_data['Price'])
            total_invested = amount * len(monthly_data)
            last_price = float(data.iloc[-1]['Price'])
            current_value = total_units * last_price

        # Calculate Returns
        abs_return = ((current_value - total_invested) / total_invested) * 100 if total_invested > 0 else 0

        # Display Metrics
        col1, col2, col3 = st.columns(3)
        col1.info(f"**Total Amount Invested:**\n\n₹ {total_invested:,.2f}")
        
        return_color = "normal" if abs_return >= 0 else "inverse"
        delta_val = current_value - total_invested
        col2.metric("Current Value", f"₹ {current_value:,.2f}", delta=f"₹ {delta_val:,.2f}", delta_color=return_color)
        col3.metric("Absolute Return", f"{abs_return:,.2f} %", delta=f"{abs_return:,.2f} %", delta_color=return_color)

    else:
        st.warning("No data available for the selected dates or ticker symbol. Please try again.")
