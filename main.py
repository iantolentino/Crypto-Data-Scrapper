#!/usr/bin/env python3
"""
Crypto Tracker with Modern UI (fixed)
- Non-blocking data fetch using QThread (no UI freeze)
- Candlestick chart (mplfinance) with theme-aware background/text
- Chart data cached per coin/day to avoid re-fetching
- Table and Card views; table click correctly maps to coin id even after sorting
- Icon fetching for cards done in background to avoid blocking refresh
- Custom auto-refresh interval dropdown
"""

import sys
import requests
import pandas as pd
import mplfinance as mpf
from datetime import datetime, timezone

from functools import partial
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QLineEdit, QComboBox, QHBoxLayout, QScrollArea, QGridLayout,
    QFrame, QStackedWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import qt_material

# ---------- Config ----------
COINS = [
    "bitcoin", "ethereum", "solana", "dogecoin", "cardano", "ripple",
    "polkadot", "litecoin", "tron", "polygon", "avalanche-2", "chainlink",
    "uniswap", "stellar", "internet-computer", "vechain", "cosmos",
    "filecoin", "aptos", "arbitrum"
]

API_URL = "https://api.coingecko.com/api/v3/coins/markets"
MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{id}/ohlc"
REFRESH_OPTIONS = {"30s": 30_000, "1m": 60_000, "5m": 300_000, "10m": 600_000}
DEFAULT_REFRESH_LABEL = "1m"
# ----------------------------


class FetchThread(QThread):
    """Generic QThread for fetching JSON from a URL (requests)."""
    finished = Signal(object, str)  # (data, tag)
    error = Signal(str)

    def __init__(self, url: str, params: dict, tag: str):
        super().__init__()
        self.url = url
        self.params = params
        self.tag = tag

    def run(self):
        try:
            r = requests.get(self.url, params=self.params, timeout=20)
            r.raise_for_status()
            data = r.json()
            self.finished.emit(data, self.tag)
        except Exception as e:
            self.error.emit(str(e))


class IconFetcher(QThread):
    """Fetch coin icons in background to avoid blocking the UI."""
    icon_loaded = Signal(str, object)  # coin_id, QPixmap

    def __init__(self, coins):
        super().__init__()
        self.coins = coins  # list of coin dicts

    def run(self):
        for coin in self.coins:
            cid = coin.get("id")
            url = coin.get("image")
            if not cid or not url:
                continue
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                pix = QPixmap()
                pix.loadFromData(r.content)
                self.icon_loaded.emit(cid, pix)
            except Exception:
                # ignore icon failures
                continue


class MplCanvas(FigureCanvas):
    """Matplotlib Canvas wrapper."""
    def __init__(self, parent=None, width=8, height=4, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.figure)


class CryptoTracker(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚀 Crypto Tracker")
        self.resize(1300, 800)
        # Center the window on screen
        frameGm = self.frameGeometry()
        screen = QApplication.primaryScreen().availableGeometry().center()
        frameGm.moveCenter(screen)
        self.move(frameGm.topLeft())

        self.theme = "dark"
        self.chart_cache = {}           # key: (coin_id, days, date) -> DataFrame
        self.icon_cache = {}            # coin_id -> QPixmap
        self.card_icon_labels = {}      # coin_id -> QLabel (to update icons)
        self.threads = []               # keep references to threads

        # UI layout
        main_layout = QVBoxLayout()

        title = QLabel("📊 Live Crypto Prices + Trends")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; margin: 10px;")
        main_layout.addWidget(title)

        # Top controls
        top_bar = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search coin...")
        self.search_bar.textChanged.connect(self.filter_table)
        top_bar.addWidget(self.search_bar)

        self.range_dropdown = QComboBox()
        self.range_dropdown.addItems(["7", "30", "90", "365"])
        top_bar.addWidget(QLabel("Chart Range (days):"))
        top_bar.addWidget(self.range_dropdown)

        self.refresh_interval_dropdown = QComboBox()
        self.refresh_interval_dropdown.addItems(list(REFRESH_OPTIONS.keys()))
        self.refresh_interval_dropdown.setCurrentText(DEFAULT_REFRESH_LABEL)
        self.refresh_interval_dropdown.currentTextChanged.connect(self.change_refresh_interval)
        top_bar.addWidget(QLabel("Auto-refresh:"))
        top_bar.addWidget(self.refresh_interval_dropdown)

        self.toggle_view_btn = QPushButton("📑 Toggle Card/Table")
        self.toggle_view_btn.clicked.connect(self.toggle_view)
        top_bar.addWidget(self.toggle_view_btn)

        self.theme_btn = QPushButton("🌙 Toggle Theme")
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_bar.addWidget(self.theme_btn)

        self.refresh_btn = QPushButton("🔄 Refresh Now")
        self.refresh_btn.clicked.connect(self.load_data)
        top_bar.addWidget(self.refresh_btn)

        main_layout.addLayout(top_bar)

        # Stacked widget for table / cards
        self.stacked = QStackedWidget()
        main_layout.addWidget(self.stacked)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Coin", "Price (USD)", "Market Cap", "24h Change (%)",
            "7d Change (%)", "24h Volume", "Circulating Supply", "Total Supply"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
        self.stacked.addWidget(self.table)

        # Cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.card_container = QWidget()
        self.card_layout = QGridLayout(self.card_container)
        scroll.setWidget(self.card_container)
        self.stacked.addWidget(scroll)

        # Chart canvas
        self.canvas = MplCanvas(self, width=9, height=5, dpi=100)
        main_layout.addWidget(self.canvas)

        # Status label
        self.status_label = QLabel("")
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

        # Auto-refresh timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_data)
        self.change_refresh_interval(self.refresh_interval_dropdown.currentText())
        self.timer.start()

        # initial load
        self.load_data()

    # -------------------
    # Refresh interval
    # -------------------
    def change_refresh_interval(self, label):
        interval = REFRESH_OPTIONS.get(label, 60_000)
        self.timer.setInterval(interval)

    # -------------------
    # Theme
    # -------------------
    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        qt_material.apply_stylesheet(self.app(), theme="dark_teal.xml" if self.theme == "dark" else "light_blue.xml")
        # update chart background immediately
        self.canvas.figure.patch.set_facecolor("#121212" if self.theme == "dark" else "white")
        self.canvas.draw()

    def app(self):
        return QApplication.instance()

    # -------------------
    # Non-blocking data fetching (markets)
    # -------------------
    def load_data(self):
        """Start a background thread to fetch market data."""
        self.status_label.setText("Fetching market data...")
        params = {"vs_currency": "usd", "ids": ",".join(COINS), "price_change_percentage": "24h,7d"}
        th = FetchThread(API_URL, params, tag="markets")
        th.finished.connect(self.on_fetch_finished)
        th.error.connect(self.on_fetch_error)
        th.start()
        self.threads.append(th)

    def on_fetch_finished(self, data, tag):
        if tag == "markets":
            # update UI
            self.populate_table(data)
            self.populate_cards(data)
            # start icon fetcher in background (so populating cards didn't block)
            icon_th = IconFetcher(data)
            icon_th.icon_loaded.connect(self.on_icon_loaded)
            icon_th.start()
            self.threads.append(icon_th)
            self.status_label.setText(f"Market data updated ({len(data)} coins)")
        else:
            # handle chart results in separate handler (we tag chart requests as chart:coin:days)
            if tag.startswith("chart:"):
                # tag format chart:coin_id:days
                try:
                    _, cid, days_s = tag.split(":", 2)
                    days = int(days_s)
                except Exception:
                    cid = None
                    days = None
                self.on_chart_fetched(data, cid, days)

    def on_fetch_error(self, msg):
        QMessageBox.critical(self, "Fetch error", msg)
        self.status_label.setText("Fetch error")

    # -------------------
    # Populate UI (table/cards)
    # -------------------
    def populate_table(self, data):
        """Populate table. Store coin id in Qt.UserRole for robust mapping."""
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(data))
        for r, coin in enumerate(data):
            # Coin name with stored coin id
            name_item = QTableWidgetItem(coin["name"])
            name_item.setData(Qt.UserRole, coin["id"])
            name_item.setData(Qt.UserRole + 1, coin.get("symbol", "").lower())
            self.table.setItem(r, 0, name_item)

            # Price (numeric value in EditRole for correct sorting)
            price_val = float(coin.get("current_price") or 0.0)
            price_item = QTableWidgetItem(f"${price_val:,.2f}")
            price_item.setData(Qt.EditRole, price_val)
            self.table.setItem(r, 1, price_item)

            # Market cap
            mcap = float(coin.get("market_cap") or 0)
            mcap_item = QTableWidgetItem(f"${mcap:,.0f}")
            mcap_item.setData(Qt.EditRole, mcap)
            self.table.setItem(r, 2, mcap_item)

            # 24h change (color-coded)
            pct24 = coin.get("price_change_percentage_24h") or 0.0
            pct24_item = QTableWidgetItem(f"{pct24:+.2f}%")
            pct24_item.setData(Qt.EditRole, float(pct24))
            pct24_item.setForeground(Qt.green if pct24 >= 0 else Qt.red)
            self.table.setItem(r, 3, pct24_item)

            # 7d change
            pct7 = coin.get("price_change_percentage_7d_in_currency") or 0.0
            pct7_item = QTableWidgetItem(f"{pct7:+.2f}%")
            pct7_item.setData(Qt.EditRole, float(pct7))
            pct7_item.setForeground(Qt.green if pct7 >= 0 else Qt.red)
            self.table.setItem(r, 4, pct7_item)

            # 24h volume
            vol = float(coin.get("total_volume") or 0)
            vol_item = QTableWidgetItem(f"${vol:,.0f}")
            vol_item.setData(Qt.EditRole, vol)
            self.table.setItem(r, 5, vol_item)

            # circulating supply
            circ = coin.get("circulating_supply") or 0
            circ_item = QTableWidgetItem(f"{circ:,.0f}")
            circ_item.setData(Qt.EditRole, float(circ))
            self.table.setItem(r, 6, circ_item)

            # total supply
            ts = coin.get("total_supply")
            ts_text = f"{ts:,.0f}" if ts else "∞"
            ts_item = QTableWidgetItem(ts_text)
            ts_item.setData(Qt.EditRole, float(ts or 0))
            self.table.setItem(r, 7, ts_item)

        self.table.setSortingEnabled(True)

    def populate_cards(self, data):
        """Create card widgets quickly (no blocking icon fetch). Icons filled later by IconFetcher."""
        # clear existing cards
        for i in reversed(range(self.card_layout.count())):
            widget = self.card_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
        self.card_icon_labels.clear()

        cols = 4
        row = col = 0
        for coin in data:
            cid = coin.get("id")
            card = QFrame()
            card.setFrameShape(QFrame.Box)
            bg = "#222" if self.theme == "dark" else "#eee"
            fg = "white" if self.theme == "dark" else "black"
            card.setStyleSheet(f"padding:10px; border-radius:10px; background:{bg}; color:{fg};")
            vbox = QVBoxLayout(card)

            # placeholder icon label; will be updated by icon thread if available
            icon_label = QLabel()
            icon_label.setFixedSize(48, 48)
            vbox.addWidget(icon_label, alignment=Qt.AlignCenter)
            self.card_icon_labels[cid] = icon_label

            name_label = QLabel(f"{coin['name']} ({coin.get('symbol','').upper()})")
            name_label.setAlignment(Qt.AlignCenter)
            vbox.addWidget(name_label)

            price_label = QLabel(f"${coin.get('current_price',0):,.2f}")
            price_label.setAlignment(Qt.AlignCenter)
            vbox.addWidget(price_label)

            pct24 = coin.get("price_change_percentage_24h") or 0.0
            change_label = QLabel(f"{pct24:+.2f}% 24h")
            change_label.setAlignment(Qt.AlignCenter)
            change_label.setStyleSheet("color: lime;" if pct24 >= 0 else "color: red;")
            vbox.addWidget(change_label)

            # make the whole card clickable and pass coin id/name
            def make_click_handler(cid_local, cname_local):
                def handler(event):
                    # find the row in table for this coin (by matching stored UserRole)
                    for r in range(self.table.rowCount()):
                        item = self.table.item(r, 0)
                        if item and item.data(Qt.UserRole) == cid_local:
                            self.start_chart_fetch(cid_local, cname_local, int(self.range_dropdown.currentText()))
                            # select row visually
                            self.table.selectRow(r)
                            break
                return handler

            card.mousePressEvent = make_click_handler(cid, coin.get("name"))
            self.card_layout.addWidget(card, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def on_icon_loaded(self, coin_id, pixmap):
        """Slot: called when IconFetcher emits a loaded icon."""
        if not pixmap:
            return
        self.icon_cache[coin_id] = pixmap
        lbl = self.card_icon_labels.get(coin_id)
        if lbl:
            lbl.setPixmap(pixmap.scaled(lbl.width(), lbl.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # -------------------
    # Chart handling (non-blocking)
    # -------------------
    def on_table_cell_clicked(self, row, col):
        """Wrapper for table cell clicks - safe mapping to coin id."""
        item = self.table.item(row, 0)
        if not item:
            return
        coin_id = item.data(Qt.UserRole)
        coin_name = item.text()
        days = int(self.range_dropdown.currentText())
        self.start_chart_fetch(coin_id, coin_name, days)

    def start_chart_fetch(self, coin_id, coin_name, days):
        """Start background fetch for OHLC data (non-blocking)."""
        # check cache first (per day)
        date_tag = datetime.now(timezone.utc).date()
        key = (coin_id, days, date_tag)
        if key in self.chart_cache:
            df = self.chart_cache[key]
            self.draw_candlestick(df, coin_name, days)
            return

        # start fetch thread
        url = MARKET_CHART_URL.format(id=coin_id)
        params = {"vs_currency": "usd", "days": days}
        tag = f"chart:{coin_id}:{days}"
        th = FetchThread(url, params, tag)
        th.finished.connect(self.on_fetch_finished)
        th.error.connect(self.on_fetch_error)
        th.start()
        self.threads.append(th)
        self.status_label.setText(f"Fetching {coin_name} {days}d chart...")

    def on_chart_fetched(self, raw, coin_id, days):
        """Process raw OHLC data returned from CoinGecko for a coin."""
        try:
            if not raw:
                raise ValueError("No OHLC data returned")
            # raw is list of [timestamp, open, high, low, close]
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            key = (coin_id, days, datetime.now(timezone.utc).date())
            self.chart_cache[key] = df
            # draw chart
            # get coin name from table (match by coin_id)
            coin_name = coin_id
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 0)
                if it and it.data(Qt.UserRole) == coin_id:
                    coin_name = it.text()
                    break
            self.draw_candlestick(df, coin_name, days)
            self.status_label.setText(f"Showing chart for {coin_name}")
        except Exception as e:
            QMessageBox.critical(self, "Chart error", str(e))

    def draw_candlestick(self, df, coin_name, days):
        """Draw candlestick with mplfinance on the canvas, respecting theme."""
        # clear and add subplot
        self.canvas.figure.clear()
        ax = self.canvas.figure.add_subplot(111)

        # theme aware background and text colors
        if self.theme == "dark":
            self.canvas.figure.patch.set_facecolor("#121212")
            ax.set_facecolor("#121212")
            tick_color = "white"
            title_color = "white"
            base_style = "nightclouds"
        else:
            self.canvas.figure.patch.set_facecolor("white")
            ax.set_facecolor("white")
            tick_color = "black"
            title_color = "black"
            base_style = "classic"
            ax.grid(color="lightgray")



        ax.tick_params(colors=tick_color)
        ax.title.set_color(title_color)

        mc = mpf.make_marketcolors(up="lime", down="red", inherit=True)
        style = mpf.make_mpf_style(base_mpf_style=base_style, marketcolors=mc)

        # Use mplfinance to plot on existing axes
        mpf.plot(df, type="candle", ax=ax, style=style, datetime_format="%m-%d", show_nontrading=True)
        ax.set_title(f"{coin_name} — {days} days Candlestick")

        self.canvas.draw()

    # -------------------
    # Helpers
    # -------------------
    def filter_table(self, text):
        txt = self.search_bar.text().lower()
        # simple filter by coin name or symbol (stored at UserRole+1)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if not it:
                self.table.setRowHidden(r, True)
                continue
            name = it.text().lower()
            symbol = it.data(Qt.UserRole + 1) or ""
            visible = (txt in name) or (txt in symbol)
            self.table.setRowHidden(r, not visible)

    def toggle_view(self):
        idx = self.stacked.currentIndex()
        self.stacked.setCurrentIndex(1 if idx == 0 else 0)


def main():
    app = QApplication(sys.argv)
    qt_material.apply_stylesheet(app, theme="dark_teal.xml")
    w = CryptoTracker()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()