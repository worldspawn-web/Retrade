/* Retrade chart bridge: Lightweight Charts + QWebChannel hooks. */
(function () {
  "use strict";

  const container = document.getElementById("chart");
  const hud = document.getElementById("hud");

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
    },
    timeScale: {
      borderColor: "#2a2e39",
      timeVisible: true,
      secondsVisible: false,
    },
    handleScroll: { vertTouchDrag: false },
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350",
  });

  let entryLine = null;
  let tpLine = null;
  let slLine = null;
  let dragTarget = null; // "tp" | "sl" | null
  let levelsEditable = false;
  let currentLevels = { entry: null, tp: null, sl: null };
  let overlayPriceLines = [];
  let overlayZoneSeries = [];

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
      });
      const bottom = chart.addLineSeries({
        color: zone.borderColor || "#26a69a",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.SparseDotted,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      });
      // Extend zone a bit to the right for visibility.
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

  function priceNear(price, target, tolPct) {
    if (price == null || target == null) {
      return false;
    }
    const tol = Math.abs(target) * tolPct;
    return Math.abs(price - target) <= tol;
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
      "O " + data.open + "  H " + data.high + "  L " + data.low + "  C " + data.close;
  });

  container.addEventListener("mousedown", function (ev) {
    if (!levelsEditable || currentLevels.tp == null || currentLevels.sl == null) {
      return;
    }
    const rect = container.getBoundingClientRect();
    const y = ev.clientY - rect.top;
    const price = candleSeries.coordinateToPrice(y);
    if (price == null) {
      return;
    }
    if (priceNear(price, currentLevels.tp, 0.0015)) {
      dragTarget = "tp";
      ev.preventDefault();
    } else if (priceNear(price, currentLevels.sl, 0.0015)) {
      dragTarget = "sl";
      ev.preventDefault();
    }
  });

  container.addEventListener("mousemove", function (ev) {
    if (!dragTarget) {
      return;
    }
    const rect = container.getBoundingClientRect();
    const y = ev.clientY - rect.top;
    const price = candleSeries.coordinateToPrice(y);
    if (price == null) {
      return;
    }
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
  });

  window.addEventListener("mouseup", function () {
    if (!dragTarget) {
      return;
    }
    const target = dragTarget;
    dragTarget = null;
    postToQt({
      type: "levelsChanged",
      entry: currentLevels.entry,
      tp: currentLevels.tp,
      sl: currentLevels.sl,
      dragged: target,
    });
  });

  window.retradeChart = {
    setCandles: function (candles, fit) {
      candleSeries.setData(candles || []);
      if (fit !== false) {
        chart.timeScale().fitContent();
      }
    },
    updateCandle: function (candle) {
      candleSeries.update(candle);
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

  // QWebChannel bootstrap (injected by Qt).
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
