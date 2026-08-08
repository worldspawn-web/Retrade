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
      mode: 0,
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

  let candleSeries = null;
  let entryLine = null;
  let tpLine = null;
  let slLine = null;
  let dragTarget = null;
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

  function candleSeriesOptions() {
    return {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
      priceFormat: {
        type: "price",
        precision: pricePrecision,
        minMove: Math.pow(10, -pricePrecision),
      },
      lastValueVisible: true,
      priceLineVisible: false,
    };
  }

  function createCandleSeries() {
    return chart.addCandlestickSeries(candleSeriesOptions());
  }

  function applyPriceFormat(precision) {
    pricePrecision = Math.max(0, Math.min(10, precision | 0));
    if (candleSeries) {
      candleSeries.applyOptions({
        priceFormat: {
          type: "price",
          precision: pricePrecision,
          minMove: Math.pow(10, -pricePrecision),
        },
      });
    }
  }

  function clearTradeLines() {
    if (!candleSeries) {
      entryLine = null;
      tpLine = null;
      slLine = null;
      currentLevels = { entry: null, tp: null, sl: null };
      return;
    }
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
    if (candleSeries) {
      overlayPriceLines.forEach(function (line) {
        try {
          candleSeries.removePriceLine(line);
        } catch (e) {
          /* series may already be gone */
        }
      });
      try {
        candleSeries.setMarkers([]);
      } catch (e) {
        /* ignore */
      }
    }
    overlayPriceLines = [];
    overlayZoneSeries.forEach(function (series) {
      try {
        chart.removeSeries(series);
      } catch (e) {
        /* ignore */
      }
    });
    overlayZoneSeries = [];
  }

  /**
   * Hard reset: drop candle series + overlays so a prior BTC scale cannot
   * pin the axis when loading a $0.02 alt (and vice versa).
   */
  function hardResetSeries(precision) {
    clearTradeLines();
    clearOverlays();
    levelsEditable = false;
    if (candleSeries) {
      try {
        chart.removeSeries(candleSeries);
      } catch (e) {
        /* ignore */
      }
      candleSeries = null;
    }
    if (precision != null) {
      pricePrecision = Math.max(0, Math.min(10, precision | 0));
    }
    // Unlock price scale after user pan/zoom (autoScale may have been turned off).
    chart.priceScale("right").applyOptions({
      autoScale: true,
      mode: 0,
      scaleMargins: { top: 0.08, bottom: 0.12 },
    });
    candleSeries = createCandleSeries();
  }

  function fitTimeAndPrice() {
    chart.timeScale().fitContent();
    chart.priceScale("right").applyOptions({ autoScale: true });
    // Second fit after layout tick helps LWC recompute price range.
    window.requestAnimationFrame(function () {
      chart.timeScale().fitContent();
      chart.priceScale("right").applyOptions({ autoScale: true });
    });
  }

  function setOverlays(payload) {
    clearOverlays();
    if (!payload || !candleSeries) {
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

    const fmt = {
      type: "price",
      precision: pricePrecision,
      minMove: Math.pow(10, -pricePrecision),
    };

    (payload.segments || []).forEach(function (seg) {
      const style =
        seg.lineStyle == null
          ? LightweightCharts.LineStyle.Dashed
          : seg.lineStyle;
      const series = chart.addLineSeries({
        color: seg.color || "#26a69a",
        lineWidth: seg.lineWidth || 1,
        lineStyle: style,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        title: seg.title || "",
        priceFormat: fmt,
      });
      const t1 = seg.timeFrom;
      let t2 = seg.timeTo;
      if (t2 <= t1) {
        t2 = t1 + 1;
      }
      series.setData([
        { time: t1, value: seg.price },
        { time: t2, value: seg.price },
      ]);
      overlayZoneSeries.push(series);
    });

    (payload.zones || []).forEach(function (zone) {
      const top = chart.addLineSeries({
        color: zone.borderColor || "#26a69a",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.SparseDotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: fmt,
      });
      const bottom = chart.addLineSeries({
        color: zone.borderColor || "#26a69a",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.SparseDotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: fmt,
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
    if (!levels || !candleSeries) {
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
    if (!candleSeries || price == null) {
      return false;
    }
    const lineY = candleSeries.priceToCoordinate(price);
    if (lineY == null) {
      return false;
    }
    return Math.abs(lineY - y) <= HIT_PX;
  }

  candleSeries = createCandleSeries();

  chart.subscribeCrosshairMove(function (param) {
    if (!param || param.point === undefined || !param.time || !candleSeries) {
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
      if (!dragTarget || !candleSeries) {
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
      const shouldFit = fit !== false;
      if (shouldFit) {
        hardResetSeries(precision);
      } else if (precision != null) {
        applyPriceFormat(precision);
      }
      lastCandles = candles || [];
      if (!candleSeries) {
        candleSeries = createCandleSeries();
      }
      candleSeries.setData(lastCandles);
      if (shouldFit) {
        fitTimeAndPrice();
      }
    },
    updateCandle: function (candle) {
      if (!candleSeries || !candle) {
        return;
      }
      candleSeries.update(candle);
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
      if (!lastCandles.length) {
        return;
      }
      // Recreate around the same data to drop a stuck manual price scale.
      const preserved = lastCandles.slice();
      const levels = currentLevels;
      const editable = levelsEditable;
      hardResetSeries(pricePrecision);
      lastCandles = preserved;
      candleSeries.setData(lastCandles);
      fitTimeAndPrice();
      if (levels.entry != null || levels.tp != null || levels.sl != null) {
        setTradeLevels(levels, editable);
      }
    },
    setTradeLevels: setTradeLevels,
    clearTradeLevels: function () {
      clearTradeLines();
      levelsEditable = false;
    },
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
