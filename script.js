const coins = [
  { pair: "BTC/USDT", symbol: "BTCUSDT", price: 0, change: 0 },
  { pair: "ETH/USDT", symbol: "ETHUSDT", price: 0, change: 0 },
  { pair: "SOL/USDT", symbol: "SOLUSDT", price: 0, change: 0 },
];

let currentInterval = "15m";
let activeCoin = coins[0];

const selectedToken = document.querySelector(".selected-token");

const ticker = document.querySelector(".market-ticker");

coins.forEach((coin, index) => {
    const card = document.createElement("div");
    card.classList.add("coin-card");
    if (index === 0) card.classList.add("active-coin");
    card.textContent = `${coin.pair} $${coin.price} ${coin.change > 0 ? "+" : ""}${coin.change}%`;
  
    card.addEventListener("click", () => {
        document.querySelectorAll(".coin-card").forEach(c => c.classList.remove("active-coin"));
        card.classList.add("active-coin");
        selectedToken.textContent = card.textContent;
        activeCoin = coins[index];
        resetFutureWhitespace();
        fetchCandles(activeCoin, currentInterval);
    });
  
    ticker.appendChild(card);

    selectedToken.textContent = document.querySelector(".active-coin").textContent;
});

const navOptions = document.querySelectorAll(".nav-option");

navOptions.forEach(card => {
    card.addEventListener("click", () => {

        navOptions.forEach(item => {
            item.classList.remove("active-option");
        });

        card.classList.add("active-option");

    });
});

const timeframes = document.querySelectorAll(".timeframe");

timeframes.forEach(frame => {
    frame.addEventListener("click", () => {

        timeframes.forEach(item => {
            item.classList.remove("active-timeframe");
        });

        frame.classList.add("active-timeframe");
        currentInterval = frame.textContent;
        resetFutureWhitespace();
        fetchCandles(activeCoin, currentInterval);

    });
});

const selectednav = document.querySelector(".selected-nav");

selectednav.textContent = document.querySelector(".active-option").textContent;

navOptions.forEach(item => {
    item.addEventListener("click", () => {

        navOptions.forEach(item => {
            item.classList.remove("active-option");
        });

        item.classList.add("active-option");

        selectednav.textContent = item.textContent;

    });
});

const log = console.log;

const chartProperties = {
    layout: {
        background: { color: '#000000' },
        textColor: '#ffffff',
    },
    grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0)' },
        horzLines: { color: 'rgba(255, 255, 255, 0)' },
    },
    rightPriceScale: {
        visible: true,
        borderVisible: false,
        scaleMargins: {
            top: 0.1,
            bottom: 0.1,
        },
    },
    timeScale: {
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 40,
        barSpacing: 6,
        minBarSpacing: 0.5,
        fixLeftEdge: false,
        fixRightEdge: false,
        lockVisibleTimeRangeOnResize: false,
        borderVisible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
    },
    localization: {
        timeFormatter: (timestamp) => {
            const isIntraday = currentInterval.endsWith('m') || currentInterval.endsWith('h');
            const date = new Date(timestamp * 1000);
            if (isIntraday) {
                return new Intl.DateTimeFormat('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    hour: '2-digit',
                    minute: '2-digit',
                    day: '2-digit',
                    month: 'short',
                }).format(date);
            }
            return new Intl.DateTimeFormat('en-IN', {
                timeZone: 'Asia/Kolkata',
                year: 'numeric',
                month: 'short',
                day: '2-digit',
            }).format(date);
        },
    },
}

const domElement = document.getElementById('tvcharts');
const chart = LightweightCharts.createChart(domElement, {
    ...chartProperties,
    width: domElement.clientWidth,
    height: domElement.clientHeight,
});
const candleSeries = chart.addCandlestickSeries();

const whitespaceSeries = chart.addLineSeries({
    color: 'transparent',
    lineWidth: 0,
    crosshairMarkerVisible: false,
    lastValueVisible: false,
    priceLineVisible: false,
    autoscaleInfoProvider: () => null,
});

let chartWs = null;
let futureAnchorTime = 0;

const resizeChart = () => {
    const width = domElement.clientWidth;
    const height = domElement.clientHeight;
    if (width > 0 && height > 0) {
        chart.resize(width, height);
    }
};

const resizeObserver = new ResizeObserver(resizeChart);
resizeObserver.observe(domElement);
window.addEventListener("resize", resizeChart);

// Returns interval duration in seconds.
function parseIntervalSecs(interval) {
    const n = parseInt(interval);
    if (interval.endsWith('m')) return n * 60;
    if (interval.endsWith('h')) return n * 3600;
    if (interval.endsWith('d')) return n * 86400;
    if (interval.endsWith('w')) return n * 7 * 86400;
    return 60;
}

// Appends `count` more future timestamps starting after futureAnchorTime.
// Uses update() per point so the series only ever grows rightward.
function extendFutureWhitespace(fromTimeSec, interval, count = 100) {
    const step = parseIntervalSecs(interval);
    // If we're resetting (new symbol / timeframe), wipe and restart.
    if (fromTimeSec < futureAnchorTime && fromTimeSec !== 0) {
        whitespaceSeries.setData([]);
        futureAnchorTime = 0;
    }
    const start = Math.max(fromTimeSec, futureAnchorTime);
    for (let i = 1; i <= count; i++) {
        const t = start + step * i;
        whitespaceSeries.update({ time: t });
        futureAnchorTime = t;
    }
}

// Resets whitespace entirely (call when switching symbol or timeframe).
function resetFutureWhitespace() {
    futureAnchorTime = 0;
    whitespaceSeries.setData([]);
}

// Dynamically extend when user scrolls near the right edge.
chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (!range || futureAnchorTime === 0) return;
    const step = parseIntervalSecs(currentInterval);
    const edgeTime = futureAnchorTime;
    // Convert visible right logical index to approximate timestamp.
    // We extend if the visible right is within 30 bars of the whitespace end.
    const totalBars = chart.timeScale().getVisibleRange();
    if (!totalBars) return;
    const rightTimeSec = totalBars.to;
    if (typeof rightTimeSec === 'number' && edgeTime - rightTimeSec < step * 30) {
        extendFutureWhitespace(futureAnchorTime, currentInterval, 100);
    }
});

fetchCandles(activeCoin, currentInterval);

function fetchCandles(coin, interval) {
    fetch(`https://api.binance.com/api/v3/klines?symbol=${coin.symbol}&interval=${interval}&limit=250`)
        .then(res => res.json())
        .then(data => {
            const candles = data.map(c => ({
                time: Math.floor(c[0] / 1000),
                open: +c[1],
                high: +c[2],
                low: +c[3],
                close: +c[4]
            }))
            .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time)
            .sort((a, b) => a.time - b.time);

            candleSeries.setData(candles);

            // Seed future timestamps so the time axis extends past the last candle.
            const lastTime = candles[candles.length - 1].time;
            extendFutureWhitespace(lastTime, interval);

            connectChartWebSocket(coin, interval);
        })
        .catch(err => console.error(err));
}

function connectWebSocket(coin, index) {
    const stream = coin.symbol.toLowerCase() + "@kline_1m";
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${stream}`);

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        const k = msg.k;

        coin.price = parseFloat(k.c).toFixed(2);
        coin.change = parseFloat(((k.c - k.o) / k.o * 100).toFixed(2));

        const card = document.querySelectorAll(".coin-card")[index];
        card.textContent = `${coin.pair} $${coin.price} ${coin.change > 0 ? "+" : ""}${coin.change}%`;

        const activeIndex = [...document.querySelectorAll(".coin-card")].findIndex(c => c.classList.contains("active-coin"));
        if (activeIndex === index) {
            selectedToken.textContent = card.textContent;
        }
    };
}

function connectChartWebSocket(coin, interval) {
    if (chartWs) {
        chartWs.close();
    }

    const stream = coin.symbol.toLowerCase() + `@kline_${interval}`;
    chartWs = new WebSocket(`wss://stream.binance.com:9443/ws/${stream}`);

    chartWs.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        const k = msg.k;

        const candle = {
            time: Math.floor(k.t / 1000),
            open: parseFloat(k.o),
            high: parseFloat(k.h),
            low: parseFloat(k.l),
            close: parseFloat(k.c),
        };

        candleSeries.update(candle);

        // When a candle closes, roll the future window forward by one slot.
        if (k.x) {
            extendFutureWhitespace(candle.time, interval);
        }
    };
}

coins.forEach((coin, index) => connectWebSocket(coin, index));