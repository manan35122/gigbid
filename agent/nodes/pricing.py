"""Pricing Strategist: real market statistics (Kaggle history, via MCP) + client budget + Connects check."""
import statistics

from agent.handoffs import PriceQuote
from agent.mcp_client import call
from agent.nodes.common import cfg, step


async def pricing(state):
    j, pol = state["job"], cfg()["policy"]
    bmin, bmax = j["budget"]["min"], j["budget"]["max"]
    prices, errs = [], []
    for skill in j["required_skills"][:2]:
        try:
            rows = await call("pricing", "marketplace", "get_price_history", {"skill": skill, "limit": 200})
            prices += [r["budget"]["max"] for r in rows if r["budget"]["max"] > 0]
        except Exception as e:
            errs.append(f"price history unavailable for {skill}: {e}")
    low = med = high = None
    if len(prices) >= 15:
        low, med, high = statistics.quantiles(prices, n=4)
        bid = min(max(med, bmin), bmax) if bmax > 0 else med
        clamped = bid != med
        basis = (f"market median {med:.0f} (n={len(prices)} real jobs), "
                 f"{'clamped to' if clamped else 'inside'} client budget {bmin:.0f}-{bmax:.0f}")
    else:
        bid, clamped = (bmin + bmax) / 2, True
        basis = f"only {len(prices)} market rows; midpoint of client budget"
    try:
        bal = (await call("pricing", "marketplace", "get_connects_balance", {}))["balance"]
    except Exception as e:
        bal = None
        errs.append(f"connects balance unavailable: {e}")
    cost = j["connects_cost"]
    worth = cost <= pol["max_connects_per_bid"] and (bal is None or bal >= cost)
    q = PriceQuote(bid_amount=max(round(bid), 1), market_low=low, market_high=high, connects_cost=cost,
                   worth_connects=worth, rationale=f"{basis}. Connects cost {cost}, balance {bal}.")
    return {"price_quote": q.model_dump(), "errors": errs,
            **step("pricing", bid=q.bid_amount, clamped_to_budget=clamped, market_n=len(prices))}