# RSI Trading Signals Bot

A polished Telegram bot for market scanning, chart-based signal delivery, and strategy backtesting.

It lets you choose an asset, pick a strategy, monitor a watchlist, and receive clear signal breakdowns with charts directly in Telegram.

## What It Does

- scans selected assets and sends trade ideas
- supports multiple strategies:
  - RSI mean reversion
  - EMA trend following
  - breakout detection
- sends charts with price action and indicators
- keeps a per-chat watchlist
- supports scheduled signal checks
- runs backtests on the current asset or the full watchlist
- shows the data source used for each signal

## Screenshots

Add your own screenshots here after running the bot in Telegram.

## Project Structure

- `bot.py` - Telegram bot entrypoint
- `data_fetcher.py` - market data download, provider routing, and chart rendering
- `strategies.py` - signal strategies and result models
- `indicators.py` - RSI, EMA, ATR utilities
- `backtester.py` - backtest engine and batch backtests
- `requirements.txt` - Python dependencies

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Telegram token

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### 3. Run the bot

```bash
python bot.py
```

## Commands

- `/start` - open the main menu
- `/asset` - choose the current asset
- `/addasset SYMBOL` - add an asset to the watchlist
- `/removeasset SYMBOL` - remove an asset from the watchlist
- `/watchlist` - show all tracked assets
- `/strategy` - choose the active strategy
- `/setperiod 1y` - change the historical data period
- `/setinterval 1h` - change the chart timeframe
- `/setscan 30` - set scheduled scan frequency in minutes
- `/watch` - enable scheduled monitoring
- `/unwatch` - disable scheduled monitoring
- `/scan` - trigger a live scan for the current asset
- `/backtest` - run a backtest for the current asset
- `/backtestwatchlist` - run backtests for all watched assets
- `/status` - show current settings
- `/signals` - show recent signal history
- `/help` - show command help

## Data Sources

The bot uses a provider router with automatic fallback:

- `yfinance` for the primary market data source
- `stooq` as a fallback for daily equity data

You can control the provider with:

```bash
MARKET_DATA_PROVIDER=auto
```

Other supported values:

- `yfinance`
- `stooq`

## Signal Logic

Each signal includes:

- direction: `BUY`, `SELL`, or `WAIT`
- confidence score
- short explanation
- entry, stop loss, and take profit estimates when available
- chart caption with the key context

Backtests also include:

- number of trades
- win rate
- average trade return
- net return
- max drawdown

## Strategy Notes

This bot is designed for analysis and alerting, not direct auto-execution.

The current strategies are intentionally simple and transparent:

- RSI mean reversion looks for reversals from oversold and overbought zones
- EMA trend follows moving-average alignment
- breakout watches for local range expansion

## Example Assets

- `BTC-USD`
- `ETH-USD`
- `AAPL`
- `TSLA`
- `SPY`
- `NVDA`

## Environment Variables

- `TELEGRAM_BOT_TOKEN` - required Telegram bot token
- `MARKET_DATA_PROVIDER` - optional provider mode: `auto`, `yfinance`, or `stooq`

## Important

This project is for educational and analytical use only.

It is not financial advice and does not guarantee profitability. Always test strategies on historical data and in a demo environment before using real capital.

## Roadmap

- richer strategy presets
- per-asset strategy configuration
- configurable risk management
- notifications for multiple users and channels
- more stable data providers for intraday feeds

## License

Add a license file before publishing publicly.
