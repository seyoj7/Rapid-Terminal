// ─── Support & Resistance Indicator ────────────────────────────────────────
// Ported from LuxAlgo "Support and Resistance Levels with Breaks" (Pine v4)
// CC BY-NC-SA 4.0  https://creativecommons.org/licenses/by-nc-sa/4.0/

const SR_LEFT_BARS  = 15;
const SR_RIGHT_BARS = 15;
const SR_VOL_THRESH = 20;   // volume oscillator %
let   srEnabled     = true; // toggled by Zones button

// All LineSeries drawn for S/R levels – cleared and redrawn each update
let srLineSeries = [];

/** Compute EMA over an array of values */
function calcEMA(values, period) {
    const k   = 2 / (period + 1);
    const ema = new Array(values.length).fill(null);
    let   sum = 0, count = 0;
    for (let i = 0; i < values.length; i++) {
        if (values[i] === null || values[i] === undefined) { ema[i] = null; continue; }
        sum += values[i];
        count++;
        if (count < period) { ema[i] = null; continue; }
        if (count === period) { ema[i] = sum / period; continue; }
        ema[i] = values[i] * k + ema[i - 1] * (1 - k);
    }
    return ema;
}

/** Detect pivot highs. Returns array of {index, price} */
function getPivotHighs(candles, left, right) {
    const pivots = [];
    for (let i = left; i < candles.length - right; i++) {
        const mid = candles[i].high;
        let   isPivot = true;
        for (let j = i - left; j <= i + right; j++) {
            if (j === i) continue;
            if (candles[j].high >= mid) { isPivot = false; break; }
        }
        if (isPivot) pivots.push({ index: i, price: mid });
    }
    return pivots;
}

/** Detect pivot lows. Returns array of {index, price} */
function getPivotLows(candles, left, right) {
    const pivots = [];
    for (let i = left; i < candles.length - right; i++) {
        const mid = candles[i].low;
        let   isPivot = true;
        for (let j = i - left; j <= i + right; j++) {
            if (j === i) continue;
            if (candles[j].low <= mid) { isPivot = false; break; }
        }
        if (isPivot) pivots.push({ index: i, price: mid });
    }
    return pivots;
}

/**
 * Build a "stepped" price array the same way Pine's fixnan() + plot offset works:
 * Line starts at the pivot bar itself (Pine's offset=-(rightBars+1) draws back to pivot).
 * Returns array of length candles.length where each entry is the active price or null.
 */
function buildLevelArray(candles, pivots) {
    const levels = new Array(candles.length).fill(null);
    for (let p = 0; p < pivots.length; p++) {
        const startIdx = pivots[p].index;
        const endIdx   = p + 1 < pivots.length
            ? pivots[p + 1].index
            : candles.length;
        for (let i = startIdx; i < endIdx && i < candles.length; i++) {
            levels[i] = pivots[p].price;
        }
    }
    return levels;
}

/** Remove all existing S/R line series from the chart */
function clearSRLines() {
    for (const s of srLineSeries) {
        try { chart.removeSeries(s); } catch (_) {}
    }
    srLineSeries = [];
}

/**
 * Draw a series of horizontal segments for one level array.
 * A new LineSeries is created every time the level value changes (matching
 * Pine's `change(highUsePivot) ? na : color` colouring logic).
 */
function drawLevelSegments(candles, levels, color) {
    let segPrice = null;
    let segData  = [];

    function flushSeg() {
        if (segData.length < 2) { segData = []; return; }
        const series = chart.addLineSeries({
            color,
            lineWidth             : 2,
            lastValueVisible      : false,
            priceLineVisible      : false,
            crosshairMarkerVisible: false,
        });
        series.setData(segData);
        srLineSeries.push(series);
        segData = [];
    }

    for (let i = 0; i < candles.length; i++) {
        const price = levels[i];
        if (price === null) {
            flushSeg();
            segPrice = null;
            continue;
        }
        if (price !== segPrice) {
            flushSeg();
            segPrice = price;
        }
        segData.push({ time: candles[i].time, value: price });
    }
    flushSeg();
}

/** Main function: compute and render the full S/R indicator */
function updateSRIndicator(candles) {
    clearSRLines();
    candleSeries.setMarkers([]);
    if (!srEnabled || candles.length < SR_LEFT_BARS + SR_RIGHT_BARS + 2) return;

    // ── Pivot detection ──────────────────────────────────────────────────────
    const pivHigh = getPivotHighs(candles, SR_LEFT_BARS, SR_RIGHT_BARS);
    const pivLow  = getPivotLows (candles, SR_LEFT_BARS, SR_RIGHT_BARS);

    const highLevels = buildLevelArray(candles, pivHigh);
    const lowLevels  = buildLevelArray(candles, pivLow);

    // ── Draw S/R lines ───────────────────────────────────────────────────────
    drawLevelSegments(candles, highLevels, '#FF0000');
    drawLevelSegments(candles, lowLevels,  '#233dee');

    // ── Volume oscillator  osc = 100 * (EMA5 - EMA10) / EMA10 ───────────────
    const vols  = candles.map(c => c.volume ?? 0);
    const ema5  = calcEMA(vols, 5);
    const ema10 = calcEMA(vols, 10);
    const osc   = ema5.map((e5, i) =>
        e5 !== null && ema10[i] !== null && ema10[i] !== 0
            ? 100 * (e5 - ema10[i]) / ema10[i]
            : null
    );

    // ── Break / Wick markers ─────────────────────────────────────────────────
    const markers = [];

    for (let i = 1; i < candles.length; i++) {
        const c    = candles[i];
        const prev = candles[i - 1];
        const res  = highLevels[i];
        const sup  = lowLevels[i];
        const vol  = osc[i];
        const volOk = vol !== null && vol > SR_VOL_THRESH;

        // crossover(close, highUsePivot)
        const crossoverRes  = res !== null && prev.close <= (highLevels[i - 1] ?? res) && c.close > res;
        // crossunder(close, lowUsePivot)
        const crossunderSup = sup !== null && prev.close >= (lowLevels[i - 1]  ?? sup) && c.close < sup;

        // Pine: not(open - low > close - open)  → body up is NOT a wick-driven move
        const isWickBull = res !== null && (c.open - c.low   > c.close - c.open);
        const isWickBear = sup !== null && (c.open - c.close < c.high  - c.open);

        if (crossoverRes && volOk && !isWickBull) {
            markers.push({ time: c.time, position: 'belowBar', color: '#26a69a', shape: 'arrowUp',   text: 'B'         });
        } else if (crossoverRes && isWickBull) {
            markers.push({ time: c.time, position: 'belowBar', color: '#26a69a', shape: 'arrowUp',   text: 'Bull Wick' });
        }

        if (crossunderSup && volOk && !isWickBear) {
            markers.push({ time: c.time, position: 'aboveBar', color: '#ef5350', shape: 'arrowDown', text: 'B'         });
        } else if (crossunderSup && isWickBear) {
            markers.push({ time: c.time, position: 'aboveBar', color: '#ef5350', shape: 'arrowDown', text: 'Bear Wick' });
        }
    }

    // Markers must be sorted by time
    markers.sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(markers);
}

// ── Zones button toggle ──────────────────────────────────────────────────────
const zonesBtn = document.querySelector('.zones-btn');
if (zonesBtn) {
    zonesBtn.style.background = 'rgba(0,162,255,0.18)';
    zonesBtn.addEventListener('click', () => {
        srEnabled = !srEnabled;
        zonesBtn.style.background = srEnabled ? 'rgba(0,162,255,0.18)' : 'transparent';
        updateSRIndicator(candleData);
    });
}
