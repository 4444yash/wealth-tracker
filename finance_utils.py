import datetime
import pandas as pd

def to_date(d):
    """Normalize various date formats into datetime.date objects."""
    if isinstance(d, pd.Timestamp):
        return d.to_pydatetime().date()
    elif isinstance(d, datetime.datetime):
        return d.date()
    elif isinstance(d, str):
        return pd.to_datetime(d).date()
    return d

def xirr(cash_flows):
    """
    Calculate the Extended Internal Rate of Return (XIRR) for a series of cash flows.
    
    Parameters:
    cash_flows (list of tuples): List of (date, amount) tuples.
        - Negative amounts represent investments (outflows).
        - Positive amounts represent returns or current portfolio value (inflows).
        
    Returns:
    float: Annualized rate of return (e.g. 0.125 for 12.5%). Returns 0.0 if calculation fails.
    """
    cf_valid = [(to_date(dt), float(val)) for dt, val in cash_flows if val != 0]
    if len(cf_valid) < 2:
        return 0.0
        
    has_neg = any(cf[1] < 0 for cf in cf_valid)
    has_pos = any(cf[1] > 0 for cf in cf_valid)
    
    if not (has_neg and has_pos):
        return 0.0
        
    t0 = cf_valid[0][0]
    
    def npv(r):
        total = 0.0
        for dt, val in cf_valid:
            t = (dt - t0).days / 365.0
            base = 1.0 + r
            if base <= 1e-6:
                base = 1e-6
            total += val / (base ** t)
        return total

    low = -0.999
    high = 10.0
    
    f_low = npv(low)
    f_high = npv(high)
    
    if f_low * f_high > 0:
        for _ in range(10):
            high *= 2.0
            f_high = npv(high)
            if f_low * f_high <= 0:
                break
                
    if f_low * f_high > 0:
        total_invested = abs(sum(cf[1] for cf in cf_valid if cf[1] < 0))
        final_val = sum(cf[1] for cf in cf_valid if cf[1] > 0)
        years = (cf_valid[-1][0] - t0).days / 365.0
        if total_invested > 0 and final_val > 0 and years > 0:
            return (final_val / total_invested) ** (1.0 / years) - 1.0
        return 0.0

    for _ in range(80):
        mid = (low + high) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-6:
            return mid
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
            
    return (low + high) / 2.0

def cagr(initial_val, current_val, years):
    """Calculate the Compound Annual Growth Rate (CAGR)."""
    if initial_val <= 0 or current_val <= 0 or years <= 0:
        return 0.0
    return (current_val / initial_val) ** (1.0 / years) - 1.0

def calculate_indian_tax(category, mf_type, is_sip, amount, investment_dates, investment_prices, final_date, final_price, current_value, slab_rate_pct=30.0):
    """
    Calculate estimated Indian Capital Gains Tax for the investment.
    
    Parameters:
    - category (str): "Stocks", "Crypto", or "Mutual Fund"
    - mf_type (str): "Equity-Oriented" or "Debt-Oriented" (only for Mutual Funds)
    - is_sip (bool): True if SIP, False if Lumpsum
    - amount (float): Monthly SIP amount or Lumpsum amount
    - investment_dates (list): Dates when investments were made
    - investment_prices (list): Prices on purchase dates
    - final_date (datetime.date): Evaluation date
    - final_price (float): Asset price on evaluation date
    - current_value (float): Current valuation
    - slab_rate_pct (float): Investor's income tax slab rate (e.g. 30.0)
    
    Returns:
    - dict: Detailed tax parameters and pre-tax/post-tax breakdown
    """
    total_invested = sum(amount for _ in investment_dates) if is_sip else amount
    pre_tax_gains = max(0.0, current_value - total_invested)
    
    if pre_tax_gains <= 0:
        return {
            'tax_amount': 0.0,
            'effective_rate_pct': 0.0,
            'ltcg_gains': 0.0,
            'stcg_gains': 0.0,
            'taxable_ltcg': 0.0,
            'taxable_stcg': 0.0,
            'ltcg_tax': 0.0,
            'stcg_tax': 0.0,
            'pre_tax_gains': 0.0,
            'post_tax_gains': 0.0,
            'details': "No capital gains tax (investment in loss or zero return)."
        }
        
    tax_amount = 0.0
    ltcg_gains = 0.0
    stcg_gains = 0.0
    details = ""
    
    # 1. Crypto / Virtual Digital Assets
    if category == "Crypto":
        tax_amount = 0.30 * pre_tax_gains
        details = "Flat 30% tax on Crypto/VDA gains under Section 115BBH."
        return {
            'tax_amount': tax_amount,
            'effective_rate_pct': 30.0,
            'ltcg_gains': 0.0,
            'stcg_gains': pre_tax_gains,
            'taxable_ltcg': 0.0,
            'taxable_stcg': pre_tax_gains,
            'ltcg_tax': 0.0,
            'stcg_tax': tax_amount,
            'pre_tax_gains': pre_tax_gains,
            'post_tax_gains': pre_tax_gains - tax_amount,
            'details': details
        }
        
    # 2. Debt Mutual Fund
    if category == "Mutual Fund" and mf_type == "Debt-Oriented":
        slab_fraction = slab_rate_pct / 100.0
        tax_amount = slab_fraction * pre_tax_gains
        details = f"Taxed at slab rate ({slab_rate_pct}%) as per individual tax bracket."
        return {
            'tax_amount': tax_amount,
            'effective_rate_pct': slab_rate_pct,
            'ltcg_gains': 0.0,
            'stcg_gains': pre_tax_gains,
            'taxable_ltcg': 0.0,
            'taxable_stcg': pre_tax_gains,
            'ltcg_tax': 0.0,
            'stcg_tax': tax_amount,
            'pre_tax_gains': pre_tax_gains,
            'post_tax_gains': pre_tax_gains - tax_amount,
            'details': details
        }
        
    # 3. Equity (Stocks & Equity Mutual Funds)
    # We trace each installment's holding period
    final_dt = to_date(final_date)
    for dt, price in zip(investment_dates, investment_prices):
        units = amount / price
        final_val_inst = units * final_price
        gain = final_val_inst - amount
        
        days_held = (final_dt - to_date(dt)).days
        if days_held > 365:
            ltcg_gains += gain
        else:
            stcg_gains += gain
            
    # Clamp negative gains to zero for simple tax bracket calculation (conservative)
    ltcg_gains = max(0.0, ltcg_gains)
    stcg_gains = max(0.0, stcg_gains)
    
    # LTCG Exemption: ₹1.25 Lakh (effective from July 23, 2024 onwards)
    taxable_ltcg = max(0.0, ltcg_gains - 125000.0)
    ltcg_tax = 0.125 * taxable_ltcg
    
    # STCG Tax: 20%
    stcg_tax = 0.20 * stcg_gains
    
    tax_amount = ltcg_tax + stcg_tax
    effective_rate_pct = (tax_amount / pre_tax_gains) * 100.0 if pre_tax_gains > 0 else 0.0
    
    details = f"LTCG taxed at 12.5% (after ₹1.25L exemption); STCG taxed at 20%."
    
    return {
        'tax_amount': tax_amount,
        'effective_rate_pct': effective_rate_pct,
        'ltcg_gains': ltcg_gains,
        'stcg_gains': stcg_gains,
        'taxable_ltcg': taxable_ltcg,
        'taxable_stcg': stcg_gains,
        'ltcg_tax': ltcg_tax,
        'stcg_tax': stcg_tax,
        'pre_tax_gains': pre_tax_gains,
        'post_tax_gains': max(0.0, pre_tax_gains - tax_amount),
        'details': details
    }

def project_future_tax(category, mf_type, slab_rate_pct, proj_amount, annual_rate, total_years, sip_years=None):
    """
    Project tax liabilities at the end of a future investment timeline with optional limited SIP duration.
    
    Parameters:
    - total_years (int): Total simulation timeline (years)
    - sip_years (int): Number of years the SIP is active. If None or equal to total_years, SIP runs for the whole timeline.
    
    Returns:
    - (tax_amount, total_fv)
    """
    if sip_years is None or sip_years > total_years:
        sip_years = total_years
        
    total_months = total_years * 12
    sip_months = int(sip_years * 12)
    monthly_rate = (annual_rate / 100.0) / 12
    
    ltcg_gains = 0.0
    stcg_gains = 0.0
    total_fv = 0.0
    total_invested = proj_amount * sip_months
    
    # Calculate for each active SIP installment
    for m in range(1, sip_months + 1):
        # h_months is how long this installment compounds till the end of the total timeline
        h_months = total_months - m + 1
        if monthly_rate > 0:
            fv_inst = proj_amount * ((1 + monthly_rate) ** h_months)
        else:
            fv_inst = proj_amount
        
        gain = fv_inst - proj_amount
        total_fv += fv_inst
        
        if category == "Crypto" or (category == "Mutual Fund" and mf_type == "Debt-Oriented"):
            pass
        else:
            if h_months >= 12:
                ltcg_gains += gain
            else:
                stcg_gains += gain
                
    pre_tax_gains = max(0.0, total_fv - total_invested)
    if pre_tax_gains <= 0:
        return 0.0, total_fv
        
    if category == "Crypto":
        tax = 0.30 * pre_tax_gains
    elif category == "Mutual Fund" and mf_type == "Debt-Oriented":
        tax = (slab_rate_pct / 100.0) * pre_tax_gains
    else:
        # Equity: LTCG 12.5% after 1.25L exemption, STCG 20%
        taxable_ltcg = max(0.0, ltcg_gains - 125000.0)
        tax = (0.125 * taxable_ltcg) + (0.20 * max(0.0, stcg_gains))
        
    return tax, total_fv

def run_swp_simulation(initial_corpus, initial_basis, monthly_withdrawal, annual_return_rate, inflation_rate, category, mf_type, slab_rate_pct, max_years, inflation_adjusted=False, percent_withdrawal=False):
    """
    Simulate systematic withdrawals month-by-month.
    
    Returns a dict with simulation timeline, values, and stats.
    """
    months = int(max_years * 12)
    monthly_rate = (annual_return_rate / 100.0) / 12
    
    portfolio = float(initial_corpus)
    basis = float(initial_basis)
    
    portfolio_values = [portfolio]
    withdrawals = []
    taxes = []
    in_hand_withdrawals = []
    dates = []
    
    total_withdrawn = 0.0
    total_tax_paid = 0.0
    
    w_amount = float(monthly_withdrawal)
    today = datetime.date.today()
    
    yearly_gain = 0.0
    depleted = False
    months_lasted = 0
    
    for m in range(1, months + 1):
        dt = today + datetime.timedelta(days=m * 30.436)
        dates.append(dt)
        
        if portfolio <= 0:
            portfolio = 0.0
            withdrawals.append(0.0)
            taxes.append(0.0)
            in_hand_withdrawals.append(0.0)
            portfolio_values.append(0.0)
            depleted = True
            continue
            
        months_lasted += 1
        
        # 1. Determine monthly withdrawal amount
        if percent_withdrawal:
            # w_amount is annual percentage
            m_withdrawal = portfolio * (w_amount / 100.0) / 12
        else:
            m_withdrawal = w_amount
            # Adjust for inflation annually (at the start of month 13, 25, etc.)
            if inflation_adjusted and m > 1 and (m - 1) % 12 == 0:
                w_amount *= (1 + (inflation_rate / 100.0))
                m_withdrawal = w_amount
                
        # Ensure we don't withdraw more than what is left
        if m_withdrawal > portfolio:
            m_withdrawal = portfolio
            
        # 2. Calculate tax on withdrawal
        tax = 0.0
        gains_ratio = (portfolio - basis) / portfolio if portfolio > 0 else 0.0
        gains_ratio = max(0.0, gains_ratio)
        
        gw = m_withdrawal * gains_ratio
        
        # Reset yearly gain at the start of each year
        if (m - 1) % 12 == 0:
            yearly_gain = 0.0
            
        if category == "Crypto":
            tax = 0.30 * gw
        elif category == "Mutual Fund" and mf_type == "Debt-Oriented":
            tax = (slab_rate_pct / 100.0) * gw
        else:
            # Equity: 12.5% tax on cumulative yearly gains above 1.25L
            prev_yearly_gain = yearly_gain
            yearly_gain += gw
            
            if yearly_gain > 125000.0:
                taxable_portion = yearly_gain - max(125000.0, prev_yearly_gain)
                tax = 0.125 * taxable_portion
                
        # 3. Update basis proportionally
        f = m_withdrawal / portfolio if portfolio > 0 else 0.0
        basis = basis * (1.0 - f)
        
        # 4. Debit portfolio and compound remaining balance
        portfolio = (portfolio - m_withdrawal) * (1.0 + monthly_rate)
        if portfolio < 0.0:
            portfolio = 0.0
            
        portfolio_values.append(portfolio)
        withdrawals.append(m_withdrawal)
        taxes.append(tax)
        in_hand_withdrawals.append(max(0.0, m_withdrawal - tax))
        
        total_withdrawn += m_withdrawal
        total_tax_paid += tax
        
    years_lasted = months_lasted / 12.0
    
    return {
        "dates": dates,
        "portfolio_values": portfolio_values[1:],
        "withdrawals": withdrawals,
        "taxes": taxes,
        "in_hand_withdrawals": in_hand_withdrawals,
        "total_withdrawn": total_withdrawn,
        "total_tax_paid": total_tax_paid,
        "years_lasted": years_lasted,
        "depleted": depleted
    }

def solve_sustainable_withdrawal(initial_corpus, initial_basis, annual_return_rate, inflation_rate, category, mf_type, slab_rate_pct, years, inflation_adjusted=False):
    """
    Find the sustainable monthly withdrawal (W) in Rupees using bisection method.
    """
    low = 0.0
    high = float(initial_corpus)
    
    for _ in range(50):
        mid = (low + high) / 2.0
        res = run_swp_simulation(
            initial_corpus=initial_corpus,
            initial_basis=initial_basis,
            monthly_withdrawal=mid,
            annual_return_rate=annual_return_rate,
            inflation_rate=inflation_rate,
            category=category,
            mf_type=mf_type,
            slab_rate_pct=slab_rate_pct,
            max_years=years,
            inflation_adjusted=inflation_adjusted,
            percent_withdrawal=False
        )
        
        if res['depleted']:
            high = mid
        else:
            final_bal = res['portfolio_values'][-1]
            if final_bal < 100.0:
                # Close enough to 0 depletion
                low = mid
            else:
                low = mid
                
    return (low + high) / 2.0
