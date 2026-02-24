import io
from dataclasses import dataclass
from typing import Dict

import pandas as pd
import streamlit as st
import yfinance as yf


DEFAULT_HOLDINGS_CSV = """ticker,shares
AAPL,227917808
AXP,151610700
BAC,517295934
KO,400000000
CVX,130156362
MCO,24669778
OXY,264941431
CB,34249183
KHC,325634818
GOOGL,17846142
"""


@dataclass
class PortfolioResult:
    position_value: pd.Series
    cumulative_dividend: pd.Series
    total_value: pd.Series
    total_return: pd.Series


def parse_holdings(csv_text: str) -> Dict[str, float]:
    frame = pd.read_csv(io.StringIO(csv_text.strip()))
    required_columns = {"ticker", "shares"}
    if not required_columns.issubset(frame.columns):
        raise ValueError("持仓数据必须包含 ticker 和 shares 两列。")

    frame = frame.dropna(subset=["ticker", "shares"])
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["shares"] = pd.to_numeric(frame["shares"], errors="coerce")
    frame = frame.dropna(subset=["shares"])

    if frame.empty:
        raise ValueError("没有可用的持仓数据。")

    return dict(zip(frame["ticker"], frame["shares"]))


def fetch_single_ticker_history(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    history = stock.history(start=start, end=end, auto_adjust=False, actions=True)
    if history.empty:
        raise ValueError(f"{ticker} 没有返回任何价格数据。")

    if "Close" not in history.columns:
        raise ValueError(f"{ticker} 历史数据缺少 Close 列。")

    if "Dividends" not in history.columns:
        history["Dividends"] = 0.0

    cleaned = history[["Close", "Dividends"]].copy()
    cleaned.index = cleaned.index.tz_localize(None)
    return cleaned


def build_portfolio_curve(holdings: Dict[str, float], start: pd.Timestamp, end: pd.Timestamp) -> PortfolioResult:
    price_table = {}
    dividend_table = {}

    for ticker, shares in holdings.items():
        data = fetch_single_ticker_history(ticker, start, end)
        price_table[ticker] = data["Close"] * shares
        dividend_table[ticker] = data["Dividends"] * shares

    position_value = pd.DataFrame(price_table).sort_index().ffill().sum(axis=1)
    daily_dividend = pd.DataFrame(dividend_table).sort_index().fillna(0).sum(axis=1)
    cumulative_dividend = daily_dividend.cumsum()
    total_value = position_value + cumulative_dividend

    base_value = total_value.iloc[0]
    if base_value == 0:
        raise ValueError("组合初始价值为 0，无法计算收益率。")

    total_return = total_value / base_value - 1

    return PortfolioResult(
        position_value=position_value,
        cumulative_dividend=cumulative_dividend,
        total_value=total_value,
        total_return=total_return,
    )


def main() -> None:
    st.set_page_config(page_title="股票组合跟踪", layout="wide")
    st.title("股票组合跟踪（含分红）")
    st.caption("数据源：Yahoo Finance（免费）")

    st.markdown(
        "在下方粘贴持仓 CSV（必须包含 `ticker,shares` 两列），例如附件中的股票组合。"
    )

    with st.sidebar:
        start_date = st.date_input("开始日期", value=pd.Timestamp("2020-01-01"))
        end_date = st.date_input("结束日期", value=pd.Timestamp.today())

    csv_text = st.text_area("持仓 CSV", value=DEFAULT_HOLDINGS_CSV, height=240)

    if st.button("计算组合收益"):
        try:
            holdings = parse_holdings(csv_text)
            result = build_portfolio_curve(holdings, pd.Timestamp(start_date), pd.Timestamp(end_date))
        except Exception as exc:
            st.error(f"计算失败：{exc}")
            return

        col1, col2, col3 = st.columns(3)
        col1.metric("当前组合总价值", f"${result.total_value.iloc[-1]:,.0f}")
        col2.metric("累计分红收入", f"${result.cumulative_dividend.iloc[-1]:,.0f}")
        col3.metric("区间总收益率", f"{result.total_return.iloc[-1] * 100:,.2f}%")

        curve_df = pd.DataFrame(
            {
                "仅持仓市值": result.position_value,
                "累计分红": result.cumulative_dividend,
                "含分红总价值": result.total_value,
                "总收益率": result.total_return,
            }
        )

        st.subheader("组合价值曲线")
        st.line_chart(curve_df[["仅持仓市值", "含分红总价值"]])

        st.subheader("组合总收益率曲线")
        st.line_chart(curve_df[["总收益率"]])

        st.subheader("明细数据")
        st.dataframe(curve_df.tail(20), use_container_width=True)


if __name__ == "__main__":
    main()
