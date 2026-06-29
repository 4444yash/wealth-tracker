import streamlit as st
import pandas as pd
import yfinance as yf
from mftool import Mftool
import datetime
import requests
import plotly.graph_objects as go
import importlib
import finance_utils
importlib.reload(finance_utils)
from finance_utils import to_date, xirr, cagr, calculate_indian_tax, project_future_tax, run_swp_simulation, solve_sustainable_withdrawal

# --- Page Config ---
st.set_page_config(page_title="Wealth Tracker", page_icon="📈", layout="wide")

# --- Custom Premium CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

/* Main font override */
html, body, [class*="css"], .stMarkdown {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Dark theme widgets (always legible on both light and dark backgrounds) */
div.metric-card {
    background: #1E293B !important;
    border: 1px solid #334155 !important;
    border-radius: 12px !important;
    padding: 1.25rem 1.5rem !important;
    box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.15) !important;
    margin-bottom: 1rem !important;
    transition: all 0.3s ease !important;
}

div.metric-card:hover {
    transform: translateY(-2px) !important;
    border-color: #14B8A6 !important;
    box-shadow: 0 8px 30px 0 rgba(20, 184, 166, 0.15) !important;
}

.metric-title {
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    color: #94A3B8 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    margin-bottom: 0.4rem !important;
}

.metric-value {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: #F8FAFC !important;
    line-height: 1.2 !important;
}

.metric-delta-pos {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    color: #2DD4BF !important;
    margin-top: 0.3rem !important;
}

.metric-delta-neg {
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    color: #F87171 !important;
    margin-top: 0.3rem !important;
}

/* Beautiful explanation cards */
.info-card {
    background: #0F172A !important;
    border-left: 4px solid #3b82f6 !important;
    border-radius: 4px 12px 12px 4px !important;
    padding: 1.25rem !important;
    margin-top: 1.5rem !important;
    color: #E2E8F0 !important;
}

.info-card, .info-card * {
    color: #E2E8F0 !important;
}

.info-card-title {
    font-weight: 700 !important;
    color: #FFFFFF !important;
    margin-bottom: 0.5rem !important;
}

/* Tabs customization */
button[data-baseweb="tab"] {
    font-size: 1rem !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.5rem !important;
}
</style>
""", unsafe_allow_html=True)

st.title("📈 Wealth Tracker")
st.markdown("Track your Stocks, Crypto, and Mutual Fund investments using Lumpsum or SIP strategies, with built-in Indian Capital Gains Tax analytics.")

# --- UI Helper ---
def metric_card(title, value, delta=None, is_percent=False, curr_symbol="₹"):
    delta_html = ""
    if delta is not None:
        if is_percent:
            delta_str = f"{delta:+.2f}% Abs Return"
        else:
            delta_str = f"{curr_symbol} {delta:+,.2f} Profit" if delta >= 0 else f"- {curr_symbol} {abs(delta):,.2f} Loss"
        
        color_class = "metric-delta-pos" if delta >= 0 else "metric-delta-neg"
        delta_html = f'<div class="{color_class}">{delta_str}</div>'
        
    card_html = f"""
    <div class="metric-card">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """
    return card_html

def get_currency_symbol(asset_id, category):
    return "₹"

# --- Timeseries Calculations ---
def calculate_sip_timeseries(data, amount, sip_stop_date=None):
    monthly_investment_indices = []
    last_yr_mo = None
    for idx, row in data.iterrows():
        # Stop investments after the stop date
        if sip_stop_date is not None and idx.date() > sip_stop_date:
            continue
            
        yr_mo = (idx.year, idx.month)
        if yr_mo != last_yr_mo:
            monthly_investment_indices.append(idx)
            last_yr_mo = yr_mo
            
    invested_dates = set(monthly_investment_indices)
    
    cumulative_invested = []
    portfolio_value = []
    units_accumulated = []
    
    current_units = 0.0
    current_invested = 0.0
    
    for idx, row in data.iterrows():
        price = float(row['Price'])
        if idx in invested_dates:
            current_units += amount / price
            current_invested += amount
        
        cumulative_invested.append(current_invested)
        portfolio_value.append(current_units * price)
        units_accumulated.append(current_units)
        
    ts_df = pd.DataFrame({
        'Invested': cumulative_invested,
        'Portfolio Value': portfolio_value,
        'Units': units_accumulated,
        'Asset Price': data['Price']
    }, index=data.index)
    
    return ts_df

def calculate_lumpsum_timeseries(data, amount):
    first_price = float(data.iloc[0]['Price'])
    units = amount / first_price
    
    ts_df = pd.DataFrame({
        'Invested': [amount] * len(data),
        'Portfolio Value': data['Price'] * units,
        'Units': [units] * len(data),
        'Asset Price': data['Price']
    }, index=data.index)
    
    return ts_df

def compute_comparison(data, amount, sip_stop_date=None):
    monthly_investment_indices = []
    last_yr_mo = None
    for idx, row in data.iterrows():
        if sip_stop_date is not None and idx.date() > sip_stop_date:
            continue
        yr_mo = (idx.year, idx.month)
        if yr_mo != last_yr_mo:
            monthly_investment_indices.append(idx)
            last_yr_mo = yr_mo
            
    num_installments = len(monthly_investment_indices)
    total_capital = amount * num_installments
    
    sip_ts = calculate_sip_timeseries(data, amount, sip_stop_date)
    lump_ts = calculate_lumpsum_timeseries(data, total_capital)
    
    return sip_ts, lump_ts, total_capital

# --- Plotting Helpers ---
def plot_growth_chart(ts_df, asset_name):
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=ts_df.index,
        y=ts_df['Portfolio Value'],
        mode='lines',
        name='Portfolio Value (Pre-Tax)',
        line=dict(color='#00D1B2', width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 209, 178, 0.08)'
    ))
    
    fig.add_trace(go.Scatter(
        x=ts_df.index,
        y=ts_df['Invested'],
        mode='lines',
        name='Amount Invested',
        line=dict(color='#FF3860', width=2, dash='dash')
    ))
    
    fig.update_layout(
        title=dict(
            text=f"Growth of Investment in {asset_name}",
            font=dict(size=18, family="Plus Jakarta Sans", color="#FFFFFF")
        ),
        xaxis_title="Date",
        yaxis_title="Value",
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
    )
    return fig

def plot_cost_averaging_chart(data, invested_dates, asset_name):
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['Price'],
        mode='lines',
        name=f'{asset_name} Price',
        line=dict(color='#3273DC', width=2.5)
    ))
    
    inv_dates_list = sorted(list(invested_dates))
    inv_data = data.loc[inv_dates_list]
    
    fig.add_trace(go.Scatter(
        x=inv_data.index,
        y=inv_data['Price'],
        mode='markers',
        name='SIP Installment',
        marker=dict(color='#FFDD57', size=9, symbol='circle', line=dict(color='#000000', width=1.5)),
        hovertemplate='SIP Purchase<br>Price: %{y:.2f}<br>Date: %{x|%Y-%m-%d}'
    ))
    
    fig.update_layout(
        title=dict(
            text=f"{asset_name} Price Trend and SIP Installments",
            font=dict(size=18, family="Plus Jakarta Sans", color="#FFFFFF")
        ),
        xaxis_title="Date",
        yaxis_title="Price",
        template="plotly_dark",
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
    )
    return fig

def plot_comparison_chart(sip_ts, lump_ts, asset_name):
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=sip_ts.index,
        y=sip_ts['Portfolio Value'],
        mode='lines',
        name='SIP Portfolio Value',
        line=dict(color='#00D1B2', width=3)
    ))
    
    fig.add_trace(go.Scatter(
        x=lump_ts.index,
        y=lump_ts['Portfolio Value'],
        mode='lines',
        name='Lumpsum Portfolio Value',
        line=dict(color='#3273DC', width=3)
    ))
    
    fig.add_trace(go.Scatter(
        x=sip_ts.index,
        y=sip_ts['Invested'],
        mode='lines',
        name='SIP Cumulative Invested',
        line=dict(color='#FF3860', width=1.5, dash='dash')
    ))
    
    fig.update_layout(
        title=dict(
            text=f"SIP vs Lumpsum Portfolio Growth (Pre-Tax) for {asset_name}",
            font=dict(size=18, family="Plus Jakarta Sans", color="#FFFFFF")
        ),
        xaxis_title="Date",
        yaxis_title="Portfolio Value",
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
    )
    return fig

def plot_tax_comparison_bars(total_invested, pre_tax_val, post_tax_val, curr_symbol):
    fig = go.Figure()
    categories = ['Total Invested', 'Pre-Tax Value', 'Post-Tax (In-Hand)']
    values = [total_invested, pre_tax_val, post_tax_val]
    colors = ['#8C9BAE', '#3273DC', '#00D1B2']
    
    fig.add_trace(go.Bar(
        x=categories,
        y=values,
        marker_color=colors,
        text=[f"{curr_symbol}{val:,.2f}" for val in values],
        textposition='auto',
        hoverinfo='none'
    ))
    
    fig.update_layout(
        title=dict(
            text="Visual Tax Impact Comparison",
            font=dict(size=16, family="Plus Jakarta Sans", color="#FFFFFF")
        ),
        template="plotly_dark",
        margin=dict(l=40, r=40, t=50, b=40),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
    )
    return fig

def plot_future_projection(monthly_amount, annual_rate, total_years, sip_years=None, tax_amount=0.0):
    if sip_years is None or sip_years > total_years:
        sip_years = total_years
        
    total_months = total_years * 12
    sip_months = int(sip_years * 12)
    monthly_rate = (annual_rate / 100.0) / 12
    
    dates = []
    invested_vals = []
    portfolio_vals = []
    
    current_invested = 0.0
    current_value = 0.0
    today = datetime.date.today()
    
    for month in range(1, total_months + 1):
        dt = today + datetime.timedelta(days=month * 30.436)
        
        # Invest if within active SIP months
        if month <= sip_months:
            current_invested += monthly_amount
            # Compound SIP formula
            if monthly_rate > 0:
                current_value = monthly_amount * (((1 + monthly_rate) ** month - 1) / monthly_rate) * (1 + monthly_rate)
            else:
                current_value = current_invested
        else:
            # SIP stopped, compound the value of the portfolio at the stop date as lumpsum
            if monthly_rate > 0:
                current_value = current_value * (1 + monthly_rate)
            # current_invested stays flat
            
        dates.append(dt)
        invested_vals.append(current_invested)
        portfolio_vals.append(current_value)
        
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=portfolio_vals,
        mode='lines',
        name='Future Portfolio Value (Pre-Tax)',
        line=dict(color='#00D1B2', width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 209, 178, 0.08)'
    ))
    
    if tax_amount > 0:
        post_tax_val = max(0.0, portfolio_vals[-1] - tax_amount)
        fig.add_trace(go.Scatter(
            x=[dates[-1]],
            y=[post_tax_val],
            mode='markers+text',
            name='In-Hand Value (Post-Tax)',
            marker=dict(color='#FFDD57', size=12, symbol='star'),
            text=[f"In-Hand"],
            textposition="bottom center"
        ))
        
    fig.add_trace(go.Scatter(
        x=dates,
        y=invested_vals,
        mode='lines',
        name='Total Amount Invested',
        line=dict(color='#FF3860', width=2, dash='dash')
    ))
    
    fig.update_layout(
        title=dict(
            text=f"Future Wealth Projection ({total_years} Years @ {annual_rate}% Expected Return)",
            font=dict(size=18, family="Plus Jakarta Sans", color="#FFFFFF")
        ),
        xaxis_title="Timeline",
        yaxis_title="Projected Value",
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
    )
    return fig, portfolio_vals[-1], invested_vals[-1]

def plot_swp_chart(res, curr_symbol="₹"):
    dates = res['dates']
    portfolio_vals = res['portfolio_values']
    withdrawals = res['withdrawals']
    taxes = res['taxes']
    
    # Calculate cumulative withdrawn and taxes
    cum_withdrawn = pd.Series(withdrawals).cumsum().tolist()
    cum_taxes = pd.Series(taxes).cumsum().tolist()
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=portfolio_vals,
        mode='lines',
        name='Portfolio Value',
        line=dict(color='#00D1B2', width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 209, 178, 0.08)'
    ))
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=cum_withdrawn,
        mode='lines',
        name='Cumulative Withdrawn',
        line=dict(color='#3273DC', width=2, dash='dash')
    ))
    
    fig.add_trace(go.Scatter(
        x=dates,
        y=cum_taxes,
        mode='lines',
        name='Cumulative Tax Paid',
        line=dict(color='#FF3860', width=1.5, dash='dot')
    ))
    
    fig.update_layout(
        title=dict(
            text="SWP Portfolio & Cash Flow Timeline",
            font=dict(size=18, family="Plus Jakarta Sans", color="#FFFFFF")
        ),
        xaxis_title="Timeline",
        yaxis_title="Value",
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.05)')
    )
    return fig


# --- Data Fetching Functions ---
@st.cache_data(show_spinner="Fetching Asset Data...")
def get_yfinance_data(ticker, start, end):
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(start=start, end=end)
        if not df.empty:
            df = df[['Close']].rename(columns={'Close': 'Price'})
            df = df.dropna(subset=['Price'])
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
        st.error(f"Search API Error: {e}")
    
    return {}

@st.cache_resource
def get_mftool_instance():
    return Mftool()

@st.cache_data(show_spinner="Loading Mutual Funds Catalog...", ttl=3600*24)
def get_mutual_funds():
    try:
        mf = get_mftool_instance()
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
            df = df.dropna(subset=['Price'])
            
            mask = (df.index.date >= start) & (df.index.date <= end)
            return df.loc[mask]
    except Exception as e:
        st.error(f"Error fetching MF data: {e}")
    return pd.DataFrame()

# --- Main App Logic Configuration ---
with st.container():
    st.markdown("### ⚙️ Configure Investment Parameters")
    
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        category = st.selectbox("Instrument Category", ["Stocks", "Crypto", "Mutual Fund"])
        
        asset_name = ""
        asset_id = ""
        
        if category in ["Stocks", "Crypto"]:
            if 'search_query' not in st.session_state:
                st.session_state.search_query = 'Reliance' if category == 'Stocks' else 'Bitcoin'
                
            search_input = st.text_input(f"Search for {category}...", st.session_state.search_query)
            st.session_state.search_query = search_input
            
            search_results = search_yahoo_finance(search_input, category)
            
            if search_results:
                selected_display = st.selectbox("Select Asset", list(search_results.keys()))
                asset_id = search_results[selected_display]
                asset_name = selected_display
            elif len(search_input) >= 2:
                st.warning(f"No {category.lower()} found matching '{search_input}'.")
                
        elif category == "Mutual Fund":
            mf_catalog = get_mutual_funds()
            if mf_catalog:
                mf_options = {name: code for code, name in mf_catalog.items()}
                search_names = list(mf_options.keys())
                
                mf_search = st.text_input("Filter Mutual Funds (e.g. Parag Parikh, HDFC)...", "Parag Parikh")
                filtered_names = [name for name in search_names if mf_search.lower() in name.lower()]
                
                if filtered_names:
                    default_idx = 0
                    for i, name in enumerate(filtered_names):
                        if "Flexi Cap" in name and "Direct" in name and "Growth" in name:
                            default_idx = i
                            break
                    
                    selected_mf_name = st.selectbox("Select Mutual Fund", filtered_names, index=default_idx)
                    asset_id = mf_options[selected_mf_name]
                    asset_name = selected_mf_name
                else:
                    st.warning("No matching Mutual Fund found. Clear search or try another keyword.")
            else:
                st.error("Failed to load Mutual Fund list.")

    with col_input2:
        invest_type = st.selectbox("Investment Type", ["Lumpsum", "SIP"])
        
        amount_label = "Monthly SIP Amount" if invest_type == "SIP" else "Lumpsum Investment Amount"
        amount = st.number_input(amount_label, min_value=10.0, value=5000.0, step=100.0)

    col_input3, col_input4 = st.columns(2)
    with col_input3:
        today = datetime.date.today()
        five_years_ago = today - datetime.timedelta(days=5*365)
        start_date = st.date_input("Start Date", five_years_ago)
        end_date = st.date_input("End Date", today)

    with col_input4:
        sip_stop_date = None
        if invest_type == "SIP":
            limit_sip = st.checkbox("Limit SIP Duration (Stop & Hold)", value=False, 
                                             help="Allows you to run the SIP for a certain time, then stop, leaving the money invested until the end date.")
            if limit_sip:
                # Default stop date is halfway through
                default_stop = start_date + (end_date - start_date) / 2
                sip_stop_date = st.date_input("SIP Stop Date", default_stop)
                if sip_stop_date < start_date or sip_stop_date > end_date:
                    st.error("SIP Stop Date must fall between Start Date and End Date.")

    # Tax parameters inside a clean expander to optimize vertical space
    with st.expander("🇮🇳 Indian Capital Gains Tax Configuration", expanded=False):
        apply_tax = st.checkbox("Apply Capital Gains Tax Layer", value=True)
        
        mf_type = "Equity-Oriented"
        slab_rate = 30.0
        
        if apply_tax:
            tax_col1, tax_col2 = st.columns(2)
            with tax_col1:
                if category == "Mutual Fund":
                    mf_type = st.selectbox("Mutual Fund Category", ["Equity-Oriented", "Debt-Oriented"], 
                                                   help="Equity mutual funds are taxed at 12.5% LTCG (>1 year) / 20% STCG. Debt funds are taxed at your slab rate.")
            with tax_col2:
                if category == "Mutual Fund" and mf_type == "Debt-Oriented":
                    slab_rate = st.selectbox("Your Income Tax Slab Rate (%)", [5.0, 10.0, 15.0, 20.0, 30.0, 39.0], index=4, 
                                                     help="Marginal tax slab rate applicable to you. Debt fund gains are added directly to your income.")

# --- Main App Logic ---
if start_date > end_date:
    st.error("Error: End date must fall after start date.")
elif asset_id:
    data = pd.DataFrame()
    st.subheader(asset_name)

    if category in ["Stocks", "Crypto"]:
        data = get_yfinance_data(asset_id, start_date, end_date)
    elif category == "Mutual Fund":
        data = get_mf_data(asset_id, start_date, end_date)

    if not data.empty:
        curr_symbol = get_currency_symbol(asset_id, category)
        
        # Calculate monthly investment dates
        monthly_investment_indices = []
        last_yr_mo = None
        for idx, row in data.iterrows():
            if sip_stop_date is not None and idx.date() > sip_stop_date:
                continue
            yr_mo = (idx.year, idx.month)
            if yr_mo != last_yr_mo:
                monthly_investment_indices.append(idx)
                last_yr_mo = yr_mo
        invested_dates = set(monthly_investment_indices)
        
        # Calculate pre-tax stats based on strategy
        if invest_type == "Lumpsum":
            ts_df = calculate_lumpsum_timeseries(data, amount)
            total_invested = amount
            current_value = float(ts_df.iloc[-1]['Portfolio Value'])
            delta_val = current_value - total_invested
            abs_return = (delta_val / total_invested) * 100 if total_invested > 0 else 0.0
            annualized_rate = cagr(total_invested, current_value, (data.index[-1] - data.index[0]).days / 365.0)
            average_cost = float(data.iloc[0]['Price'])
            total_units = total_invested / average_cost
            
            # Setup arrays for tax function
            inv_dates = [data.index[0]]
            inv_prices = [float(data.iloc[0]['Price'])]
        else: # SIP
            ts_df = calculate_sip_timeseries(data, amount, sip_stop_date)
            total_invested = float(ts_df.iloc[-1]['Invested'])
            current_value = float(ts_df.iloc[-1]['Portfolio Value'])
            delta_val = current_value - total_invested
            abs_return = (delta_val / total_invested) * 100 if total_invested > 0 else 0.0
            
            # XIRR calculation
            cash_flows = [(dt, -amount) for dt in monthly_investment_indices]
            cash_flows.append((data.index[-1], current_value))
            annualized_rate = xirr(cash_flows)
            
            total_units = float(ts_df.iloc[-1]['Units'])
            average_cost = total_invested / total_units if total_units > 0 else 0.0
            
            # Setup arrays for tax function
            inv_dates = monthly_investment_indices
            inv_prices = [float(data.loc[dt]['Price']) for dt in monthly_investment_indices]

        # Calculate Post-Tax details
        if apply_tax:
            tax_res = calculate_indian_tax(
                category=category,
                mf_type=mf_type,
                is_sip=(invest_type == "SIP"),
                amount=amount,
                investment_dates=inv_dates,
                investment_prices=inv_prices,
                final_date=data.index[-1],
                final_price=float(data.iloc[-1]['Price']),
                current_value=current_value,
                slab_rate_pct=float(slab_rate)
            )
            tax_amount = tax_res['tax_amount']
            post_tax_value = current_value - tax_amount
            post_tax_profit = post_tax_value - total_invested
            post_tax_abs_return = (post_tax_profit / total_invested) * 100 if total_invested > 0 else 0.0
            effective_tax_rate = tax_res['effective_rate_pct']
            tax_details = tax_res['details']
            
            if invest_type == "Lumpsum":
                post_tax_annualized_rate = cagr(total_invested, post_tax_value, (data.index[-1] - data.index[0]).days / 365.0)
            else: # SIP
                post_tax_cash_flows = [(dt, -amount) for dt in monthly_investment_indices]
                post_tax_cash_flows.append((data.index[-1], post_tax_value))
                post_tax_annualized_rate = xirr(post_tax_cash_flows)
        else:
            tax_amount = 0.0
            post_tax_value = current_value
            post_tax_profit = delta_val
            post_tax_abs_return = abs_return
            effective_tax_rate = 0.0
            post_tax_annualized_rate = annualized_rate
            tax_details = "Tax layer is disabled."

        # Tabs Layout
        tab1, tab2, tab3 = st.tabs(["📊 Performance Dashboard", "⚖️ SIP vs Lumpsum Comparison", "🔮 Future Goal Planner"])
        
        with tab1:
            # 1. Metric cards
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(metric_card("Total Amount Invested", f"{curr_symbol} {total_invested:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
            with col2:
                st.markdown(metric_card("Current Portfolio Value (Pre-Tax)", f"{curr_symbol} {current_value:,.2f}", delta=delta_val, curr_symbol=curr_symbol), unsafe_allow_html=True)
            with col3:
                if apply_tax:
                    st.markdown(metric_card("In-Hand Value (Post-Tax)", f"{curr_symbol} {post_tax_value:,.2f}", delta=post_tax_profit, curr_symbol=curr_symbol), unsafe_allow_html=True)
                else:
                    rate_label = "Annualized Return (XIRR)" if invest_type == "SIP" else "Annualized Return (CAGR)"
                    st.markdown(metric_card(rate_label, f"{annualized_rate * 100:.2f}%", delta=abs_return, is_percent=True, curr_symbol=curr_symbol), unsafe_allow_html=True)

            # 2. Charts (Growth Chart & Purchase Entry Visualizer placed above the tax breakdown)
            fig_growth = plot_growth_chart(ts_df, asset_name)
            st.plotly_chart(fig_growth, use_container_width=True)
            
            st.markdown("### 🎯 Price Trend & Purchase Visualizer")
            if invest_type == "SIP":
                st.write("This chart shows when your monthly purchases were made relative to the asset's price. Notice how SIP automatically buys more units (dots) when the price dips, lowering your average cost.")
                entry_dates = invested_dates
            else:
                st.write("This chart shows your lumpsum purchase entry point (yellow dot) relative to the asset's price trend over time.")
                entry_dates = set([data.index[0]])
                
            fig_averaging = plot_cost_averaging_chart(data, entry_dates, asset_name)
            st.plotly_chart(fig_averaging, use_container_width=True)

            # 3. Pre-Tax vs Post-Tax Breakdown
            if apply_tax:
                st.markdown("### 📋 Pre-Tax vs. Post-Tax Breakdown")
                
                breakdown_data = {
                    "Financial Metric": ["Portfolio Valuation", "Total Net Gain (Profit)", "Annualized Rate of Return", "Absolute Return"],
                    "Pre-Tax": [
                        f"{curr_symbol} {current_value:,.2f}",
                        f"{curr_symbol} {delta_val:,.2f}",
                        f"{annualized_rate * 100:.2f}% ({'XIRR' if invest_type == 'SIP' else 'CAGR'})",
                        f"{abs_return:.2f}%"
                    ],
                    "Post-Tax (In-Hand)": [
                        f"{curr_symbol} {post_tax_value:,.2f}",
                        f"{curr_symbol} {post_tax_profit:,.2f}",
                        f"{post_tax_annualized_rate * 100:.2f}% ({'XIRR' if invest_type == 'SIP' else 'CAGR'})",
                        f"{post_tax_abs_return:.2f}%"
                    ],
                    "Capital Gains Tax impact": [
                        f"-{curr_symbol}{tax_amount:,.2f}",
                        f"-{curr_symbol}{tax_amount:,.2f}",
                        f"-{(annualized_rate - post_tax_annualized_rate) * 100:.2f}%",
                        f"-{abs_return - post_tax_abs_return:.2f}%"
                    ]
                }
                df_breakdown = pd.DataFrame(breakdown_data)
                st.table(df_breakdown.set_index("Financial Metric"))
                
                tax_col1, tax_col2 = st.columns([2, 1])
                with tax_col1:
                    st.info(f"⚖️ **Taxation details**: {tax_details}\n\n📊 **Effective Tax Rate on Gains**: **{effective_tax_rate:.2f}%** (tax paid relative to pre-tax profits).")
                with tax_col2:
                    fig_bars = plot_tax_comparison_bars(total_invested, current_value, post_tax_value, curr_symbol)
                    st.plotly_chart(fig_bars, use_container_width=True)

            # 4. Key Portfolio Statistics
            st.markdown("### 📊 Key Portfolio Statistics")
            sub_col1, sub_col2, sub_col3, sub_col4 = st.columns(4)
            current_price = float(data.iloc[-1]['Price'])
            with sub_col1:
                st.metric("Total Units Accumulated", f"{total_units:,.4f}")
            with sub_col2:
                st.metric("Average Purchase Price", f"{curr_symbol} {average_cost:,.2f}")
            with sub_col3:
                st.metric("Current Market Price", f"{curr_symbol} {current_price:,.2f}")
            with sub_col4:
                multiplier = current_value / total_invested if total_invested > 0 else 0.0
                st.metric("Wealth Multiplier (Pre-Tax)", f"{multiplier:.2f}x")
                
        with tab2:
            sip_ts, lump_ts, total_capital = compute_comparison(data, amount, sip_stop_date)
            
            # SIP Pre-tax
            sip_final_val_pre = float(sip_ts.iloc[-1]['Portfolio Value'])
            sip_profit_pre = sip_final_val_pre - total_capital
            sip_abs_pre = (sip_profit_pre / total_capital) * 100 if total_capital > 0 else 0.0
            
            sip_cash_flows_pre = [(dt, -amount) for dt in monthly_investment_indices]
            sip_cash_flows_pre.append((data.index[-1], sip_final_val_pre))
            sip_xirr_pre = xirr(sip_cash_flows_pre)
            
            # SIP Tax
            if apply_tax:
                sip_tax_res = calculate_indian_tax(
                    category=category,
                    mf_type=mf_type,
                    is_sip=True,
                    amount=amount,
                    investment_dates=monthly_investment_indices,
                    investment_prices=[float(data.loc[dt]['Price']) for dt in monthly_investment_indices],
                    final_date=data.index[-1],
                    final_price=float(data.iloc[-1]['Price']),
                    current_value=sip_final_val_pre,
                    slab_rate_pct=float(slab_rate)
                )
                sip_tax = sip_tax_res['tax_amount']
                sip_eff_rate = sip_tax_res['effective_rate_pct']
            else:
                sip_tax = 0.0
                sip_eff_rate = 0.0
                
            sip_final_val_post = sip_final_val_pre - sip_tax
            sip_profit_post = sip_final_val_post - total_capital
            sip_abs_post = (sip_profit_post / total_capital) * 100 if total_capital > 0 else 0.0
            sip_cash_flows_post = [(dt, -amount) for dt in monthly_investment_indices]
            sip_cash_flows_post.append((data.index[-1], sip_final_val_post))
            sip_xirr_post = xirr(sip_cash_flows_post)
            
            # Lumpsum Pre-tax
            lump_final_val_pre = float(lump_ts.iloc[-1]['Portfolio Value'])
            lump_profit_pre = lump_final_val_pre - total_capital
            lump_abs_pre = (lump_profit_pre / total_capital) * 100 if total_capital > 0 else 0.0
            lump_cagr_pre = cagr(total_capital, lump_final_val_pre, (data.index[-1] - data.index[0]).days / 365.0)
            
            # Lumpsum Tax
            if apply_tax:
                lump_tax_res = calculate_indian_tax(
                    category=category,
                    mf_type=mf_type,
                    is_sip=False,
                    amount=total_capital,
                    investment_dates=[data.index[0]],
                    investment_prices=[float(data.iloc[0]['Price'])],
                    final_date=data.index[-1],
                    final_price=float(data.iloc[-1]['Price']),
                    current_value=lump_final_val_pre,
                    slab_rate_pct=float(slab_rate)
                )
                lump_tax = lump_tax_res['tax_amount']
                lump_eff_rate = lump_tax_res['effective_rate_pct']
            else:
                lump_tax = 0.0
                lump_eff_rate = 0.0
                
            lump_final_val_post = lump_final_val_pre - lump_tax
            lump_profit_post = lump_final_val_post - total_capital
            lump_abs_post = (lump_profit_post / total_capital) * 100 if total_capital > 0 else 0.0
            lump_cagr_post = cagr(total_capital, lump_final_val_post, (data.index[-1] - data.index[0]).days / 365.0)
            
            # Side by side layouts
            comp_col1, comp_col2 = st.columns(2)
            with comp_col1:
                st.markdown("#### 🔄 Systematic Investment Plan (SIP)")
                st.markdown(metric_card("SIP Total Invested", f"{curr_symbol} {total_capital:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
                if apply_tax:
                    st.markdown(metric_card("SIP Value (Pre-Tax)", f"{curr_symbol} {sip_final_val_pre:,.2f}", delta=sip_profit_pre, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("SIP Est. Tax Paid", f"{curr_symbol} {sip_tax:,.2f}", delta=-sip_tax, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("SIP In-Hand Value (Post-Tax)", f"{curr_symbol} {sip_final_val_post:,.2f}", delta=sip_profit_post, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("SIP Post-Tax Return (XIRR)", f"{sip_xirr_post * 100:.2f}%", delta=sip_abs_post, is_percent=True, curr_symbol=curr_symbol), unsafe_allow_html=True)
                else:
                    st.markdown(metric_card("SIP Final Value", f"{curr_symbol} {sip_final_val_pre:,.2f}", delta=sip_profit_pre, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("SIP Annualized Return (XIRR)", f"{sip_xirr_pre * 100:.2f}%", delta=sip_abs_pre, is_percent=True, curr_symbol=curr_symbol), unsafe_allow_html=True)
            
            with comp_col2:
                st.markdown("#### 💰 Lumpsum Investment")
                st.markdown(metric_card("Lumpsum Total Invested", f"{curr_symbol} {total_capital:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
                if apply_tax:
                    st.markdown(metric_card("Lumpsum Value (Pre-Tax)", f"{curr_symbol} {lump_final_val_pre:,.2f}", delta=lump_profit_pre, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("Lumpsum Est. Tax Paid", f"{curr_symbol} {lump_tax:,.2f}", delta=-lump_tax, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("Lumpsum In-Hand Value (Post-Tax)", f"{curr_symbol} {lump_final_val_post:,.2f}", delta=lump_profit_post, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("Lumpsum Post-Tax Return (CAGR)", f"{lump_cagr_post * 100:.2f}%", delta=lump_abs_post, is_percent=True, curr_symbol=curr_symbol), unsafe_allow_html=True)
                else:
                    st.markdown(metric_card("Lumpsum Final Value", f"{curr_symbol} {lump_final_val_pre:,.2f}", delta=lump_profit_pre, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    st.markdown(metric_card("Lumpsum Annualized Return (CAGR)", f"{lump_cagr_pre * 100:.2f}%", delta=lump_abs_pre, is_percent=True, curr_symbol=curr_symbol), unsafe_allow_html=True)
                
            winning_val_sip = sip_final_val_post if apply_tax else sip_final_val_pre
            winning_val_lump = lump_final_val_post if apply_tax else lump_final_val_pre
            
            if winning_val_sip > winning_val_lump:
                pct_diff = ((winning_val_sip - winning_val_lump) / winning_val_lump) * 100
                st.success(f"🏆 **SIP outperformed Lumpsum by {pct_diff:.2f}% (Post-Tax)** in this period! This is due to Rupee Cost Averaging during market fluctuations.")
            elif winning_val_lump > winning_val_sip:
                pct_diff = ((winning_val_lump - winning_val_sip) / winning_val_sip) * 100
                st.info(f"🏆 **Lumpsum outperformed SIP by {pct_diff:.2f}% (Post-Tax)** in this period. Lumpsum generally performs better during strong, uninterrupted bull markets because all capital compounds from day one.")
            else:
                st.info("Both strategies resulted in the same final value.")
                
            fig_comp = plot_comparison_chart(sip_ts, lump_ts, asset_name)
            st.plotly_chart(fig_comp, use_container_width=True)
            
        with tab3:
            st.markdown("### 🔮 Future SIP Wealth Projector")
            st.write("Estimate the future value of your Systematic Investment Plan based on compound interest and estimated tax liability.")
            
            plan_col1, plan_col2 = st.columns([1, 2])
            with plan_col1:
                proj_amount = st.number_input(
                    "Monthly Investment Amount", 
                    min_value=10.0, 
                    value=float(amount) if invest_type == "SIP" else 5000.0, 
                    step=500.0,
                    key="proj_amount"
                )
                
                default_rate = max(1.0, min(50.0, float(annualized_rate * 100))) if annualized_rate > 0 else 12.0
                
                proj_rate = st.slider(
                    "Expected Annual Return Rate (%)", 
                    min_value=1.0, 
                    max_value=50.0, 
                    value=round(default_rate, 1), 
                    step=0.5,
                    key="proj_rate"
                )
                
                proj_years = st.slider(
                    "Growth Period before SWP starts (Years)", 
                    min_value=1, 
                    max_value=40, 
                    value=10, 
                    key="proj_years"
                )
                
                limit_future_sip = st.checkbox("Limit SIP Duration (Stop & Hold)", value=False, key="limit_future_sip")
                if limit_future_sip:
                    future_sip_years = st.slider(
                        "SIP Active Period (Years)", 
                        min_value=1, 
                        max_value=int(proj_years), 
                        value=min(5, int(proj_years)),
                        key="future_sip_years"
                    )
                else:
                    future_sip_years = proj_years
                
            # Project future tax
            if apply_tax:
                proj_tax, final_proj_val_pre = project_future_tax(
                    category=category,
                    mf_type=mf_type,
                    slab_rate_pct=float(slab_rate),
                    proj_amount=proj_amount,
                    annual_rate=proj_rate,
                    total_years=proj_years,
                    sip_years=future_sip_years
                )
            else:
                proj_tax = 0.0
                _, final_proj_val_pre = project_future_tax(
                    category=category,
                    mf_type=mf_type,
                    slab_rate_pct=float(slab_rate),
                    proj_amount=proj_amount,
                    annual_rate=proj_rate,
                    total_years=proj_years,
                    sip_years=future_sip_years
                )
                
            total_proj_invested = proj_amount * future_sip_years * 12
            final_proj_val_post = final_proj_val_pre - proj_tax
            proj_gain_pre = final_proj_val_pre - total_proj_invested
            proj_gain_post = final_proj_val_post - total_proj_invested
            proj_multiplier = final_proj_val_post / total_proj_invested if total_proj_invested > 0 else 0.0
            proj_eff_tax_rate = (proj_tax / proj_gain_pre) * 100.0 if proj_gain_pre > 0 else 0.0
            
            with plan_col2:
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    st.markdown(metric_card("Total Projected Invested", f"{curr_symbol} {total_proj_invested:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
                    if apply_tax:
                        st.markdown(metric_card("Est. Future Tax (Effective: " + f"{proj_eff_tax_rate:.1f}%)", f"{curr_symbol} {proj_tax:,.2f}", delta=-proj_tax, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    else:
                        st.markdown(metric_card("Projected Return Gain", f"{curr_symbol} {proj_gain_pre:,.2f}", delta=proj_gain_pre, curr_symbol=curr_symbol), unsafe_allow_html=True)
                with f_col2:
                    st.markdown(metric_card("Projected Value (Pre-Tax)", f"{curr_symbol} {final_proj_val_pre:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
                    if apply_tax:
                        st.markdown(metric_card("In-Hand Value (Post-Tax)", f"{curr_symbol} {final_proj_val_post:,.2f}", delta=proj_gain_post, curr_symbol=curr_symbol), unsafe_allow_html=True)
                    else:
                        st.markdown(metric_card("Wealth Multiplier", f"{final_proj_val_pre / total_proj_invested:.2f}x", curr_symbol=curr_symbol), unsafe_allow_html=True)
            
            fig_proj, _, _ = plot_future_projection(proj_amount, proj_rate, proj_years, sip_years=future_sip_years, tax_amount=proj_tax)
            st.plotly_chart(fig_proj, use_container_width=True)
            
            # --- Systematic Withdrawal Plan (SWP) Simulator ---
            st.markdown("---")
            st.markdown("### 💸 Systematic Withdrawal Plan (SWP) Simulator")
            st.write("Simulate post-retirement withdrawals with tax-aware, inflation-adjusted, and sustainability-focused modeling.")
            
            # Default SWP Corpus and Basis based on SIP projector
            default_swp_corpus = final_proj_val_post if apply_tax else final_proj_val_pre
            if final_proj_val_pre > 0:
                default_swp_basis = default_swp_corpus * (total_proj_invested / final_proj_val_pre)
            else:
                default_swp_basis = default_swp_corpus
                
            initial_swp_corpus = st.number_input(
                "Initial Retirement Corpus (₹)",
                min_value=0.0,
                value=float(default_swp_corpus),
                step=50000.0,
                help="The starting value of your retirement portfolio. Auto-filled from the SIP Projector's final value."
            )
            
            swp_mode = st.radio(
                "What would you like to calculate?",
                ["💰 How much can I withdraw monthly?", "⏳ How long will my money last?"],
                horizontal=True,
                help="Choose whether to calculate a safe monthly withdrawal amount for a target period, or to see how long your money lasts with a target monthly withdrawal."
            )
            
            col_ctrl1, col_ctrl2 = st.columns(2)
            
            with col_ctrl1:
                if swp_mode == "💰 How much can I withdraw monthly?":
                    swp_years = st.slider(
                        "Target Withdrawal Period (Years)",
                        min_value=1,
                        max_value=40,
                        value=25,
                        step=1,
                        help="The number of years you want your portfolio to last."
                    )
                else:
                    # Depletion Timeline Mode: input withdrawal amount
                    # Default monthly withdrawal is ~4% annual withdrawal rate
                    suggested_w = max(1000.0, round((initial_swp_corpus * 0.04) / 12, -3))
                    
                    percent_withdrawal = st.session_state.get("percent_withdrawal", False)
                    
                    if percent_withdrawal:
                        monthly_withdrawal = st.number_input(
                            "Target Annual Withdrawal Rate (%)",
                            min_value=0.1,
                            max_value=50.0,
                            value=4.0,
                            step=0.5,
                            help="The annual percentage of the portfolio value to withdraw (e.g., 4.0 for the 4% rule)."
                        )
                    else:
                        monthly_withdrawal = st.number_input(
                            "Target Monthly Withdrawal (₹)",
                            min_value=100.0,
                            value=float(suggested_w),
                            step=1000.0,
                            help="The gross amount you wish to withdraw each month."
                        )
                        
            with col_ctrl2:
                if swp_mode == "💰 How much can I withdraw monthly?":
                    st.info("ℹ️ The engine will compute the maximum monthly withdrawal that keeps your portfolio above zero for the target period.")
                else:
                    swp_years = st.slider(
                        "Target Withdrawal Period (Years)",
                        min_value=1,
                        max_value=40,
                        value=25,
                        step=1,
                        help="The target period you want your portfolio to survive."
                    )
                    
            with st.expander("🛠️ Advanced SWP Settings"):
                adv_col1, adv_col2 = st.columns(2)
                with adv_col1:
                    swp_rate = st.slider(
                        "Expected Annual Return Rate during SWP (%)",
                        min_value=1.0,
                        max_value=50.0,
                        value=float(proj_rate),
                        step=0.5,
                        help="The expected return of your portfolio during the withdrawal phase."
                    )
                    swp_inflation = st.slider(
                        "Annual Inflation Rate (%)",
                        min_value=0.0,
                        max_value=20.0,
                        value=6.0,
                        step=0.5,
                        help="Expected average inflation. If adjusted, withdrawals will increase annually to maintain purchasing power."
                    )
                    initial_swp_basis = st.number_input(
                        "Initial Cost Basis (₹)",
                        min_value=0.0,
                        value=float(default_swp_basis),
                        step=50000.0,
                        help="The total capital invested to build this corpus. Used to calculate capital gains tax on withdrawals."
                    )
                with adv_col2:
                    swp_tax_option = st.selectbox(
                        "Tax Rules for Retirement Phase",
                        ["Inherit from Sidebar Asset", "Equity (12.5% LTCG, ₹1.25L exemption)", "Debt Funds (Taxed at Slab)", "Crypto (30% Flat Tax)", "No Tax (Tax-free)"],
                        help="Select how withdrawals are taxed. By default, it inherits the rules based on the main asset selected."
                    )
                    
                    inflation_adjusted = st.checkbox(
                        "Inflation-adjusted withdrawals",
                        value=True,
                        help="Increase withdrawals annually by the inflation rate to maintain real purchasing power."
                    )
                    
                    if swp_mode == "⏳ How long will my money last?":
                        percent_withdrawal = st.checkbox(
                            "Use % of Portfolio Strategy",
                            value=False,
                            key="percent_withdrawal",
                            help="Withdraw a fixed percentage of the remaining portfolio annually rather than a fixed Rupee amount."
                        )
                    else:
                        percent_withdrawal = False
                        
            # Map SWP Tax Rules
            if swp_tax_option == "Inherit from Sidebar Asset":
                swp_category = category
                swp_mf_type = mf_type
                swp_slab_rate = slab_rate
            elif swp_tax_option == "Equity (12.5% LTCG, ₹1.25L exemption)":
                swp_category = "Mutual Fund"
                swp_mf_type = "Equity-Oriented"
                swp_slab_rate = 0.0
            elif swp_tax_option == "Debt Funds (Taxed at Slab)":
                swp_category = "Mutual Fund"
                swp_mf_type = "Debt-Oriented"
                swp_slab_rate = slab_rate
            elif swp_tax_option == "Crypto (30% Flat Tax)":
                swp_category = "Crypto"
                swp_mf_type = None
                swp_slab_rate = 0.0
            else: # No Tax (Tax-free)
                swp_category = "Mutual Fund"
                swp_mf_type = "Debt-Oriented"
                swp_slab_rate = 0.0
                
            if not apply_tax:
                swp_category = "Mutual Fund"
                swp_mf_type = "Debt-Oriented"
                swp_slab_rate = 0.0
                
            # Run simulation or solver
            if swp_mode == "💰 How much can I withdraw monthly?":
                solved_w = solve_sustainable_withdrawal(
                    initial_corpus=initial_swp_corpus,
                    initial_basis=initial_swp_basis,
                    annual_return_rate=swp_rate,
                    inflation_rate=swp_inflation,
                    category=swp_category,
                    mf_type=swp_mf_type,
                    slab_rate_pct=swp_slab_rate,
                    years=swp_years,
                    inflation_adjusted=inflation_adjusted
                )
                
                res = run_swp_simulation(
                    initial_corpus=initial_swp_corpus,
                    initial_basis=initial_swp_basis,
                    monthly_withdrawal=solved_w,
                    annual_return_rate=swp_rate,
                    inflation_rate=swp_inflation,
                    category=swp_category,
                    mf_type=swp_mf_type,
                    slab_rate_pct=swp_slab_rate,
                    max_years=swp_years,
                    inflation_adjusted=inflation_adjusted,
                    percent_withdrawal=False
                )
                display_w = solved_w
            else:
                res = run_swp_simulation(
                    initial_corpus=initial_swp_corpus,
                    initial_basis=initial_swp_basis,
                    monthly_withdrawal=monthly_withdrawal,
                    annual_return_rate=swp_rate,
                    inflation_rate=swp_inflation,
                    category=swp_category,
                    mf_type=swp_mf_type,
                    slab_rate_pct=swp_slab_rate,
                    max_years=swp_years,
                    inflation_adjusted=inflation_adjusted,
                    percent_withdrawal=percent_withdrawal
                )
                if percent_withdrawal:
                    display_w = res['withdrawals'][0] if res['withdrawals'] else 0.0
                else:
                    display_w = monthly_withdrawal
                    
            # Calculate metrics for display
            post_tax_income = res['in_hand_withdrawals'][0] if len(res['in_hand_withdrawals']) > 0 else 0.0
            swr_val = (12 * display_w) / initial_swp_corpus * 100 if initial_swp_corpus > 0 else 0.0
            
            # Survival indicator logic
            if res['depleted']:
                survival_status = "Depletes Early"
                survival_color = "red"
                survival_icon = "🔴"
            elif res['portfolio_values'][-1] < initial_swp_corpus * 0.1 or swr_val > 5.5:
                survival_status = "Risky / Critical"
                survival_color = "yellow"
                survival_icon = "🟡"
            else:
                survival_status = "Sustainable"
                survival_color = "green"
                survival_icon = "🟢"
                
            # Display Plain-English Verdict & Suggestion Engine
            st.markdown("#### 🎯 Plan Verdict")
            if swp_mode == "💰 How much can I withdraw monthly?":
                if solved_w > 10.0:
                    st.info(f"💡 **Verdict**: To make your corpus last **{swp_years} years**, you can safely withdraw a maximum of **{curr_symbol} {solved_w:,.0f} / month** (estimated **{curr_symbol} {post_tax_income:,.0f} / month** in-hand post-tax).")
                else:
                    st.error(f"🔴 **Verdict**: Your corpus is too small to sustain any withdrawals for **{swp_years} years** after accounting for inflation and taxes.")
            else:
                # Depletion Timeline Mode
                if res['depleted']:
                    def solve_required_corpus(target_w, initial_basis_ratio, annual_return_rate, inflation_rate, category, mf_type, slab_rate_pct, years, inflation_adjusted):
                        low_c = 0.0
                        high_c = target_w * 12 * years * 2
                        if high_c < 10000.0:
                            high_c = 10000000.0
                        for _ in range(35):
                            mid_c = (low_c + high_c) / 2.0
                            basis_mid = mid_c * initial_basis_ratio
                            sim = run_swp_simulation(
                                initial_corpus=mid_c,
                                initial_basis=basis_mid,
                                monthly_withdrawal=target_w,
                                annual_return_rate=annual_return_rate,
                                inflation_rate=inflation_rate,
                                category=category,
                                mf_type=mf_type,
                                slab_rate_pct=slab_rate_pct,
                                max_years=years,
                                inflation_adjusted=inflation_adjusted,
                                percent_withdrawal=False
                            )
                            if sim['depleted']:
                                low_c = mid_c
                            else:
                                high_c = mid_c
                        return (low_c + high_c) / 2.0

                    basis_ratio = (initial_swp_basis / initial_swp_corpus) if initial_swp_corpus > 0 else 1.0
                    
                    if percent_withdrawal:
                        st.error(f"🔴 **Verdict**: Your target withdrawal rate of **{monthly_withdrawal:.2f}% / year** will deplete your portfolio in **{res['years_lasted']:.1f} years** (before your target of {swp_years} years).")
                    else:
                        req_c = solve_required_corpus(
                            target_w=monthly_withdrawal,
                            initial_basis_ratio=basis_ratio,
                            annual_return_rate=swp_rate,
                            inflation_rate=swp_inflation,
                            category=swp_category,
                            mf_type=swp_mf_type,
                            slab_rate_pct=swp_slab_rate,
                            years=swp_years,
                            inflation_adjusted=inflation_adjusted
                        )
                        sust_w = solve_sustainable_withdrawal(
                            initial_corpus=initial_swp_corpus,
                            initial_basis=initial_swp_basis,
                            annual_return_rate=swp_rate,
                            inflation_rate=swp_inflation,
                            category=swp_category,
                            mf_type=swp_mf_type,
                            slab_rate_pct=swp_slab_rate,
                            years=swp_years,
                            inflation_adjusted=inflation_adjusted
                        )
                        
                        st.error(f"🔴 **Verdict**: Your corpus of **{curr_symbol} {initial_swp_corpus:,.0f}** will run out of funds early in **{res['years_lasted']:.1f} years** at a monthly withdrawal of **{curr_symbol} {monthly_withdrawal:,.0f}**.")
                        
                        # Show Actionable Recommendations
                        st.markdown("##### 💡 Recommendations to achieve your goal:")
                        st.markdown(f"""
                        * 📉 **Option A (Lower Withdrawal)**: Reduce your monthly withdrawal to **{curr_symbol} {sust_w:,.0f} / month** to make your current corpus last the full **{swp_years} years**.
                        * 📈 **Option B (Higher Capital)**: Increase your retirement corpus by **{curr_symbol} {max(0.0, req_c - initial_swp_corpus):,.0f}** (to a total of **{curr_symbol} {req_c:,.0f}**) to safely sustain your target withdrawal of **{curr_symbol} {monthly_withdrawal:,.0f} / month** for **{swp_years} years**.
                        * ⏳ **Option C (Extend Savings)**: Go to the SIP Projector above and increase your savings period by a few years to build the required **{curr_symbol} {req_c:,.0f}** corpus before starting withdrawals.
                        """)
                else:
                    if percent_withdrawal:
                        st.success(f"🟢 **Verdict**: Your percentage-based withdrawal rate of **{monthly_withdrawal:.2f}% / year** is **fully sustainable**! Your portfolio survives the target **{swp_years} years** with a remaining balance of **{curr_symbol} {res['portfolio_values'][-1]:,.0f}**.")
                    else:
                        st.success(f"🟢 **Verdict**: Your corpus is **fully sustainable**! At **{curr_symbol} {monthly_withdrawal:,.0f} / month**, your money will last the entire **{swp_years} years** with a remaining balance of **{curr_symbol} {res['portfolio_values'][-1]:,.0f}**.")
                
            # Display metrics cards
            st.markdown("#### 📊 Key SWP Metrics")
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                income_label = "Initial Post-Tax Monthly Income"
                st.markdown(metric_card(income_label, f"{curr_symbol} {post_tax_income:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
            with m_col2:
                st.markdown(metric_card("Total Amount Withdrawn", f"{curr_symbol} {res['total_withdrawn']:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
            with m_col3:
                st.markdown(metric_card("Total Capital Gains Tax Paid", f"{curr_symbol} {res['total_tax_paid']:,.2f}", delta=-res['total_tax_paid'] if res['total_tax_paid'] > 0 else None, curr_symbol=curr_symbol), unsafe_allow_html=True)
                
            m_col4, m_col5, m_col6 = st.columns(3)
            with m_col4:
                lifespan_text = f"{res['years_lasted']:.1f} Years"
                if res['depleted']:
                    lifespan_text += " (Depleted)"
                else:
                    lifespan_text += " (Sustainable)"
                st.markdown(metric_card("Portfolio Lifespan", lifespan_text, curr_symbol=curr_symbol), unsafe_allow_html=True)
            with m_col5:
                st.markdown(metric_card("Remaining Portfolio Balance", f"{curr_symbol} {res['portfolio_values'][-1]:,.2f}", curr_symbol=curr_symbol), unsafe_allow_html=True)
            with m_col6:
                st.markdown(metric_card("Safe Withdrawal Rate (SWR)", f"{swr_val:.2f}%", curr_symbol=""), unsafe_allow_html=True)
                
            # Sustainability info callout
            if survival_icon == "🟢":
                st.success(f"🟢 **Sustainability Status: {survival_status}** | Your portfolio sustains withdrawals for the full {swp_years} years. Your initial Safe Withdrawal Rate of {swr_val:.2f}% is within or close to the recommended 4% retirement benchmark.")
            elif survival_icon == "🟡":
                st.warning(f"🟡 **Sustainability Status: {survival_status}** | Your portfolio survives but is risky. It leaves a very small remaining corpus (< 10% of initial) or has an SWR ({swr_val:.2f}%) higher than the 4% benchmark. Watch out for inflation!")
            else:
                st.error(f"🔴 **Sustainability Status: {survival_status}** | Your portfolio runs out of funds in {res['years_lasted']:.1f} years. Consider reducing your monthly withdrawal amount, increasing your initial retirement corpus, or lowering your retirement expectations.")
                
            # Timeline Chart
            st.plotly_chart(plot_swp_chart(res, curr_symbol), use_container_width=True)
            
            # Smart Insights Engine
            st.markdown("#### 🧠 Smart Insights Engine")
            insights = []
            
            if res['depleted']:
                insights.append(f"🔴 **Portfolio Depletion**: Funds run out in **{res['years_lasted']:.1f} years** under simulated parameters.")
            else:
                insights.append(f"🟢 **Portfolio Sustainability**: Portfolio successfully sustains withdrawals for the entire **{swp_years} years** and leaves a remaining balance of **{curr_symbol}{res['portfolio_values'][-1]:,.2f}**.")
                
            if res['depleted'] and not percent_withdrawal:
                reduced_w = display_w * 0.9
                res_reduced = run_swp_simulation(
                    initial_corpus=initial_swp_corpus,
                    initial_basis=initial_swp_basis,
                    monthly_withdrawal=reduced_w,
                    annual_return_rate=swp_rate,
                    inflation_rate=swp_inflation,
                    category=swp_category,
                    mf_type=swp_mf_type,
                    slab_rate_pct=swp_slab_rate,
                    max_years=swp_years,
                    inflation_adjusted=inflation_adjusted,
                    percent_withdrawal=False
                )
                if not res_reduced['depleted']:
                    insights.append(f"💡 **Lifespan Extension**: Reducing your monthly withdrawal by 10% (to **{curr_symbol}{reduced_w:,.0f}**) makes your portfolio **fully sustainable** for the entire {swp_years} years.")
                else:
                    extension = res_reduced['years_lasted'] - res['years_lasted']
                    if extension > 0.1:
                        insights.append(f"💡 **Lifespan Extension**: Reducing your monthly withdrawal by 10% (to **{curr_symbol}{reduced_w:,.0f}**) extends your portfolio lifespan by **{extension:.1f} years** (lasts {res_reduced['years_lasted']:.1f} years).")
                        
            if inflation_adjusted and swp_inflation > 0.0:
                res_no_inf = run_swp_simulation(
                    initial_corpus=initial_swp_corpus,
                    initial_basis=initial_swp_basis,
                    monthly_withdrawal=display_w,
                    annual_return_rate=swp_rate,
                    inflation_rate=0.0,
                    category=swp_category,
                    mf_type=swp_mf_type,
                    slab_rate_pct=swp_slab_rate,
                    max_years=swp_years,
                    inflation_adjusted=False,
                    percent_withdrawal=percent_withdrawal
                )
                if res['depleted']:
                    if not res_no_inf['depleted']:
                        insights.append(f"🎈 **Inflation Impact**: Inflation-adjusted withdrawals reduce your portfolio lifespan from fully sustainable to **{res['years_lasted']:.1f} years**.")
                    else:
                        extension = res_no_inf['years_lasted'] - res['years_lasted']
                        if extension > 0.1:
                            insights.append(f"🎈 **Inflation Impact**: Adjusting withdrawals for inflation reduces your portfolio lifespan by **{extension:.1f} years** (would last {res_no_inf['years_lasted']:.1f} years without inflation).")
                else:
                    diff_corpus = res_no_inf['portfolio_values'][-1] - res['portfolio_values'][-1]
                    if diff_corpus > 100.0:
                        insights.append(f"🎈 **Inflation Impact**: Adjusting withdrawals for inflation reduces your final remaining corpus by **{curr_symbol}{diff_corpus:,.2f}** (would be **{curr_symbol}{res_no_inf['portfolio_values'][-1]:,.2f}** without inflation).")
                        
            if res['total_tax_paid'] > 0.0:
                tax_impact_pct = (res['total_tax_paid'] / res['total_withdrawn']) * 100 if res['total_withdrawn'] > 0 else 0.0
                insights.append(f"💸 **Tax Impact**: Capital gains taxes reduce your effective retirement income by **{tax_impact_pct:.1f}%**. Total estimated tax paid over the simulation is **{curr_symbol}{res['total_tax_paid']:,.2f}**.")
                
            for insight in insights:
                st.markdown(f"- {insight}")

            
        # Education section
        st.markdown("---")
        st.markdown("### 🎓 Understanding Indian Capital Gains Tax (Union Budget 2024)")
        
        tax_col1, tax_col2, tax_col3 = st.columns(3)
        with tax_col1:
            st.markdown("""
            <div class="info-card" style="border-left-color: #00D1B2;">
                <div class="info-card-title">📈 Equity Stocks & Mutual Funds</div>
                Holding period threshold is <b>12 months</b>.
                <ul>
                    <li><b>LTCG</b> (> 1 yr): <b>12.5% tax</b> on gains. First <b>₹1.25 Lakh</b> of total LTCG gains in a financial year is fully tax-free.</li>
                    <li><b>STCG</b> (<= 1 yr): Flat <b>20% tax</b> on gains.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with tax_col2:
            st.markdown("""
            <div class="info-card" style="border-left-color: #FF3860;">
                <div class="info-card-title">🪙 Crypto Assets (VDAs)</div>
                Virtual Digital Assets (cryptocurrency/NFTs) are taxed at a flat rate of <b>30%</b> on capital gains under Section 115BBH. 
                <ul>
                    <li>No holding period distinctions (same rate for short or long term).</li>
                    <li>Losses cannot be set off against other income classes.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
        with tax_col3:
            st.markdown("""
            <div class="info-card" style="border-left-color: #FFDD57;">
                <div class="info-card-title">🏦 Debt Mutual Funds</div>
                Debt mutual funds purchased on or after April 1, 2023, do not qualify for long-term tax rates.
                <ul>
                    <li>All gains are added directly to your individual taxable income.</li>
                    <li>Taxed according to your applicable <b>personal income tax slab rate</b> (up to 30%+ depending on your bracket).</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("No data available for the selected dates or ticker symbol. Please try again.")
