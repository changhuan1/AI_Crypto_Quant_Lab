import numpy as np
import pandas as pd


def calculate_metrics(nav: pd.DataFrame, periods_per_year: int = 365) -> dict[str, float]:
    if nav.empty:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }

    returns = nav["nav"].pct_change().dropna()
    total_return = nav["nav"].iloc[-1] / nav["nav"].iloc[0] - 1
    years = max(len(nav) / periods_per_year, 1 / periods_per_year)
    annual_return = (1 + total_return) ** (1 / years) - 1
    annual_volatility = returns.std() * np.sqrt(periods_per_year)
    sharpe = annual_return / annual_volatility if annual_volatility else 0.0
    max_drawdown = (nav["nav"] / nav["nav"].cummax() - 1).min()
    win_rate = (returns > 0).mean() if not returns.empty else 0.0

    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "annual_volatility": float(annual_volatility),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "win_rate": float(win_rate),
    }
