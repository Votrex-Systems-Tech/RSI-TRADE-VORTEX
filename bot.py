from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Sequence

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from backtester import backtest_many, backtest_strategy
from data_fetcher import fetch_ohlcv, render_equity_chart, render_price_chart
from indicators import rsi
from strategies import STRATEGIES
from yfinance.exceptions import YFRateLimitError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rsi-bot")


DEFAULT_ASSET = "BTC-USD"
DEFAULT_STRATEGY = "rsi"
DEFAULT_INTERVAL = "1d"
DEFAULT_PERIOD = "6mo"
DEFAULT_SCAN_MINUTES = 60


@dataclass
class ChatState:
    asset: str = DEFAULT_ASSET
    watchlist: List[str] = field(default_factory=lambda: [DEFAULT_ASSET])
    strategy: str = DEFAULT_STRATEGY
    interval: str = DEFAULT_INTERVAL
    period: str = DEFAULT_PERIOD
    scan_minutes: int = DEFAULT_SCAN_MINUTES
    watching: bool = False
    last_signatures: Dict[str, str] = field(default_factory=dict)
    history: List[str] = field(default_factory=list)


states: Dict[int, ChatState] = {}


def get_state(chat_id: int) -> ChatState:
    if chat_id not in states:
        states[chat_id] = ChatState()
    return states[chat_id]


def parse_arg(text: str, index: int = 1) -> str | None:
    parts = text.split(maxsplit=index)
    if len(parts) <= index:
        return None
    return parts[index].strip()


def format_watchlist(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "пусто"


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Выбрать актив", callback_data="menu:asset")],
            [InlineKeyboardButton("Выбрать стратегию", callback_data="menu:strategy")],
            [InlineKeyboardButton("Включить отслеживание", callback_data="menu:watch")],
            [InlineKeyboardButton("Отключить отслеживание", callback_data="menu:unwatch")],
            [InlineKeyboardButton("Проверить сигнал", callback_data="menu:scan")],
        ]
    )


def asset_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("BTC-USD", callback_data="asset:BTC-USD"), InlineKeyboardButton("ETH-USD", callback_data="asset:ETH-USD")],
        [InlineKeyboardButton("AAPL", callback_data="asset:AAPL"), InlineKeyboardButton("TSLA", callback_data="asset:TSLA")],
        [InlineKeyboardButton("SPY", callback_data="asset:SPY"), InlineKeyboardButton("NVDA", callback_data="asset:NVDA")],
        [InlineKeyboardButton("Назад", callback_data="menu:start")],
    ]
    return InlineKeyboardMarkup(rows)


def strategy_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("RSI mean reversion", callback_data="strategy:rsi")],
        [InlineKeyboardButton("EMA trend", callback_data="strategy:ema")],
        [InlineKeyboardButton("Breakout", callback_data="strategy:breakout")],
        [InlineKeyboardButton("Назад", callback_data="menu:start")],
    ]
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    await update.message.reply_text(
        f"Готов. Актив: {state.asset}\nСтратегия: {STRATEGIES[state.strategy][0]}\nИнтервал: {state.interval}\nПериод: {state.period}\n\nВыбирай актив и стратегию, затем жми /scan.",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/start - меню\n/asset - выбор актива\n/addasset SYMBOL - добавить актив в watchlist\n/removeasset SYMBOL - удалить актив\n/watchlist - показать список активов\n/strategy - выбор стратегии\n/setperiod 1y - период данных\n/setinterval 1h - таймфрейм\n/setscan 30 - частота проверок в минутах\n/watch - включить автоотслеживание\n/unwatch - выключить автоотслеживание\n/scan - отправить сигнал\n/backtest - тест текущего актива\n/backtestwatchlist - тест watchlist\n/status - текущие настройки\n/signals - история сигналов"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    await update.message.reply_text(
        f"Актив: {state.asset}\nWatchlist: {format_watchlist(state.watchlist)}\nСтратегия: {STRATEGIES[state.strategy][0]}\nИнтервал: {state.interval}\nПериод: {state.period}\nОтслеживание: {'вкл' if state.watching else 'выкл'}\nЧастота: каждые {state.scan_minutes} мин"
    )


async def asset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выбери актив:", reply_markup=asset_menu())


async def strategy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Выбери стратегию:", reply_markup=strategy_menu())


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await perform_scan(update.effective_chat.id, context, update.message.reply_text)


async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    name, strategy_fn = STRATEGIES[state.strategy]
    await update.message.reply_text(f"Запускаю backtest для {state.asset} по стратегии {name}...")
    try:
        snapshot = fetch_ohlcv(state.asset, period=state.period, interval=state.interval)
        result = backtest_strategy(snapshot.data, strategy_fn, name)
        chart = render_equity_chart(result.equity, f"Backtest: {state.asset} / {name}")
        text = (
            f"*Backtest {state.asset}*\n"
            f"Стратегия: {name}\n\n"
            f"Источник: {snapshot.source}\n\n"
            f"{result.summary}"
        )
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=InputFile(chart, filename=f"backtest-{state.asset}.png"),
            caption=text,
            parse_mode="Markdown",
        )
    except YFRateLimitError:
        await update.message.reply_text("Источник данных временно ограничил backtest. Подожди немного и попробуй снова.")
    except Exception as exc:
        log.exception("backtest failed")
        await update.message.reply_text(f"Backtest не удался: {exc}")


async def backtest_watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    name, strategy_fn = STRATEGIES[state.strategy]
    await update.message.reply_text(f"Запускаю backtest watchlist по стратегии {name}...")
    try:
        items = []
        sources = []
        for asset in state.watchlist:
            snapshot = fetch_ohlcv(asset, period=state.period, interval=state.interval)
            items.append((asset, snapshot.data))
            sources.append((asset, snapshot.source))
        batch = backtest_many(items, strategy_fn, name)
        lines = [f"*Watchlist Backtest*\nСтратегия: {name}\n"]
        for (asset, source), result in zip(sources, batch.results, strict=False):
            lines.append(
                f"{asset} [{source}]: trades={result.trades}, win={result.win_rate:.1f}%, net={result.net_return_pct:.2f}%, dd={result.max_drawdown_pct:.2f}%"
            )
        lines.append(f"\nCosts: commission {batch.results[0].commission_pct:.2f}% x2, slippage {batch.results[0].slippage_pct:.2f}%")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        if len(batch.results) == 1:
            chart = render_equity_chart(batch.results[0].equity, f"Backtest: {state.asset} / {name}")
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=InputFile(chart, filename=f"backtest-{state.asset}.png"),
                caption=f"*Backtest {state.asset}*\n{name}\n\n{batch.results[0].summary}",
                parse_mode="Markdown",
            )
    except YFRateLimitError:
        await update.message.reply_text("Источник данных временно ограничил backtest watchlist. Подожди немного и попробуй снова.")
    except Exception as exc:
        log.exception("watchlist backtest failed")
        await update.message.reply_text(f"Backtest watchlist не удался: {exc}")


async def addasset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    asset = parse_arg(update.message.text or "")
    if not asset:
        await update.message.reply_text("Использование: /addasset BTC-USD")
        return
    asset = asset.upper()
    if asset not in state.watchlist:
        state.watchlist.append(asset)
    state.asset = asset
    await update.message.reply_text(f"Добавлен: {asset}\nWatchlist: {format_watchlist(state.watchlist)}")


async def removeasset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    asset = parse_arg(update.message.text or "")
    if not asset:
        await update.message.reply_text("Использование: /removeasset BTC-USD")
        return
    asset = asset.upper()
    state.watchlist = [item for item in state.watchlist if item != asset]
    if not state.watchlist:
        state.watchlist = [DEFAULT_ASSET]
    if state.asset == asset:
        state.asset = state.watchlist[0]
    await update.message.reply_text(f"Удален: {asset}\nWatchlist: {format_watchlist(state.watchlist)}")


async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    await update.message.reply_text(f"Watchlist: {format_watchlist(state.watchlist)}")


async def setperiod_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    value = parse_arg(update.message.text or "")
    if not value:
        await update.message.reply_text("Использование: /setperiod 1y")
        return
    state.period = value
    await update.message.reply_text(f"Период установлен: {state.period}")


async def setinterval_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    value = parse_arg(update.message.text or "")
    if not value:
        await update.message.reply_text("Использование: /setinterval 1h")
        return
    state.interval = value
    await update.message.reply_text(f"Интервал установлен: {state.interval}")


async def setscan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    value = parse_arg(update.message.text or "")
    if not value or not value.isdigit():
        await update.message.reply_text("Использование: /setscan 30")
        return
    state.scan_minutes = max(5, int(value))
    if state.watching:
        schedule_watch_job(context.application, update.effective_chat.id, state.scan_minutes)
    await update.message.reply_text(f"Частота сканов: каждые {state.scan_minutes} мин")


async def watch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    state.watching = True
    schedule_watch_job(context.application, update.effective_chat.id, state.scan_minutes)
    await update.message.reply_text("Отслеживание включено.", reply_markup=main_menu())


async def unwatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    state.watching = False
    remove_watch_job(context.application, update.effective_chat.id)
    await update.message.reply_text("Отслеживание выключено.", reply_markup=main_menu())


async def signals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(update.effective_chat.id)
    if not state.history:
        await update.message.reply_text("История сигналов пока пуста.")
        return
    await update.message.reply_text("Последние сигналы:\n" + "\n".join(state.history[-10:]))


async def perform_scan(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_fn) -> None:
    state = get_state(chat_id)
    name, strategy_fn = STRATEGIES[state.strategy]
    await reply_fn(f"Сканирую {state.asset} по стратегии {name}...")

    try:
        await scan_asset(chat_id, context, state.asset, state, name, strategy_fn)
    except YFRateLimitError:
        await reply_fn("Источник данных временно ограничил запросы. Подожди 2-3 минуты и попробуй снова.")
    except Exception as exc:
        log.exception("scan failed")
        await reply_fn(f"Не удалось получить сигнал: {exc}")


async def scan_asset(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    asset: str,
    state: ChatState,
    strategy_name: str,
    strategy_fn,
) -> None:
    snapshot = fetch_ohlcv(asset, period=state.period, interval=state.interval)
    df = snapshot.data.copy()
    df["RSI"] = rsi(df["Close"])
    result = strategy_fn(df)
    chart = render_price_chart(
        df,
        asset,
        result.chart_title,
        f"{result.action} | {result.summary}\n{result.details}",
    )

    signature = f"{asset}:{state.strategy}:{result.action}:{result.summary}"
    if signature != state.last_signatures.get(asset):
        state.last_signatures[asset] = signature
        state.history.append(signature)

    text = (
        f"*{asset}*\n"
        f"Стратегия: {strategy_name}\n"
        f"Источник: {snapshot.source}\n"
        f"Сигнал: *{result.action}*\n"
        f"Уверенность: *{result.confidence}%*\n\n"
        f"{result.summary}\n\n"
        f"{result.details}"
    )
    if result.entry is not None:
        text += f"\n\nEntry: {result.entry:.2f}"
        if result.stop_loss is not None:
            text += f"\nSL: {result.stop_loss:.2f}"
        if result.take_profit is not None:
            text += f"\nTP: {result.take_profit:.2f}"
    if result.risk_note:
        text += f"\n\nRisk: {result.risk_note}"
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=InputFile(chart, filename=f"{asset}.png"),
        caption=text,
        parse_mode="Markdown",
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    state = get_state(chat_id)
    data = query.data or ""

    if data == "menu:start":
        await query.message.edit_text(
            f"Актив: {state.asset}\nСтратегия: {STRATEGIES[state.strategy][0]}",
            reply_markup=main_menu(),
        )
    elif data == "menu:asset":
        await query.message.edit_text("Выбери актив:", reply_markup=asset_menu())
    elif data == "menu:strategy":
        await query.message.edit_text("Выбери стратегию:", reply_markup=strategy_menu())
    elif data == "menu:scan":
        await perform_scan(chat_id, context, query.message.reply_text)
    elif data == "menu:watch":
        state.watching = True
        schedule_watch_job(context.application, chat_id, state.scan_minutes)
        await query.message.edit_text("Отслеживание включено.", reply_markup=main_menu())
    elif data == "menu:unwatch":
        state.watching = False
        remove_watch_job(context.application, chat_id)
        await query.message.edit_text("Отслеживание выключено.", reply_markup=main_menu())
    elif data.startswith("asset:"):
        state.asset = data.split(":", 1)[1]
        await query.message.edit_text(f"Актив выбран: {state.asset}", reply_markup=main_menu())
    elif data.startswith("strategy:"):
        state.strategy = data.split(":", 1)[1]
        await query.message.edit_text(
            f"Стратегия выбрана: {STRATEGIES[state.strategy][0]}",
            reply_markup=main_menu(),
        )


def build_app() -> Application:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("asset", asset_cmd))
    app.add_handler(CommandHandler("addasset", addasset_cmd))
    app.add_handler(CommandHandler("removeasset", removeasset_cmd))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("strategy", strategy_cmd))
    app.add_handler(CommandHandler("setperiod", setperiod_cmd))
    app.add_handler(CommandHandler("setinterval", setinterval_cmd))
    app.add_handler(CommandHandler("setscan", setscan_cmd))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("backtest", backtest_cmd))
    app.add_handler(CommandHandler("backtestwatchlist", backtest_watchlist_cmd))
    app.add_handler(CommandHandler("watch", watch_cmd))
    app.add_handler(CommandHandler("unwatch", unwatch_cmd))
    app.add_handler(CommandHandler("signals", signals_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    return app


def schedule_watch_job(app: Application, chat_id: int, scan_minutes: int) -> None:
    remove_watch_job(app, chat_id)
    app.job_queue.run_repeating(
        chat_watch_scan,
        interval=timedelta(minutes=scan_minutes),
        first=5,
        name=f"watch:{chat_id}",
        data={"chat_id": chat_id},
    )


def remove_watch_job(app: Application, chat_id: int) -> None:
    for job in app.job_queue.get_jobs_by_name(f"watch:{chat_id}"):
        job.schedule_removal()


async def chat_watch_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    state = get_state(chat_id)
    if not state.watching:
        return
    name, strategy_fn = STRATEGIES[state.strategy]
    for asset in list(state.watchlist):
        await context.bot.send_message(chat_id=chat_id, text=f"Сканирую {asset} по стратегии {name}...")
        try:
            await scan_asset(chat_id, context, asset, state, name, strategy_fn)
        except Exception as exc:
            log.exception("watch scan failed")
            await context.bot.send_message(chat_id=chat_id, text=f"Не удалось получить сигнал по {asset}: {exc}")


if __name__ == "__main__":
    app = build_app()
    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
