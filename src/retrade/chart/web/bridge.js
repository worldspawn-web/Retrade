/* Retrade chart bridge: Lightweight Charts + QWebChannel hooks. */
(function () {
  "use strict";

  const container = document.getElementById("chart");
  const hud = document.getElementById("hud");
  const HIT_PX = 12;

  const chart = LightweightCharts.createChart(container, {
    layout: {
      background: { type: "solid", color: "#131722" },
      textColor: "#d1d4dc",
      fontSize: 12,
    },
    grid: {
      vertLines: { color: "#1f2330" },
      horzLines: { color: "#1f2330" },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "#758696", labelBackgroundColor: "#2a2e39" },
      horzLine: { color: "#758696", labelBackgroundColor: "#2a2e39" },
    },
    rightPriceScale: {
      borderColor: "#2a2e39",
      scaleMargins: { top: 0.08, bottom: 0.12 },
      autoScale: true,
    },
    timeScale: {
      borderColor: "#2a2e39",
      timeVisible: true,
      secondsVisible: false,
    },
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: false,
    },
    handleScale: {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true,
    },
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350",
    priceFormat: {
      type: "price",
      precision: 2,
      minMove: 0.01,
    },
  });

  let entryLine = null;
  let tpLine = null;
  let slLine = null;
  let dragTarget = null; // "tp" | "sl" | null
  let levelsEditable = false;
  let currentLevels = { entry: null, tp: null, sl: null };
  let overlayPriceLines = [];
  let overlayZoneSeries = [];
  let lastCandles = [];
  let pricePrecision = 2;

  function defaultScrollOptions() {
    return {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: false,
    };
  }

  function defaultScaleOptions() {
    return {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true,
    };
  }

  function setInteractionEnabled(enabled) {
    chart.applyOptions({
      handleScroll: enabled ? defaultScrollOptions() : false,
      handleScale: enabled ? defaultScaleOptions() : false,
    });
  }

  function resize() {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  }
  window.addEventListener("resize", resize);
  resize();

  function postToQt(payload) {
    if (window.qtBridge && typeof window.qtBridge.onChartEvent === "function") {
      window.qtBridge.onChartEvent(JSON.stringify(payload));
    }
  }

  function formatPrice(value) {
    if (value == null || typeof value !== "number") {
      return "";
    }
    return value.toFixed(pricePrecision);
  }

  function applyPriceFormat(precision) {
    pricePrecision = Math.max(0, Math.min(10, precision | 0));
    const minMove = Math.pow(10, -pricePrecision);
    candleSeries.applyOptions({
      priceFormat: {
        type: "price",
        precision: pricePrecision,
        minMove: minMove,
      },
    });
  }

  function computePriceRange(data) {
    let lo = data[0].low;
    let hi = data[0].high;
    for (let i = 1; i < data.length; i++) {
      if (data[i].low < lo) {
        lo = data[i].low;
      }
      if (data[i].high > hi) {
        hi = data[i].high;
      }
    }
    const span = hi - lo;
    const pad =
      span > 0
        ? span * 0.1
        : Math.max(Math.abs(lo) * 0.02, Math.pow(10, -pricePrecision));
    return {
      minValue: lo - pad,
      maxValue: hi + pad,
    };
  }

  function resetView(candles) {
    if (candles && candles.length) {
      lastCandles = candles;
    }
    chart.timeScale().fitContent();
    candleSeries.applyOptions({
      autoscaleInfoProvider: function () {
        if (!lastCandles.length) {
          return null;
        }
        return { priceRange: computePriceRange(lastCandles) };
      },
    });
    // Re-fit so the provider is applied to the current viewport.
    chart.timeScale().fitContent();
  }

  function clearTradeLines() {
    if (entryLine) {
      candleSeries.removePriceLine(entryLine);
      entryLine = null;
    }
    if (tpLine) {
      candleSeries.removePriceLine(tpLine);
      tpLine = null;
    }
    if (slLine) {
      candleSeries.removePriceLine(slLine);
      slLine = null;
    }
    currentLevels = { entry: null, tp: null, sl: null };
  }

  function clearOverlays() {
    overlayPriceLines.forEach(function (line) {
      candleSeries.removePriceLine(line);
    });
    overlayPriceLines = [];
    overlayZoneSeries.forEach(function (series) {
      chart.removeSeries(series);
    });
    overlayZoneSeries = [];
    candleSeries.setMarkers([]);
  }

  function setOverlays(payload) {
    clearOverlays();
    if (!payload) {
      return;
    }
    const markers = payload.markers || [];
    candleSeries.setMarkers(markers);

    (payload.levels || []).forEach(function (lv) {
      const line = candleSeries.createPriceLine({
        price: lv.price,
        color: lv.color || "#787b86",
        lineWidth: lv.lineWidth || 1,
        lineStyle: lv.lineStyle == null ? 2 : lv.lineStyle,
        axisLabelVisible: true,
        title: lv.title || "",
      });
      overlayPriceLines.push(line);
    });

    (payload.zones || []).forEach(function (zone) {
      const top = chart.addLineSeries({
        color: zone.borderColor || "#26a69a",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.SparseDotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: {
          type: "price",
          precision: pricePrecision,
          minMove: Math.pow(10, -pricePrecision),
        },
      });
      const bottom = chart.addLineSeries({
        color: zone.borderColor || "#26a69a",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.SparseDotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: {
          type: "price",
          precision: pricePrecision,
          minMove: Math.pow(10, -pricePrecision),
        },
      });
      const t1 = zone.timeFrom;
      const t2 = zone.timeTo;
      const t3 = t2 + Math.max(1, Math.floor((t2 - t1) * 3));
      top.setData([
        { time: t1, value: zone.priceTop },
        { time: t3, value: zone.priceTop },
      ]);
      bottom.setData([
        { time: t1, value: zone.priceBottom },
        { time: t3, value: zone.priceBottom },
      ]);
      overlayZoneSeries.push(top, bottom);
    });
  }

  function makeLine(price, color, title) {
    return candleSeries.createPriceLine({
      price: price,
      color: color,
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true,
      title: title,
    });
  }

  function setTradeLevels(levels, editable) {
    clearTradeLines();
    levelsEditable = !!editable;
    if (!levels) {
      return;
    }
    currentLevels = {
      entry: levels.entry,
      tp: levels.tp,
      sl: levels.sl,
    };
    if (levels.entry != null) {
      entryLine = makeLine(levels.entry, "#2962ff", "Entry");
    }
    if (levels.tp != null) {
      tpLine = makeLine(levels.tp, "#26a69a", "TP");
    }
    if (levels.sl != null) {
      slLine = makeLine(levels.sl, "#ef5350", "SL");
    }
  }

  function hitPriceLine(y, price) {
    if (price == null) {
      return false;
    }
    const lineY = candleSeries.priceToCoordinate(price);
    if (lineY == null) {
      return false;
    }
    return Math.abs(lineY - y) <= HIT_PX;
  }

  chart.subscribeCrosshairMove(function (param) {
    if (!param || param.point === undefined || !param.time) {
      return;
    }
    const data = param.seriesData.get(candleSeries);
    if (!data) {
      return;
    }
    hud.textContent =
      "O " +
      formatPrice(data.open) +
      "  H " +
      formatPrice(data.high) +
      "  L " +
      formatPrice(data.low) +
      "  C " +
      formatPrice(data.close);
  });

  container.addEventListener(
    "mousedown",
    function (ev) {
      if (!levelsEditable || currentLevels.tp == null || currentLevels.sl == null) {
        return;
      }
      const rect = container.getBoundingClientRect();
      const y = ev.clientY - rect.top;
      if (hitPriceLine(y, currentLevels.tp)) {
        dragTarget = "tp";
      } else if (hitPriceLine(y, currentLevels.sl)) {
        dragTarget = "sl";
      } else {
        return;
      }
      setInteractionEnabled(false);
      ev.preventDefault();
      ev.stopPropagation();
    },
    true
  );

  container.addEventListener(
    "mousemove",
    function (ev) {
      if (!dragTarget) {
        return;
      }
      const rect = container.getBoundingClientRect();
      const y = ev.clientY - rect.top;
      const price = candleSeries.coordinateToPrice(y);
      if (price == null) {
        return;
      }
      ev.preventDefault();
      ev.stopPropagation();
      if (dragTarget === "tp") {
        currentLevels.tp = price;
        if (tpLine) {
          candleSeries.removePriceLine(tpLine);
        }
        tpLine = makeLine(price, "#26a69a", "TP");
      } else if (dragTarget === "sl") {
        currentLevels.sl = price;
        if (slLine) {
          candleSeries.removePriceLine(slLine);
        }
        slLine = makeLine(price, "#ef5350", "SL");
      }
    },
    true
  );

  window.addEventListener("mouseup", function () {
    if (!dragTarget) {
      return;
    }
    const target = dragTarget;
    dragTarget = null;
    setInteractionEnabled(true);
    postToQt({
      type: "levelsChanged",
      entry: currentLevels.entry,
      tp: currentLevels.tp,
      sl: currentLevels.sl,
      dragged: target,
    });
  });

  window.retradeChart = {
    setCandles: function (candles, fit, precision) {
      if (precision != null) {
        applyPriceFormat(precision);
      }
      lastCandles = candles || [];
      candleSeries.setData(lastCandles);
      if (fit !== false) {
        resetView(lastCandles);
      }
    },
    updateCandle: function (candle) {
      candleSeries.update(candle);
      if (!candle) {
        return;
      }
      if (
        lastCandles.length &&
        lastCandles[lastCandles.length - 1].time === candle.time
      ) {
        lastCandles[lastCandles.length - 1] = candle;
      } else {
        lastCandles.push(candle);
      }
    },
    resetView: function () {
      resetView(lastCandles);
    },
    setTradeLevels: setTradeLevels,
    clearTradeLevels: clearTradeLines,
    setOverlays: setOverlays,
    clearOverlays: clearOverlays,
    setHud: function (text) {
      hud.textContent = text || "";
    },
    ready: function () {
      postToQt({ type: "ready" });
    },
  };

  function bindBridge() {
    if (typeof qt === "undefined" || typeof QWebChannel === "undefined") {
      window.retradeChart.ready();
      return;
    }
    new QWebChannel(qt.webChannelTransport, function (channel) {
      window.qtBridge = channel.objects.qtBridge;
      window.retradeChart.ready();
    });
  }

  if (document.readyState === "complete") {
    bindBridge();
  } else {
    window.addEventListener("load", bindBridge);
  }
})();
