"""
Scoring module - Calculate buy consideration scores for stocks.
"""


def calculate_score(metrics: dict) -> dict:
    """
    Calculate a composite buy consideration score (0-100).
    Returns score and breakdown of components.
    """
    scores = {}
    weights = {}
    
    # 1. Valuation Score (25% weight)
    valuation_score = 50  # Start neutral
    weights['valuation'] = 25
    
    pe = metrics.get('pe_ratio')
    if pe is not None and pe > 0:
        if pe < 15:
            valuation_score += 30
        elif pe < 20:
            valuation_score += 15
        elif pe < 30:
            valuation_score += 0
        elif pe < 50:
            valuation_score -= 15
        else:
            valuation_score -= 30
    
    peg = metrics.get('dividend_yield')
    if peg is not None and peg > 0:
        if peg > 0.04:
            valuation_score += 20
        elif peg > 0.02:
            valuation_score += 10
        else:
            valuation_score += 5
    
    scores['valuation'] = max(0, min(100, valuation_score))
    
    # 2. Profitability Score (20% weight)
    profit_score = 50
    weights['profitability'] = 20
    
    roe = metrics.get('return_on_equity')
    if roe is not None:
        if roe > 0.20:
            profit_score += 25
        elif roe > 0.15:
            profit_score += 15
        elif roe > 0.10:
            profit_score += 5
        elif roe > 0:
            profit_score -= 5
        else:
            profit_score -= 20
    
    margin = metrics.get('profit_margin')
    if margin is not None:
        if margin > 0.20:
            profit_score += 25
        elif margin > 0.10:
            profit_score += 15
        elif margin > 0:
            profit_score += 5
        else:
            profit_score -= 20
    
    scores['profitability'] = max(0, min(100, profit_score))
    
    # 3. Growth Score (20% weight)
    growth_score = 50
    weights['growth'] = 20
    
    rev_growth = metrics.get('revenue_growth')
    if rev_growth is not None:
        if rev_growth > 0.25:
            growth_score += 25
        elif rev_growth > 0.10:
            growth_score += 15
        elif rev_growth > 0:
            growth_score += 5
        else:
            growth_score -= 15
    
    earn_growth = metrics.get('earnings_growth')
    if earn_growth is not None:
        if earn_growth > 0.25:
            earn_growth_bonus = 25
        elif earn_growth > 0.10:
            earn_growth_bonus = 15
        elif earn_growth > 0:
            earn_growth_bonus = 5
        else:
            earn_growth_bonus = -15
        growth_score += earn_growth_bonus
    
    scores['growth'] = max(0, min(100, growth_score))
    
    # 4. Financial Health Score (20% weight)
    health_score = 50
    weights['financial_health'] = 20
    
    de = metrics.get('debt_to_equity')
    if de is not None:
        if de < 30:
            health_score += 25
        elif de < 50:
            health_score += 15
        elif de < 100:
            health_score += 0
        elif de < 200:
            health_score -= 15
        else:
            health_score -= 25
    
    cr = metrics.get('current_ratio')
    if cr is not None:
        if cr > 2:
            health_score += 20
        elif cr > 1.5:
            health_score += 10
        elif cr > 1:
            health_score += 0
        else:
            health_score -= 20
    
    scores['financial_health'] = max(0, min(100, health_score))
    
    # 5. Technical/Momentum Score (15% weight)
    tech_score = 50
    weights['technical'] = 15
    
    dist_high = metrics.get('distance_from_52w_high')
    if dist_high is not None:
        if dist_high > -10:  # Within 10% of high
            tech_score += 15
        elif dist_high > -20:
            tech_score += 5
        elif dist_high > -30:
            tech_score -= 5
        else:
            tech_score -= 15
    
    volatility = metrics.get('volatility')
    if volatility is not None:
        if volatility < 20:
            tech_score += 15
        elif volatility < 30:
            tech_score += 5
        elif volatility < 50:
            tech_score -= 5
        else:
            tech_score -= 15
    
    beta = metrics.get('beta')
    if beta is not None:
        if 0.8 <= beta <= 1.2:
            tech_score += 10
        elif 0.5 <= beta <= 1.5:
            tech_score += 5
        else:
            tech_score -= 5
    
    scores['technical'] = max(0, min(100, tech_score))
    
    # Calculate weighted total
    total_score = sum(scores[k] * weights[k] / 100 for k in scores)
    
    # Determine recommendation
    if total_score >= 75:
        recommendation = "STRONG CONSIDER"
    elif total_score >= 60:
        recommendation = "CONSIDER"
    elif total_score >= 45:
        recommendation = "NEUTRAL"
    elif total_score >= 30:
        recommendation = "CAUTION"
    else:
        recommendation = "AVOID"
    
    return {
        'total_score': round(total_score, 1),
        'recommendation': recommendation,
        'component_scores': scores,
        'weights': weights
    }