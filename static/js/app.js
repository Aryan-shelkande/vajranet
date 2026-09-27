(() => {
  const pad = (n) => String(n).padStart(2, "0");
  const cfg = () => window.VAJRANET_CONFIG || {};

  function tickClock() {
    const el = document.getElementById("clock");
    if (!el) return;
    const now = new Date();
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(now);
    const get = (type) => parts.find((p) => p.type === type)?.value || "";
    el.textContent = `${get("day")}/${get("month")}/${get("year")} ${get("hour")}:${get("minute")} IST`;
    el.dateTime = now.toISOString();
  }

  async function fetchJSON(url, options = {}) {
    const res = await fetch(url, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      const err = new Error(`Request failed: ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  function severityColor(temp) {
    if (temp == null) return "#647c91";
    if (temp >= 40) return "#ef4444";
    if (temp >= 32) return "#f59e0b";
    if (temp >= 20) return "#38a9e8";
    return "#3b82f6";
  }

  function atmosphereFromWeather(weather, nowcast) {
    if (!weather) return "partly-cloudy";
    const code = weather.weather_code;
    const temp = weather.temperature_c;
    const rain = weather.rainfall_mm || 0;
    const risk = (nowcast && nowcast.risk_level) || "";
    if (code === 95 || code === 96 || code === 99 || /HIGH/i.test(risk)) return "thunderstorm";
    if (code === 65 || code === 67 || code === 82 || rain >= 8) return "heavy-rain";
    if ([51, 53, 55, 56, 57, 61, 63, 66, 80, 81].includes(code)) return "rain";
    if (typeof temp === "number" && temp >= 38) return "extreme-heat";
    if (code === 0 || code === 1) return "sunny";
    if (code === 2) return "partly-cloudy";
    if (code === 3 || code === 45 || code === 48) return "cloudy";
    return "partly-cloudy";
  }

  function intensityFromState(condition, nowcast) {
    const risk = String((nowcast && nowcast.risk_level) || "").toUpperCase();
    if (risk === "HIGH" || risk === "VERY HIGH" || condition === "thunderstorm" || condition === "heavy-rain") {
      return "high";
    }
    if (condition === "rain" || condition === "cloudy" || condition === "extreme-heat") return "medium";
    return "low";
  }

  const Atmosphere = {
    reducedMotion: false,
    ticking: false,
    _lightningTimer: null,

    init() {
      const root = document.getElementById("atmospheric-background");
      if (!root) return;
      this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (this.reducedMotion) document.body.classList.add("reduced-motion");
      this.applyTimeOfDay();
      this.bindScroll();
      this.scheduleLightning();
      window.setInterval(() => this.applyTimeOfDay(), 5 * 60 * 1000);
    },

    scheduleLightning() {
      if (this.reducedMotion) return;
      const flash = () => {
        const body = document.body;
        const decorative =
          body.classList.contains("theme-storm") ||
          body.classList.contains("cond-thunderstorm");
        const bolt = document.querySelector(".atmosphere .atm-lightning");
        if (decorative && bolt) {
          bolt.classList.add("is-flash");
          window.setTimeout(() => bolt.classList.remove("is-flash"), 220);
        }
        const wait = 15000 + Math.random() * 15000;
        this._lightningTimer = window.setTimeout(flash, wait);
      };
      this._lightningTimer = window.setTimeout(flash, 8000 + Math.random() * 8000);
    },

    applyTimeOfDay() {
      const hour = Number(
        new Intl.DateTimeFormat("en-GB", {
          timeZone: "Asia/Kolkata",
          hour: "numeric",
          hour12: false,
        }).format(new Date())
      );
      let tod = "day";
      if (hour < 6) tod = "night";
      else if (hour < 11) tod = "morning";
      else if (hour < 17) tod = "day";
      else if (hour < 20) tod = "evening";
      else tod = "night";
      const body = document.body;
      [...body.classList].forEach((c) => {
        if (c.startsWith("tod-")) body.classList.remove(c);
      });
      body.classList.add(`tod-${tod}`);
      body.dataset.timeOfDay = tod;
    },

    setCondition(condition, nowcast) {
      const body = document.body;
      if (body.classList.contains("sky-lock")) return;
      const state = condition || "partly-cloudy";
      [...body.classList].forEach((c) => {
        if (c.startsWith("cond-") || c.startsWith("atm-")) body.classList.remove(c);
      });
      body.classList.add(`cond-${state}`);
      body.dataset.atmosphere = state;
      const intensity = intensityFromState(state, nowcast);
      body.dataset.intensity = intensity;
      const intensityMap = { low: 0.4, medium: 0.55, high: 0.75 };
      body.style.setProperty("--atm-intensity", String(intensityMap[intensity] || 0.55));
    },

    bindScroll() {
      if (this.reducedMotion) return;
      const onScroll = () => {
        if (this.ticking) return;
        this.ticking = true;
        window.requestAnimationFrame(() => {
          const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
          const progress = Math.min(1, Math.max(0, window.scrollY / max));
          document.documentElement.style.setProperty("--atm-scroll", progress.toFixed(4));
          this.ticking = false;
        });
      };
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    },
  };

  function weatherEmoji(weather) {
    if (!weather) return "☁";
    const code = weather.weather_code;
    if ([95, 96, 99].includes(code)) return "⛈";
    if ([61, 63, 65, 80, 81, 82, 51, 53, 55].includes(code)) return "🌧";
    if (code === 0 || code === 1) return "☀";
    if (code === 2) return "⛅";
    return "☁";
  }

  const VajraNet = {
    map: null,
    layers: {},
    radarLayer: null,
    basemapLayer: null,
    selectedCity: window.VAJRANET_CITY || "Pune",
    selectedMarker: null,
    cityIndex: {},
    searchTimer: null,

    setGreeting() {
      const label = document.getElementById("hero-greeting-label");
      const title = document.getElementById("hero-greeting");
      const hour = Number(
        new Intl.DateTimeFormat("en-GB", {
          timeZone: "Asia/Kolkata",
          hour: "numeric",
          hour12: false,
        }).format(new Date())
      );
      let greet = "Good day";
      if (hour < 12) greet = "Good morning";
      else if (hour < 17) greet = "Good afternoon";
      else greet = "Good evening";
      if (label) label.textContent = `${greet} · Atmospheric intelligence`;
      if (title) title.textContent = "VajraNet";
    },

    applyAtmosphere(state) {
      Atmosphere.setCondition(state || "partly-cloudy");
    },

    applyAtmosphereFromWeather(weather, nowcast) {
      Atmosphere.setCondition(atmosphereFromWeather(weather, nowcast), nowcast);
    },

    renderWeatherIcon(weather) {
      const el = document.getElementById("wx-icon");
      if (!el) return;
      const state = atmosphereFromWeather(weather, null);
      if (state === "sunny" || state === "extreme-heat") {
        el.classList.add("sun");
        el.innerHTML = `
          <circle cx="36" cy="36" r="12" fill="#f59e0b"/>
          ${[0, 45, 90, 135, 180, 225, 270, 315]
            .map(
              (a) =>
                `<rect class="ray" x="34" y="8" width="4" height="10" rx="2" fill="#fbbf24" transform="rotate(${a} 36 36)"/>`
            )
            .join("")}`;
      } else if (state === "rain" || state === "heavy-rain" || state === "thunderstorm") {
        el.classList.remove("sun");
        el.innerHTML = `
          <ellipse cx="30" cy="30" rx="14" ry="10" fill="#94a3b8"/>
          <ellipse cx="44" cy="32" rx="12" ry="9" fill="#647c91"/>
          <path d="M28 44 l-2 10 M36 44 l-2 12 M44 44 l-2 9" stroke="#38a9e8" stroke-width="2" stroke-linecap="round"/>
          ${
            state === "thunderstorm"
              ? '<path d="M40 38 L34 48 H40 L36 58" fill="#f59e0b" stroke="#b45309" stroke-width="1"/>'
              : ""
          }`;
      } else {
        el.classList.remove("sun");
        el.innerHTML = `
          <circle cx="26" cy="28" r="10" fill="#fbbf24" opacity="0.85"/>
          <ellipse cx="40" cy="34" rx="16" ry="11" fill="#cbd5e1"/>
          <ellipse cx="28" cy="36" rx="12" ry="9" fill="#e2e8f0"/>`;
      }
    },

    mapStyleUrl() {
      const url = (cfg().mapStyleUrl || "").trim();
      if (!url || /tile\.openstreetmap\.org|basemaps\.cartocdn|cartodb/i.test(url)) {
        return "https://tiles.openfreemap.org/styles/liberty";
      }
      return url;
    },

    basemapAttribution() {
      return (
        cfg().mapAttribution ||
        'OpenFreeMap © <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'
      );
    },

    showMapError(message) {
      const err = document.getElementById("map-error");
      if (!err) return;
      err.textContent = message || "Map temporarily unavailable. Please retry.";
      err.classList.add("visible");
    },

    hideMapError() {
      const err = document.getElementById("map-error");
      if (err) err.classList.remove("visible");
    },

    addBasemap(map) {
      if (!map || !window.L) throw new Error("leaflet_unavailable");
      if (typeof L.maplibreGL !== "function") {
        throw new Error("maplibre_gl_leaflet_unavailable");
      }
      const layer = L.maplibreGL({
        style: this.mapStyleUrl(),
        attribution: this.basemapAttribution(),
        interactive: false,
      });
      layer.addTo(map);

      const syncGlSize = () => {
        try {
          map.invalidateSize({ pan: false });
          const glMap = layer.getMaplibreMap && layer.getMaplibreMap();
          if (glMap) {
            glMap.resize();
            // Nudge paint after Leaflet pane layout settles
            if (typeof glMap.triggerRepaint === "function") glMap.triggerRepaint();
          }
        } catch (_) {
          /* ignore */
        }
      };

      try {
        const glMap = layer.getMaplibreMap && layer.getMaplibreMap();
        if (glMap) {
          glMap.on("error", (e) => {
            const msg = (e && e.error && e.error.message) || "";
            if (/403|401|failed|error/i.test(msg)) {
              this.showMapError("Map temporarily unavailable. Please retry.");
            }
          });
          glMap.once("load", () => {
            this.hideMapError();
            syncGlSize();
            setTimeout(syncGlSize, 100);
            setTimeout(syncGlSize, 400);
          });
          glMap.on("idle", () => this.hideMapError());
        }
      } catch (_) {
        /* older plugin builds may not expose getMaplibreMap */
      }

      // Always schedule size syncs — GL layer often mounts before container layout is final
      setTimeout(syncGlSize, 50);
      setTimeout(syncGlSize, 250);
      setTimeout(syncGlSize, 800);
      return layer;
    },

    initHomeMap() {
      const el = document.getElementById("india-map");
      if (!el || !window.L) return;
      if (this.map) {
        this.map.remove();
        this.map = null;
      }
      this.hideMapError();
      this.map = L.map(el, {
        zoomControl: true,
        scrollWheelZoom: true,
        minZoom: 3,
        maxZoom: cfg().mapMaxZoom || 18,
      }).setView([22.5, 79], 5);

      try {
        this.basemapLayer = this.addBasemap(this.map);
      } catch (err) {
        console.warn("Basemap failed", err);
        this.showMapError("Map temporarily unavailable. Please retry.");
      }

      this.layers.temperature = L.layerGroup().addTo(this.map);
      this.layers.rainfall = L.layerGroup().addTo(this.map);
      this.layers.earthquakes = L.layerGroup().addTo(this.map);
      this.layers.selection = L.layerGroup().addTo(this.map);

      document.querySelectorAll("#layer-controls input[data-layer]").forEach((input) => {
        input.addEventListener("change", () => this.syncLayers(input));
      });

      this.loadCityMarkers().then(() => {
        this.highlightSelectedCity(this.selectedCity || window.VAJRANET_CITY);
      });
      this.loadEarthquakes();
      this.loadAlertsPill();
      this.poll();

      const invalidate = () => {
        if (!this.map) return;
        this.map.invalidateSize();
        try {
          const gl = this.basemapLayer && this.basemapLayer.getMaplibreMap && this.basemapLayer.getMaplibreMap();
          if (gl) gl.resize();
        } catch (_) {
          /* ignore */
        }
      };
      setTimeout(invalidate, 200);
      setTimeout(invalidate, 800);
      window.addEventListener("resize", invalidate);
      document.getElementById("primary-nav")?.addEventListener("transitionend", invalidate);
    },

    createLightMap(targetId) {
      const el = document.getElementById(targetId);
      if (!el || !window.L) return null;
      const map = L.map(el, {
        zoomControl: true,
        minZoom: 3,
        maxZoom: cfg().mapMaxZoom || 18,
      }).setView([22.5, 79], 5);
      try {
        this.addBasemap(map);
      } catch (err) {
        console.warn("Basemap failed", err);
      }
      setTimeout(() => map.invalidateSize(), 250);
      return map;
    },

    syncLayers(input) {
      const key = input.dataset.layer;
      const status = document.getElementById("radar-status");
      if (key === "radar") {
        if (input.checked) this.enableRadar();
        else {
          if (this.radarLayer) {
            this.map.removeLayer(this.radarLayer);
            this.radarLayer = null;
          }
          if (status) status.textContent = "";
        }
        return;
      }
      const layer = this.layers[key];
      if (!layer) return;
      if (input.checked) layer.addTo(this.map);
      else this.map.removeLayer(layer);
    },

    async loadCityMarkers() {
      try {
        const data = await fetchJSON("/api/weather/map/");
        this.layers.temperature?.clearLayers();
        this.layers.rainfall?.clearLayers();
        this.cityIndex = {};
        (data.cities || []).forEach((item) => {
          const loc = item.location || {};
          const lat = loc.latitude;
          const lon = loc.longitude;
          if (lat == null || lon == null) return;
          const temp = item.temperature_c;
          const color = severityColor(temp);
          const name = loc.name || "";
          const icon = L.divIcon({
            className: "",
            html: `<div class="temp-label" data-city="${name}" style="border-color:${color}"><div>${temp == null ? "—" : Math.round(temp)}°</div><small>${name}</small></div>`,
            iconSize: [64, 36],
            iconAnchor: [32, 18],
          });
          const tempMarker = L.marker([lat, lon], { icon }).bindPopup(
            `<strong>${name}</strong><br>${temp ?? "—"}°C<br>${item.weather_description || ""}<br><small>${item.source || ""} · ${item.data_kind || ""}</small>`
          );
          this.layers.temperature.addLayer(tempMarker);
          if (name) {
            this.cityIndex[name.toLowerCase()] = {
              lat,
              lon,
              marker: tempMarker,
              item,
            };
          }

          const rain = item.rainfall_mm || 0;
          if (rain > 0) {
            const rainMarker = L.circleMarker([lat, lon], {
              radius: Math.min(18, 6 + rain * 2),
              color: "#38a9e8",
              fillColor: "#5bc0eb",
              fillOpacity: 0.25,
              weight: 1,
            }).bindPopup(`<strong>${name}</strong><br>Rain ${rain} mm`);
            this.layers.rainfall.addLayer(rainMarker);
          }
        });
      } catch (err) {
        console.warn("Map weather load failed", err);
      }
    },

    highlightSelectedCity(city) {
      if (!this.map || !city) return;
      const entry = this.cityIndex[(city || "").toLowerCase()];
      this.layers.selection?.clearLayers();
      document.querySelectorAll(".temp-label.selected").forEach((el) => el.classList.remove("selected"));

      const weather = window.VAJRANET_WEATHER || {};
      const loc = (weather.location && weather.location.name === city && weather.location) || (entry && {
        latitude: entry.lat,
        longitude: entry.lon,
        name: city,
      });
      if (!loc || loc.latitude == null || loc.longitude == null) return;

      const ring = L.circleMarker([loc.latitude, loc.longitude], {
        radius: 18,
        color: "#38a9e8",
        weight: 3,
        fillColor: "#5bc0eb",
        fillOpacity: 0.15,
        className: "selected-city-ring",
      }).bindPopup(`<strong>${loc.name || city}</strong><br>Selected city`);
      this.layers.selection.addLayer(ring);

      if (entry && entry.marker) {
        const el = entry.marker.getElement();
        const label = el && el.querySelector(".temp-label");
        if (label) label.classList.add("selected");
        entry.marker.openPopup();
      }

      this.map.flyTo([loc.latitude, loc.longitude], Math.max(this.map.getZoom(), 7), {
        duration: 0.75,
      });
    },

    async loadEarthquakes() {
      try {
        const data = await fetchJSON("/api/disasters/earthquakes/");
        if (!data.available) return;
        (data.events || []).forEach((ev) => {
          if (ev.latitude == null || ev.longitude == null) return;
          const m = L.circleMarker([ev.latitude, ev.longitude], {
            radius: Math.max(5, (ev.magnitude || 3) * 2),
            color: "#ef4444",
            fillColor: "#ef4444",
            fillOpacity: 0.45,
            weight: 1,
          }).bindPopup(
            `<strong>${ev.title}</strong><br>M${ev.magnitude ?? "—"}<br><small>OBSERVED · Source: USGS</small>`
          );
          this.layers.earthquakes.addLayer(m);
        });
      } catch (err) {
        console.warn("Earthquake layer failed", err);
      }
    },

    async enableRadar() {
      const status = document.getElementById("radar-status");
      if (status) status.textContent = "Loading radar…";
      try {
        const data = await fetchJSON("/api/radar/");
        if (!data.available || !data.frames || !data.frames.length) {
          if (status) status.textContent = "Radar unavailable";
          const input = document.querySelector('#layer-controls input[data-layer="radar"]');
          if (input) input.checked = false;
          return;
        }
        const last =
          data.frames.filter((f) => f.kind === "observed").pop() || data.frames.at(-1);
        if (this.radarLayer) this.map.removeLayer(this.radarLayer);
        this.radarLayer = L.tileLayer(last.path, {
          opacity: 0.55,
          attribution: data.attribution || "Weather data by RainViewer",
        }).addTo(this.map);
        if (status) status.textContent = "Radar · RainViewer (not IMD)";
      } catch (err) {
        console.warn("Radar layer failed", err);
        if (status) status.textContent = "Radar unavailable";
        const input = document.querySelector('#layer-controls input[data-layer="radar"]');
        if (input) input.checked = false;
      }
    },

    async loadAlertsPill(city) {
      const pill = document.getElementById("alert-pill");
      if (!pill) return;
      try {
        const c = city || window.VAJRANET_CITY || "Pune";
        const data = await fetchJSON(`/api/alerts/?city=${encodeURIComponent(c)}`);
        const count = (data.alerts || []).length;
        pill.textContent = count ? `${count} alert${count > 1 ? "s" : ""}` : "No alerts";
        pill.classList.toggle("warn", count > 0);
        pill.classList.toggle(
          "danger",
          (data.alerts || []).some((a) => a.severity === "high" || a.severity === "extreme")
        );
      } catch (_) {
        pill.textContent = "Alerts";
      }
    },

    initTempChart(daily) {
      const canvas = document.getElementById("temp-chart");
      if (!canvas || !window.Chart || !daily || !daily.length) return;
      if (canvas._chart) {
        canvas._chart.destroy();
      }
      canvas._chart = new Chart(canvas, {
        type: "line",
        data: {
          labels: daily.map((d) => d.time),
          datasets: [
            {
              label: "Max °C",
              data: daily.map((d) => d.max),
              borderColor: "#ef4444",
              backgroundColor: "rgba(239,68,68,0.08)",
              tension: 0.35,
              fill: false,
            },
            {
              label: "Min °C",
              data: daily.map((d) => d.min),
              borderColor: "#38a9e8",
              backgroundColor: "rgba(56,169,232,0.08)",
              tension: 0.35,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend: { labels: { color: "#647c91" } } },
          scales: {
            x: {
              ticks: { color: "#647c91" },
              grid: { color: "rgba(22,50,79,0.06)" },
            },
            y: {
              ticks: { color: "#647c91" },
              grid: { color: "rgba(22,50,79,0.06)" },
            },
          },
        },
      });
    },

    initCitySearch() {
      const input = document.getElementById("city-input");
      const results = document.getElementById("city-results");
      const form = document.getElementById("city-search-form");
      if (!input || !results) return;

      const close = () => {
        results.classList.remove("open");
        results.innerHTML = "";
      };

      input.addEventListener("input", () => {
        const q = input.value.trim();
        clearTimeout(this.searchTimer);
        if (q.length < 2) {
          close();
          return;
        }
        this.searchTimer = setTimeout(async () => {
          try {
            const data = await fetchJSON(`/api/locations/search/?q=${encodeURIComponent(q)}`);
            const items = data.results || [];
            if (!items.length) {
              results.innerHTML = `<button type="button" disabled><strong>No matches</strong><span>Try another Indian city</span></button>`;
              results.classList.add("open");
              return;
            }
            results.innerHTML = items
              .map(
                (r, i) => `<button type="button" role="option" data-idx="${i}" data-name="${String(r.name || "").replace(/"/g, "&quot;")}">
                  <strong>${r.name || ""}</strong>
                  <span>${[r.state, r.country_code || "India"].filter(Boolean).join(", ")}</span>
                </button>`
              )
              .join("");
            results.classList.add("open");
            results.querySelectorAll("button[data-name]").forEach((btn) => {
              btn.addEventListener("click", () => {
                const name = btn.dataset.name;
                input.value = name;
                close();
                this.selectCity(name, { pushUrl: true });
              });
            });
          } catch (err) {
            console.warn("City search failed", err);
          }
        }, 220);
      });

      form?.addEventListener("submit", (e) => {
        e.preventDefault();
        const name = input.value.trim();
        if (!name) return;
        close();
        this.selectCity(name, { pushUrl: true });
      });

      document.addEventListener("click", (e) => {
        if (!e.target.closest("#city-search")) close();
      });

      document.querySelectorAll("#featured-chips [data-city]").forEach((chip) => {
        chip.addEventListener("click", (e) => {
          e.preventDefault();
          this.selectCity(chip.dataset.city, { pushUrl: true });
        });
      });
    },

    async selectCity(city, { pushUrl } = {}) {
      this.selectedCity = city;
      window.VAJRANET_CITY = city;
      const input = document.getElementById("city-input");
      if (input) input.value = city;
      if (pushUrl) {
        const view = window.VAJRANET_VIEW || "citizen";
        const url = `/?city=${encodeURIComponent(city)}&view=${encodeURIComponent(view)}`;
        window.history.pushState({ city }, "", url);
      }
      await this.refreshDashboard(city);
      this.loadAlertsPill(city);
      this.highlightSelectedCity(city);
    },

    async refreshDashboard(city) {
      const live = document.getElementById("dashboard-live");
      if (live) live.setAttribute("aria-busy", "true");
      try {
        const [current, forecast, alerts, nowcast] = await Promise.all([
          fetchJSON(`/api/weather/current/?city=${encodeURIComponent(city)}`),
          fetchJSON(`/api/weather/forecast/?city=${encodeURIComponent(city)}`),
          fetchJSON(`/api/alerts/?city=${encodeURIComponent(city)}`),
          fetchJSON(`/api/nowcasting/?city=${encodeURIComponent(city)}`),
        ]);
        window.VAJRANET_WEATHER = current;
        window.VAJRANET_NOWCAST = nowcast;
        window.VAJRANET_ALERTS = alerts.alerts || [];
        this.applyAtmosphereFromWeather(current, nowcast);
        this.renderWeatherIcon(current);
        this.updateConditionCard(current);
        this.updateNowcastCard(nowcast);
        this.updateAlerts(alerts);
        this.updateForecast(forecast);
      } catch (err) {
        console.warn("Dashboard refresh failed", err);
        const banner = document.getElementById("weather-error");
        if (banner) {
          banner.style.display = "block";
          banner.innerHTML = `Weather data temporarily unavailable<div class="meta" style="margin:0.35rem 0 0;color:inherit">Could not refresh ${city}. <button type="button" class="btn secondary" onclick="location.reload()">Retry</button></div>`;
        }
      } finally {
        if (live) live.removeAttribute("aria-busy");
      }
    },

    updateConditionCard(current) {
      if (!current) return;
      const loc = current.location || {};
      const setText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
      };
      setText(
        "condition-place",
        `${loc.name || ""}${loc.state ? `, ${loc.state}` : ""}`
      );
      setText(
        "condition-temp",
        `${current.temperature_c == null ? "—" : Math.round(current.temperature_c)}°`
      );
      setText("condition-desc", current.weather_description || "—");
      setText(
        "condition-feels",
        `Feels like ${current.feels_like_c == null ? "—" : Math.round(current.feels_like_c)}°`
      );
      setText(
        "m-humidity",
        `${current.humidity_pct == null ? "—" : Math.round(current.humidity_pct)}%`
      );
      setText(
        "m-wind",
        `${current.wind_speed_kmh == null ? "—" : Math.round(current.wind_speed_kmh)} km/h`
      );
      setText(
        "m-pressure",
        `${current.pressure_hpa == null ? "—" : Math.round(current.pressure_hpa)} hPa`
      );
      setText("m-rain", `${current.rainfall_mm ?? 0} mm`);
      setText("condition-observed", current.observed_at || "");
    },

    updateNowcastCard(nowcast) {
      if (!nowcast) return;
      const level = document.getElementById("nowcast-level");
      if (level) {
        level.textContent = nowcast.risk_level || "—";
        level.className = `risk-level ${nowcast.risk_level || ""}`;
      }
      const place = document.getElementById("nowcast-place");
      if (place) {
        place.textContent = `${(nowcast.location && nowcast.location.name) || ""} · Next 60 minutes`;
      }
      const label = document.getElementById("nowcast-label");
      if (label) {
        label.innerHTML = `${nowcast.label || ""} · Score <span id="nowcast-score">${nowcast.risk_score ?? "—"}</span>/100`;
      }
      const meter = document.getElementById("nowcast-meter");
      if (meter) meter.style.width = `${nowcast.risk_score || 0}%`;
      const factors = document.getElementById("nowcast-factors");
      if (factors) {
        const items = nowcast.factors || [];
        factors.innerHTML = items.length
          ? items
              .slice(0, 5)
              .map(
                (f) =>
                  `<li>• ${f.name} — ${f.signal}${f.value ? ` (${f.value})` : ""}</li>`
              )
              .join("")
          : "<li>• Factors unavailable for this assessment</li>";
      }
      const updated = document.getElementById("nowcast-updated");
      if (updated) {
        updated.textContent = `Model: Baseline / Derived risk · Updated ${nowcast.observed_at || ""} ${nowcast.timezone || ""}`;
      }
    },

    updateAlerts(payload) {
      const note = document.getElementById("alert-note");
      if (note) note.textContent = payload.note || "";
      const list = document.getElementById("alerts-list");
      if (!list) return;
      const alerts = payload.alerts || [];
      if (!alerts.length) {
        list.innerHTML = `<div class="empty">No derived alerts for this location right now.</div>`;
        return;
      }
      list.innerHTML = alerts
        .map((a) => {
          const derived =
            a.data_kind === "derived_risk" || a.origin === "derived"
              ? `<span class="badge derived">Derived risk</span>`
              : a.data_kind || a.origin || "";
          return `<div class="alert-item ${a.severity || ""}">
            <strong>⚠ ${a.title || "Alert"}</strong>
            <span>${a.area_name || ""} · ${(a.severity || "").toUpperCase()} · ${derived}</span>
            <span>${a.description || ""}</span>
            ${a.recommended_action ? `<span><em>Action:</em> ${a.recommended_action}</span>` : ""}
            ${a.source ? `<span class="meta">Source: ${a.source}</span>` : ""}
          </div>`;
        })
        .join("");
    },

    updateForecast(forecast) {
      const hourly = (forecast.hourly || []).slice(0, 12);
      const daily = (forecast.daily || []).slice(0, 7);
      const strip = document.getElementById("hourly-strip");
      if (strip && hourly.length) {
        strip.innerHTML = hourly
          .map((h, i) => {
            const t = i === 0 ? "Now" : String(h.time || "").slice(11, 16);
            const icon = h.thunderstorm_hint
              ? "⛈"
              : h.precipitation_mm > 0
                ? "🌧"
                : weatherEmoji({ weather_code: h.weather_code });
            return `<div class="hour-card">
              <div class="t">${t}</div>
              <div class="icon">${icon}</div>
              <strong>${h.temperature_c == null ? "—" : Math.round(h.temperature_c)}°</strong>
              <div class="t">${h.precipitation_probability_pct ?? "—"}%</div>
            </div>`;
          })
          .join("");
      }
      const dailyStrip = document.getElementById("daily-strip");
      if (dailyStrip && daily.length) {
        dailyStrip.innerHTML = daily
          .map(
            (d) => `<div class="day-card">
              <div class="t">${d.time || ""}</div>
              <div class="icon">🌤</div>
              <strong>${d.temperature_max_c == null ? "—" : Math.round(d.temperature_max_c)}° / ${d.temperature_min_c == null ? "—" : Math.round(d.temperature_min_c)}°</strong>
              <div class="t">${d.precipitation_mm ?? 0} mm</div>
            </div>`
          )
          .join("");
      }
      window.VAJRANET_DAILY = daily.map((d) => ({
        time: d.time,
        min: d.temperature_min_c,
        max: d.temperature_max_c,
      }));
      this.initTempChart(window.VAJRANET_DAILY);
    },

    initEmergencyKit() {
      const items = document.querySelectorAll("[data-kit-item]");
      if (!items.length) return;
      const key = "vajranet-kit";
      const saved = JSON.parse(localStorage.getItem(key) || "{}");
      const progress = document.getElementById("kit-progress");
      const sync = () => {
        let ready = 0;
        items.forEach((el) => {
          const id = el.dataset.kitItem;
          const on = !!saved[id];
          el.classList.toggle("checked", on);
          const input = el.querySelector("input");
          if (input) input.checked = on;
          if (on) ready += 1;
        });
        if (progress) progress.textContent = `${ready} / ${items.length} items ready`;
      };
      items.forEach((el) => {
        el.addEventListener("click", () => {
          const id = el.dataset.kitItem;
          saved[id] = !saved[id];
          localStorage.setItem(key, JSON.stringify(saved));
          sync();
        });
      });
      sync();
    },

    initNav() {
      const toggle = document.querySelector(".nav-toggle");
      const nav = document.getElementById("primary-nav");
      if (!toggle || !nav) return;
      toggle.addEventListener("click", () => {
        const open = nav.classList.toggle("open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (this.map) setTimeout(() => this.map.invalidateSize(), 200);
      });
      const path = window.location.pathname.replace(/\/$/, "") || "/";
      nav.querySelectorAll("a").forEach((a) => {
        try {
          const href = new URL(a.href).pathname.replace(/\/$/, "") || "/";
          if (href === path) a.setAttribute("aria-current", "page");
        } catch (_) {
          /* ignore */
        }
      });
    },

    initAssistant() {
      const panel = document.getElementById("vajra-ai-panel");
      const fab = document.getElementById("ai-fab");
      const headerBtn = document.getElementById("ai-launch-header");
      const closeBtn = document.getElementById("ai-close");
      const form = document.getElementById("ai-form");
      const input = document.getElementById("ai-input");
      const messages = document.getElementById("ai-messages");
      const modeLabel = document.getElementById("ai-mode-label");
      if (!panel || !form || !messages) return;

      const setOpen = (open) => {
        panel.classList.toggle("open", open);
        panel.setAttribute("aria-hidden", open ? "false" : "true");
        fab?.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) input?.focus();
      };

      fab?.addEventListener("click", () => setOpen(!panel.classList.contains("open")));
      headerBtn?.addEventListener("click", () => setOpen(true));
      closeBtn?.addEventListener("click", () => setOpen(false));

      document.querySelectorAll("[data-ai-prompt]").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (input) input.value = btn.dataset.aiPrompt;
          form.requestSubmit();
        });
      });

      const append = (text, cls) => {
        const bubble = document.createElement("div");
        bubble.className = `ai-bubble${cls ? ` ${cls}` : ""}`;
        bubble.textContent = text;
        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;
      };

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const question = (input?.value || "").trim();
        if (!question) return;
        append(question, "user");
        input.value = "";
        append("Thinking…");
        const thinking = messages.lastChild;
        try {
          const weather = window.VAJRANET_WEATHER || {};
          const nowcast = window.VAJRANET_NOWCAST || {};
          const payload = {
            question,
            city: window.VAJRANET_CITY || this.selectedCity || "",
            language: document.getElementById("ask-lang")?.value || "en",
            use_live_data: true,
            context: {
              city: window.VAJRANET_CITY || this.selectedCity,
              location: weather.location || {},
              weather: {
                temperature_c: weather.temperature_c,
                feels_like_c: weather.feels_like_c,
                humidity_pct: weather.humidity_pct,
                wind_speed_kmh: weather.wind_speed_kmh,
                pressure_hpa: weather.pressure_hpa,
                rainfall_mm: weather.rainfall_mm,
                weather_code: weather.weather_code,
                weather_description: weather.weather_description,
                cloud_cover_pct: weather.cloud_cover_pct,
                data_kind: weather.data_kind,
                source: weather.source,
              },
              nowcast: {
                risk_level: nowcast.risk_level,
                risk_score: nowcast.risk_score,
                label: nowcast.label,
                engine_type: nowcast.engine_type,
                data_kind: nowcast.data_kind,
                factors: nowcast.factors || [],
              },
              alerts: window.VAJRANET_ALERTS || [],
              lightning_status: "unavailable",
            },
          };
          const data = await fetchJSON("/api/assistant/", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": cfg().csrfToken || "",
            },
            body: JSON.stringify(payload),
          });
          thinking.remove();
          if (modeLabel) {
            if (data.mode === "llm") {
              modeLabel.textContent =
                data.provider === "ollama"
                  ? "Vajra AI — local model enabled"
                  : "Vajra AI — AI model enabled";
            } else {
              modeLabel.textContent = data.provider_error
                ? data.provider_error
                : "Platform Assistant";
            }
          }
          append(data.answer || "No response available.");
        } catch (err) {
          thinking.textContent =
            "Assistant temporarily unavailable. Try again, or open the Safety Center.";
          console.warn("AI assistant failed", err);
        }
      });
    },

    poll() {
      setInterval(() => {
        this.loadAlertsPill(window.VAJRANET_CITY || this.selectedCity);
      }, 5 * 60 * 1000);
    },
  };

  window.VajraNet = VajraNet;
  window.VajraAtmosphere = Atmosphere;
  document.addEventListener("DOMContentLoaded", () => {
    Atmosphere.init();
    tickClock();
    setInterval(tickClock, 30000);
    VajraNet.initNav();
    VajraNet.initEmergencyKit();
    VajraNet.initAssistant();
    VajraNet.setGreeting();
    window.addEventListener("popstate", (ev) => {
      const city = (ev.state && ev.state.city) || new URLSearchParams(location.search).get("city");
      if (city) VajraNet.selectCity(city, { pushUrl: false });
    });
  });
})();
