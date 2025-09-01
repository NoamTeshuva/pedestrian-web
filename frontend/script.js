// script.js - Full Screen Map Application

function bboxFromLeafletMap(map) {
  if (!map) return null;
  const b = map.getBounds();
  const sw = b.getSouthWest(), ne = b.getNorthEast();
  return { west: sw.lng, south: sw.lat, east: ne.lng, north: ne.lat };
}

function smallBBoxAround(lat, lon, radiusKm = 3) {
  const b = L.latLng(lat, lon).toBounds(radiusKm * 1000);
  const sw = b.getSouthWest(), ne = b.getNorthEast();
  return { west: sw.lng, south: sw.lat, east: ne.lng, north: ne.lat };
}

// מדרג תוצאות Nominatim: מעדיפים ישויות יישוביות (city/town/village/hamlet/suburb/neighbourhood)
// ושמים בונוס אם country_code תואם לרמז מדינה אחרון (אם יש).
function pickBestGeocode(results, countryHint = null) {
  if (!Array.isArray(results) || !results.length) return null;

  const typeScore = {
    city: 100, town: 90, village: 80, hamlet: 70,
    suburb: 60, neighbourhood: 50, municipality: 45,
    county: 20, state: 10, country: 0
  };

  return results
    .map(r => {
      const t = (r.type || '').toLowerCase();
      const cls = (r.class || '').toLowerCase();
      let score = (typeScore[t] ?? 40);
      if (cls === 'place') score += 10;
      if (countryHint && r.address?.country_code?.toLowerCase() === countryHint.toLowerCase()) {
        score += 20;
      }
      // חשיבות של Nominatim (float) – מוסיפים מעט
      const imp = Number(r.importance ?? 0);
      score += Math.min(imp * 10, 10);
      return { r, score };
    })
    .sort((a, b) => b.score - a.score)
    .map(x => x.r)[0];
}

function normalizeBBoxFromLoc(loc, fallbackCenter) {
  // loc.boundingbox בפורמט [south, north, west, east] ב-jsonv2
  const bb = loc?.boundingbox || [];
  const south = parseFloat(bb[0]), north = parseFloat(bb[1]);
  const west  = parseFloat(bb[2]), east  = parseFloat(bb[3]);

  // אם חסר/לא מספרים – קופצים לבוקס קטן סביב המרכז
  const lat = parseFloat(loc?.lat);
  const lon = parseFloat(loc?.lon);
  if (![south, north, west, east].every(Number.isFinite)) {
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      return smallBBoxAround(lat, lon, 3);
    }
    if (fallbackCenter) return smallBBoxAround(fallbackCenter.lat, fallbackCenter.lon, 3);
    return null;
  }

  // אם ה-BBOX ענק (למשל מדינה שלמה) – מכווצים ל-3 ק״מ סביב המרכז
  const areaDeg2 = Math.abs((east - west) * (north - south));
  if (areaDeg2 > 1.0) { // בערך “גדול מדי”
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      return smallBBoxAround(lat, lon, 3);
    }
  }
  return { west, south, east, north };
}


class PedestrianPredictionApp {
    constructor() {
        this.API_BASE_URL = window.API_BASE || 'http://127.0.0.1:8000';
        console.log('[PedestrianPredictionApp] Using API:', this.API_BASE_URL);

        this.map = null;
        this.currentLayer = null;
        this._inFlight = false;

        this.initializeElements();
        this.setDefaultSearchParameters();
        this.initializeEventListeners();
        this.initializeMap();
        this.updateLegend();
        this.initializePanelToggles();
        this.lastGeocodeCenter = null;
        this.lastGeocodeBBox = null;
        this.lastCountryHint = null; // נשמר מהתוצאה האחרונה, לא מחייב ישראל

    }

    // -----------------------------
    // DOM Elements & UI
    // -----------------------------
    initializeElements() {
        this.searchForm = document.getElementById('searchForm');
        this.cityInput = document.getElementById('cityInput');
        this.searchBtn = document.getElementById('searchBtn');
        this.buttonText = document.getElementById('buttonText');
        this.loadingSpinner = document.getElementById('loadingSpinner');
        this.statusMessage = document.getElementById('statusMessage');
        this.loadingMessage = document.getElementById('loadingMessage');
        this.predictionDetails = document.getElementById('predictionDetails');

        // Panels
        this.detailsPanel = document.getElementById('detailsPanel');
        this.parametersPanel = document.getElementById('parametersPanel');

        // Download GPKG button elements
        this.downloadGpkgBtn = document.getElementById('downloadGpkgBtn');
        this.downloadBtnText = document.getElementById('downloadBtnText');
        this.downloadLoadingSpinner = document.getElementById('downloadLoadingSpinner');

        // Search parameter elements
        this.seasonSelect = document.getElementById('seasonSelect');
        this.weekTypeSelect = document.getElementById('weekTypeSelect');
        this.timeOfDaySelect = document.getElementById('timeOfDaySelect');

        // Panel toggles
        this.parametersToggle = document.getElementById('parametersToggle');
        this.parametersClose = document.getElementById('parametersClose');
        this.detailsPanelToggle = document.getElementById('detailsPanelToggle');
        this.detailsPanelContent = document.getElementById('detailsPanelContent');
    }

    initializePanelToggles() {
        // Parameters panel toggle
        if (this.parametersToggle) {
            this.parametersToggle.addEventListener('click', () => {
                this.parametersPanel.classList.toggle('hidden');
            });
        }

        if (this.parametersClose) {
            this.parametersClose.addEventListener('click', () => {
                this.parametersPanel.classList.add('hidden');
            });
        }

        // Details panel toggle
        if (this.detailsPanelToggle) {
            this.detailsPanelToggle.addEventListener('click', () => {
                this.togglePanel('details');
            });
        }
    }

    togglePanel(panelName) {
        if (panelName === 'details' && this.detailsPanelContent && this.detailsPanelToggle) {
            this.detailsPanelContent.classList.toggle('collapsed');
            const icon = this.detailsPanelToggle.querySelector('.toggle-icon');
            if (icon) {
                icon.textContent = this.detailsPanelContent.classList.contains('collapsed') ? '+' : '−';
            }
        }
    }

    // -----------------------------
    // Defaults
    // -----------------------------
    setDefaultSearchParameters() {
        const now = new Date();

        // Set default season based on Israeli seasons
        const currentSeason = this.getCurrentSeason(now);
        if (this.seasonSelect) this.seasonSelect.value = currentSeason;

        // Set default week type
        const isWeekend = this.isIsraeliWeekend(now);
        if (this.weekTypeSelect) this.weekTypeSelect.value = isWeekend ? 'weekend' : 'weekday';

        // Set default time of day
        const currentTimeOfDay = this.getCurrentTimeOfDay(now);
        if (this.timeOfDaySelect) this.timeOfDaySelect.value = currentTimeOfDay;
    }

    getCurrentSeason(date) {
        const month = date.getMonth() + 1;
        if (month === 12 || month <= 2) return 'winter';
        if (month >= 3 && month <= 5) return 'spring';
        if (month >= 6 && month <= 8) return 'summer';
        return 'autumn';
    }

    // In JS getDay(): 0=Sunday ... 6=Saturday.
    // כאן weekend מוגדר חמישי-שבת (4–6) כפי שביקשת בעבר.
    isIsraeliWeekend(date) {
        const day = date.getDay();
        return day === 4 || day === 5 || day === 6;
    }

    getCurrentTimeOfDay(date) {
        const hour = date.getHours();
        if (hour >= 5 && hour < 12) return 'morning';
        if (hour >= 12 && hour < 17) return 'afternoon';
        if (hour >= 17 && hour < 21) return 'evening';
        return 'night';
    }

    getHourFromTimeOfDay(timeOfDay) {
        const defaultHours = {
            morning: 8,
            afternoon: 14,
            evening: 20,
            night: 2
        };
        return defaultHours[timeOfDay] || 8;
    }

    // -----------------------------
    // Events
    // -----------------------------
    initializeEventListeners() {
        if (this.searchForm) {
            this.searchForm.addEventListener('submit', (e) => this.handleSearch(e));
        }

        if (this.cityInput) {
            // Clear error messages when user starts typing
            this.cityInput.addEventListener('input', () => {
                if (!this.statusMessage.classList.contains('hidden') && this.statusMessage.classList.contains('error')) {
                    this.hideStatusMessage();
                }
            });

            // Allow Enter key in city input
            this.cityInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.handleSearch(e);
                }
            });
        }

        // Download GPKG button
        if (this.downloadGpkgBtn) {
            this.downloadGpkgBtn.addEventListener('click', () => this.handleDownloadGpkg());
        }
    }

    // -----------------------------
    // Map
    // -----------------------------
    initializeMap() {
        // Create map centered on Israel
        this.map = L.map('map').setView([31.5, 35.0], 8);

        // Add OpenStreetMap tile layer for better street visibility
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19,
            subdomains: ['a', 'b', 'c']
        }).addTo(this.map);
    }

    // -----------------------------
    // Search & Fetch
    // -----------------------------
    buildSearchDate() {
        const timeOfDay = this.timeOfDaySelect?.value || 'morning';
        const weekType = this.weekTypeSelect?.value || 'weekday';
        const hour = this.getHourFromTimeOfDay(timeOfDay);

        // Create a date object representing the search parameters
        let searchDate = new Date();

        // Adjust to correct day of week if needed
        searchDate = this.apply_week_type_to_datetime(searchDate, weekType);

        // Set the hour
        searchDate.setHours(hour, 0, 0, 0);

        return searchDate.toISOString();
    }

    apply_week_type_to_datetime(dt, weekType) {
        const currentIsWeekend = this.isIsraeliWeekend(dt);
        const targetIsWeekend = (weekType === 'weekend');

        if (currentIsWeekend === targetIsWeekend) {
            return dt;
        }

        // Find next appropriate day
        let daysAhead = 0;
        for (let i = 1; i <= 7; i++) {
            const testDate = new Date(dt.getTime() + (i * 24 * 60 * 60 * 1000));
            if (this.isIsraeliWeekend(testDate) === targetIsWeekend) {
                daysAhead = i;
                break;
            }
        }
        return new Date(dt.getTime() + (daysAhead * 24 * 60 * 60 * 1000));
    }

    // async handleSearch(event) {
    //     event.preventDefault();
    //     if (this._inFlight) return;
    //     this._inFlight = true;

    //     const city = (this.cityInput?.value || '').trim();
    //     if (!city) {
    //         this.showStatusMessage('נא הזן שם עיר', 'error');
    //         this._inFlight = false;
    //         return;
    //     }

    //     // Clear any existing error messages
    //     this.hideStatusMessage();

    //     this.setLoading(true);
    //     this.showLoadingOnMap(true);

    //     // Move to location immediately before server request
    //     await this.searchAndMoveToLocation(city);

    //     try {
    //         const predictions = await this.fetchPredictions(city);
    //         this.displayResults(predictions, city);
    //     } catch (error) {
    //         console.error('Prediction error:', error);
    //         this.showStatusMessage(`שגיאה: ${error.message}`, 'error');
    //     } finally {
    //         this.setLoading(false);
    //         this.showLoadingOnMap(false);
    //         this._inFlight = false;
    //     }
    // }

    async handleSearch(event) {
        event.preventDefault();
        if (this._inFlight) return;
        this._inFlight = true;

        const city = (this.cityInput?.value || '').trim();
        if (!city) {
            this.showStatusMessage('נא הזן שם עיר', 'error');
            this._inFlight = false;
            return;
        }

        this.hideStatusMessage();
        this.setLoading(true);
        this.showLoadingOnMap(true);

        // ג׳אוקוד + תזוזה לפני בקשה לשרת
        await this.searchAndMoveToLocation(city);

        try {
            // ניסיון 1: לפי place
            let data = await this.fetchPredictions(city);

            // אם מעט מאוד קצוות – נסה מייד BBox סביב מרכז הג׳אוקוד
            const nEdges = (data?.network_stats?.n_edges ?? (data?.geojson?.features?.length || 0));
            if (nEdges < 50 && this.lastGeocodeCenter) {
            console.warn('[fallback] few edges (', nEdges, ') → trying BBox 3km');
            const fallback = await this.fetchPredictionsByBBox(this.lastGeocodeCenter, 3);
            const n2 = (fallback?.network_stats?.n_edges ?? (fallback?.geojson?.features?.length || 0));
            if ((fallback?.geojson?.features?.length || 0) > (data?.geojson?.features?.length || 0)) {
                data = fallback; // אם ה־fallback טוב יותר, נשתמש בו
                this.showStatusMessage('אזור קטן – הורחב חיפוש ל-3 ק״מ סביב היישוב', 'success');
            }
            // אם גם ה־fallback דל – אפשר לנסות 5 ק״מ
            if (n2 < 50) {
                try {
                const fallback2 = await this.fetchPredictionsByBBox(this.lastGeocodeCenter, 5);
                const n3 = (fallback2?.network_stats?.n_edges ?? (fallback2?.geojson?.features?.length || 0));
                if (n3 > n2) {
                    data = fallback2;
                    this.showStatusMessage('הורחב חיפוש ל-5 ק״מ סביב היישוב', 'success');
                }
                } catch {}
            }
            }

            this.displayResults(data, city);
        } catch (error) {
            console.error('Prediction error:', error);
            this.showStatusMessage(`שגיאה: ${error.message}`, 'error');
        } finally {
            this.setLoading(false);
            this.showLoadingOnMap(false);
            this._inFlight = false;
        }
    }


    showLoadingOnMap(show) {
        if (!this.loadingMessage) return;
        if (show) {
            this.loadingMessage.classList.remove('hidden');
        } else {
            this.loadingMessage.classList.add('hidden');
        }
    }

    // async searchAndMoveToLocation(cityName) {
    //     try {
    //         // Search location using Nominatim
    //         const geocodeUrl = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(cityName)}&limit=1`;
    //         const response = await fetch(geocodeUrl);
    //         const results = await response.json();

    //         if (results && results.length > 0) {
    //             const location = results[0];
    //             const lat = parseFloat(location.lat);
    //             const lon = parseFloat(location.lon);
    //             this.lastGeocodeCenter = { lat, lon };


    //             // Move to location with animation
    //             this.map.flyTo([lat, lon], 13, {
    //                 animate: true,
    //                 duration: 1.5
    //             });

    //             console.log(`Moved to ${cityName}: ${lat}, ${lon}`);
    //         } else {
    //             console.log(`Location not found for: ${cityName}`);
    //         }
    //     } catch (error) {
    //         console.error('Error finding location:', error);
    //     }
    // }

    async searchAndMoveToLocation(cityName) {
        try {
            const base = 'https://nominatim.openstreetmap.org/search';

            // 1) local-first: בתוך תיחום המפה
            const localBox = bboxFromLeafletMap(this.map);
            let results = null;

            if (localBox) {
            const p = new URLSearchParams({
                q: cityName,
                format: 'jsonv2',
                addressdetails: '1',
                'accept-language': 'he,en',
                limit: '5',
                viewbox: localBox.west + ',' + localBox.north + ',' + localBox.east + ',' + localBox.south,
                bounded: '1'
            });
            const urlLocal = base + '?' + p.toString();
            const resp = await fetch(urlLocal);
            results = await resp.json();
            }

            // בחירת מועמד מקומי אם יש
            let loc = pickBestGeocode(results || [], this.lastCountryHint);

            // 2) fallback גלובלי עם מדרוג
            if (!loc) {
            const p2 = new URLSearchParams({
                q: cityName,
                format: 'jsonv2',
                addressdetails: '1',
                'accept-language': 'he,en',
                limit: '8'
            });
            const url2 = base + '?' + p2.toString();
            const resp2 = await fetch(url2);
            const results2 = await resp2.json();
            loc = pickBestGeocode(results2 || [], this.lastCountryHint);
            }

            if (!loc) {
            this.showStatusMessage('לא נמצא מיקום מתאים לחיפוש הזה', 'error');
            return;
            }

            const lat = parseFloat(loc.lat);
            const lon = parseFloat(loc.lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
            this.showStatusMessage('מיקום שהוחזר אינו תקין', 'error');
            return;
            }

            // נשמור country hint (בלי optional chaining)
            const cc = (loc.address && typeof loc.address.country_code === 'string') ? loc.address.country_code : null;
            if (cc) this.lastCountryHint = cc.toLowerCase();

            // מנרמל/מצמצם BBOX לפי הצורך
            const normBBox = normalizeBBoxFromLoc(loc, { lat: lat, lon: lon });
            this.lastGeocodeCenter = { lat: lat, lon: lon };
            this.lastGeocodeBBox = normBBox;

            // תזוזה למקום
            this.map.flyTo([lat, lon], 13, { animate: true, duration: 1.5 });
            console.log('[geocode]', cityName, { lat: lat, lon: lon, bbox: normBBox, country: this.lastCountryHint });
        } catch (err) {
            console.error('Error finding location:', err);
        }
    }




    // async fetchPredictions(city) {
    //     const searchDate = this.buildSearchDate();

    //     const params = new URLSearchParams({
    //         place: city,
    //         date: searchDate
    //     });

    //     // Log search parameters for debugging
    //     console.log('Search parameters:', {
    //         place: city,
    //         season: this.seasonSelect?.value,
    //         weekType: this.weekTypeSelect?.value,
    //         timeOfDay: this.timeOfDaySelect?.value,
    //         hour: this.getHourFromTimeOfDay(this.timeOfDaySelect?.value || 'morning'),
    //         searchDate: searchDate
    //     });

    //     try {
    //         const response = await fetch(`${this.API_BASE_URL}/predict?${params.toString()}`, {
    //             method: 'GET',
    //             headers: { Accept: 'application/json' }
    //         });

    //         if (!response.ok) {
    //             const errorText = await response.text();
    //             console.error('Response error:', errorText);

    //             if (response.status === 404) {
    //                 throw new Error('העיר לא נמצאה. אנא בדוק את השם ונסה שוב');
    //             } else if (response.status === 500) {
    //                 throw new Error('שגיאה בשרת. אנא נסה שוב מאוחר יותר');
    //             } else if (response.status === 503) {
    //                 throw new Error('השירות אינו זמין כרגע');
    //             } else {
    //                 throw new Error(`שגיאת HTTP ${response.status}: ${response.statusText}`);
    //             }
    //         }

    //         const data = await response.json();
    //         console.log('Received data:', data);

    //         // Check if we have geojson in response
    //         if (!data.geojson || !data.geojson.features) {
    //             throw new Error('לא התקבלו נתוני מפה מהשרת');
    //         }

    //         return data;
    //     } catch (error) {
    //         if (error.name === 'TypeError' && error.message.includes('fetch')) {
    //             throw new Error(`לא ניתן להתחבר לשרת. ודא שהשרת רץ על ${this.API_BASE_URL}`);
    //         }
    //         throw error;
    //     }
    // }
    // async fetchPredictions(city) {
    //     const searchDate = this.buildSearchDate();

    //     const timeOfDay = this.timeOfDaySelect?.value || 'morning';
    //     const weekType  = this.weekTypeSelect?.value || 'weekday';
    //     const season    = this.seasonSelect?.value || 'summer';

    //     const params = new URLSearchParams({
    //         place: city,
    //         date: searchDate,
    //         season: season,
    //         week_type: weekType,
    //         time_of_day: timeOfDay
    //     });

    //     const url = `${this.API_BASE_URL}/predict?${params.toString()}`;

    //     const response = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
    //     if (!response.ok) {
    //         const t = await response.text();
    //         throw new Error(`HTTP ${response.status}: ${t}`);
    //     }
    //     const data = await response.json();
    //     if (!data.geojson || !data.geojson.features) throw new Error('לא התקבלו נתוני מפה מהשרת');
    //     return data;
    // }

    // async fetchPredictions(city) {
    //     const date      = this.buildSearchDate();
    //     const timeOfDay = this.timeOfDaySelect?.value || 'morning';
    //     const weekType  = this.weekTypeSelect?.value || 'weekday';
    //     const season    = this.seasonSelect?.value || 'summer';

    //     const params = new URLSearchParams({
    //         date,
    //         season,
    //         week_type: weekType,
    //         time_of_day: timeOfDay
    //     });

    //     // אם יש לנו BBOX מהג׳יאוקוד – נשתמש בו (מונע "קפיצה" לעולם)
    //     if (this.lastGeocodeBBox) {
    //         const { west, south, east, north } = this.lastGeocodeBBox;
    //         params.set('bbox', `${west},${south},${east},${north}`);
    //     } else {
    //         // גיבוי: שליחת place בלבד
    //         params.set('place', city);
    //     }

    //     const url = `${this.API_BASE_URL}/predict?${params.toString()}`;
    //     const response = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
    //     if (!response.ok) {
    //         const t = await response.text();
    //         throw new Error(`HTTP ${response.status}: ${t}`);
    //     }
    //     const data = await response.json();
    //     if (!data.geojson || !data.geojson.features) throw new Error('לא התקבלו נתוני מפה מהשרת');
    //     return data;
    // }

        // ----- fetchPredictions: place תמיד, bbox אופציונלי -----
    async fetchPredictions(city) {
        const date      = this.buildSearchDate();
        const timeOfDay = this.timeOfDaySelect?.value || 'morning';
        const weekType  = this.weekTypeSelect?.value || 'weekday';
        const season    = this.seasonSelect?.value || 'summer';

        const params = new URLSearchParams({
            place: city,               // << תמיד שולחים place
            date,
            season,
            week_type: weekType,
            time_of_day: timeOfDay
        });

        // ברירת מחדל: תמיד לפי שם העיר (place-first)
        params.set('place', city);

        const url = `${this.API_BASE_URL}/predict?${params.toString()}`;
        const response = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
        if (!response.ok) {
            const t = await response.text();
            throw new Error(`HTTP ${response.status}: ${t}`);
        }
        const data = await response.json();
        if (!data.geojson || !data.geojson.features) throw new Error('לא התקבלו נתוני מפה מהשרת');
        return data;
    }
   


    async fetchPredictionsByBBox(center, radiusKm = 3) {
        if (!center || typeof center.lat !== 'number' || typeof center.lon !== 'number') {
            throw new Error('Center for BBox fallback is missing');
        }
        const timeOfDay = this.timeOfDaySelect?.value || 'morning';
        const weekType  = this.weekTypeSelect?.value || 'weekday';
        const season    = this.seasonSelect?.value || 'summer';
        const date      = this.buildSearchDate();

        // Leaflet מספק כלי נוח להמרה לריבוע סביב נקודה
        const bounds = L.latLng(center.lat, center.lon).toBounds(radiusKm * 1000);
        const sw = bounds.getSouthWest();
        const ne = bounds.getNorthEast();
        const bbox = `${sw.lng},${sw.lat},${ne.lng},${ne.lat}`; // west,south,east,north

        const params = new URLSearchParams({
            bbox,
            date,
            season,
            week_type: weekType,
            time_of_day: timeOfDay
        });

        const url = `${this.API_BASE_URL}/predict?${params.toString()}`;
        const resp = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!resp.ok) {
            const t = await resp.text();
            throw new Error(`HTTP ${resp.status}: ${t}`);
        }
        const data = await resp.json();
        if (!data.geojson || !data.geojson.features) {
            throw new Error('לא התקבלו נתוני מפה מהשרת (BBox)');
        }
        return data;
    }




    // -----------------------------
    // Display
    // -----------------------------
    displayResults(data, cityName) {
        // Show details panel
        if (this.detailsPanel) {
            this.detailsPanel.classList.remove('hidden');
        }

        // Extract stats from response
        const numFeatures = data.geojson && data.geojson.features ? data.geojson.features.length : 0;
        const processingTime = data.processing_time || 'לא זמין';
        const networkStats = data.network_stats || { n_edges: numFeatures, n_nodes: 0 };

        // Get current search parameters for display
        const searchParams = this.getCurrentSearchParams();

        // Update map with results
        this.updateMapWithData(data.geojson);

        // Create sample prediction from first feature if not provided
        let samplePrediction = data.sample_prediction;
        if (!samplePrediction && data.geojson.features && data.geojson.features.length > 0) {
            const firstFeature = data.geojson.features[0];
            samplePrediction = {
                volume_bin: firstFeature.properties.volume_bin,
                features: {
                    Hour: firstFeature.properties.Hour,
                    is_weekend: firstFeature.properties.is_weekend,
                    time_of_day: firstFeature.properties.time_of_day,
                    highway: firstFeature.properties.highway,
                    land_use: firstFeature.properties.land_use
                }
            };
        }

        // Update details with search parameters
        this.updatePredictionDetails({
            sample_prediction: samplePrediction,
            network_stats: networkStats,
            processing_time: processingTime,
            validation: data.validation || { warnings: [] },
            search_parameters: data.search_parameters || null,
            search_params: searchParams,
            city_name: cityName
        });

        // Show GPKG download button
        this.showDownloadButton(true);
    }

    getCurrentSearchParams() {
        const hour = this.getHourFromTimeOfDay(this.timeOfDaySelect?.value || 'morning');
        return {
            season: this.seasonSelect?.value,
            weekType: this.weekTypeSelect?.value,
            timeOfDay: this.timeOfDaySelect?.value,
            hour: hour,
            isWeekend: (this.weekTypeSelect?.value === 'weekend')
        };
    }

    updateMapWithData(geojson) {
        // Remove previous layer
        if (this.currentLayer) {
            this.map.removeLayer(this.currentLayer);
        }

        // Add GeoJSON layer with enhanced styling
        this.currentLayer = L.geoJSON(geojson, {
            style: (feature) => this.getFeatureStyle(feature),
            onEachFeature: (feature, layer) => this.bindFeaturePopup(feature, layer)
        }).addTo(this.map);

        // Fit map to bounds with padding
        const bounds = this.currentLayer.getBounds();
        if (bounds.isValid()) {
            this.map.fitBounds(bounds, {
                padding: [50, 50],
                maxZoom: 15
            });
        }
    }

    getFeatureStyle(feature) {
        const volumeBin = feature.properties.volume_bin || 1;

        // Enhanced color scheme
        const colors = {
            1: '#00FF00', // Green
            2: '#FFFF00', // Yellow
            3: '#FFA500', // Orange
            4: '#FF0000', // Red
            5: '#660000'  // Dark Red
        };

        // Dynamic width based on volume
        const widths = {
            1: 2,
            2: 3,
            3: 4,
            4: 5,
            5: 6
        };

        return {
            color: colors[volumeBin] || colors[1],
            weight: widths[volumeBin] || widths[1],
            opacity: 0.85
        };
    }

    updateLegend() {
        const legendContainer = document.getElementById('legendItems');
        if (!legendContainer) return;

        legendContainer.innerHTML = '';

        const labels = {
            1: 'נפח נמוך (1)',
            2: 'נפח בינוני-נמוך (2)',
            3: 'נפח בינוני (3)',
            4: 'נפח גבוה (4)',
            5: 'נפח גבוה מאוד (5)'
        };

        for (let i = 1; i <= 5; i++) {
            const color = this.getFeatureStyle({ properties: { volume_bin: i } }).color;
            const item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `
                <span class="legend-color" style="background-color:${color}"></span>
                <span>${labels[i]}</span>
            `;
            legendContainer.appendChild(item);
        }
    }

    // -----------------------------
    // Popups & Formatting
    // -----------------------------
    bindFeaturePopup(feature, layer) {
        const props = feature.properties;

        const popupContent = `
            <div style="direction: rtl; text-align: right; min-width: 250px;">
                <h3 style="margin: 0 0 10px 0; color: #333;">
                    ${props.name || 'רחוב ללא שם'}
                </h3>

                <div style="background: ${this.getFeatureStyle(feature).color};
                            color: white; padding: 8px; border-radius: 6px; margin-bottom: 10px;
                            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
                    <strong>נפח חזוי: </strong>
                    <span style="font-size: 1.2em; font-weight: bold;">
                        ${props.volume_bin ?? 'לא ידוע'}
                    </span>
                </div>

                <div style="background: #f8f9fa; padding: 10px; border-radius: 6px;">
                    <p style="margin: 5px 0;"><strong>סוג רחוב:</strong> ${this.translateHighway(props.highway) || 'לא ידוע'}</p>
                    <p style="margin: 5px 0;"><strong>שימוש קרקע:</strong> ${this.translateLandUse(props.land_use) || 'לא ידוע'}</p>

                    <hr style="margin: 10px 0; border: none; border-top: 1px solid #dee2e6;">

                    <div style="font-size: 0.9em;">
                        <p style="margin: 3px 0;"><strong>הסתברויות:</strong></p>
                        ${this.formatProbabilities(props)}
                    </div>

                    <hr style="margin: 10px 0; border: none; border-top: 1px solid #dee2e6;">

                    <div style="font-size: 0.85em; color: #666;">
                        <p style="margin: 3px 0;"><strong>Betweenness:</strong> ${props.betweenness ? props.betweenness.toFixed(5) : 'לא ידוע'}</p>
                        <p style="margin: 3px 0;"><strong>Closeness:</strong> ${props.closeness ? props.closeness.toFixed(5) : 'לא ידוע'}</p>
                    </div>
                </div>

                ${props.osmid ? `<p style="font-size: 0.8em; color: #999; margin-top: 8px;">OSM ID: ${props.osmid}</p>` : ''}
            </div>
        `;

        layer.bindPopup(popupContent, {
            maxWidth: 350,
            className: 'custom-popup',
            autoPan: true,
            autoPanPaddingTopLeft: [50, 50],
            autoPanPaddingBottomRight: [50, 50]
        });

        // Center map on popup when opened
        layer.on('popupopen', (e) => {
            const popup = e.popup;
            const px = this.map.project(popup.getLatLng());
            px.y -= popup._container.clientHeight / 2;
            this.map.panTo(this.map.unproject(px), { animate: true });
        });
    }

    formatProbabilities(props) {
        let html = '<div style="margin-top: 5px;">';
        for (let i = 1; i <= 5; i++) {
            const prob = props[`proba_${i}`];
            if (prob !== undefined) {
                const percentage = (parseFloat(prob) * 100).toFixed(1);
                const barWidth = percentage;
                html += `
                    <div style="display: flex; align-items: center; margin: 2px 0;">
                        <span style="width: 20px;">${i}:</span>
                        <div style="flex: 1; background: #e9ecef; height: 14px; border-radius: 7px; margin: 0 5px; position: relative;">
                            <div style="background: ${this.getFeatureStyle({ properties: { volume_bin: i } }).color};
                                        width: ${barWidth}%; height: 100%; border-radius: 7px;"></div>
                        </div>
                        <span style="width: 45px; text-align: left; font-size: 0.85em;">${percentage}%</span>
                    </div>
                `;
            }
        }
        html += '</div>';
        return html;
    }

    formatProb(val) {
        const n = Number(val);
        return Number.isFinite(n) ? n.toFixed(5) : 'לא ידוע';
    }

    translateHighway(highway) {
        const translations = {
            primary: 'כביש ראשי',
            secondary: 'כביש משני',
            tertiary: 'כביש שלישוני',
            residential: 'רחוב מגורים',
            footway: 'שביל הולכי רגל',
            path: 'שביל',
            pedestrian: 'אזור הולכי רגל',
            living_street: 'רחוב מגורים שקט',
            unclassified: 'לא מסווג',
            service: 'דרך שירות'
        };
        return translations[highway] || highway;
    }

    translateLandUse(landUse) {
        const translations = {
            residential: 'מגורים',
            commercial: 'מסחרי',
            retail: 'קמעונאי',
            industrial: 'תעשייתי',
            other: 'אחר'
        };
        return translations[landUse] || landUse;
    }

    translateSeason(season) {
        const translations = {
            winter: 'חורף',
            spring: 'אביב',
            summer: 'קיץ',
            autumn: 'סתיו'
        };
        return translations[season] || season;
    }

    translateWeekType(weekType) {
        const translations = {
            weekday: 'אמצע שבוע',
            weekend: 'סוף שבוע'
        };
        return translations[weekType] || weekType;
    }

    translateTimeOfDay(timeOfDay) {
        const translations = {
            morning: 'בוקר',
            afternoon: 'אחר צהריים',
            evening: 'ערב',
            night: 'לילה'
        };
        return translations[timeOfDay] || timeOfDay;
    }

    updatePredictionDetails(data) {
        const sample = data.sample_prediction;
        const stats = data.network_stats || {};
        // const searchParams = data.search_parameters || {};

        // נעדיף את אובייקט השרת ואם חסר – נשתמש במה שבא מה-UI, עם נרמול שמות
        const spSrv = data.search_parameters || null;
        const spCli = data.search_params || {};
        const searchParams = spSrv ? {
            season: spSrv.season,
            weekType: spSrv.week_type,
            timeOfDay: spSrv.time_of_day
        } : spCli;

        if (!this.predictionDetails) return;

        this.predictionDetails.innerHTML = `
            <div class="detail-item">
                <div class="detail-label">עיר</div>
                <div class="detail-value highlight">${data.city_name || 'לא ידוע'}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">נפח חזוי לדוגמה</div>
                <div class="detail-value highlight">${sample?.volume_bin ?? 'N/A'}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">עונה</div>
                <div class="detail-value">${this.translateSeason(searchParams.season)}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">זמן בשבוע</div>
                <div class="detail-value">${this.translateWeekType(searchParams.weekType)}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">זמן ביום</div>
                <div class="detail-value">${this.translateTimeOfDay(searchParams.timeOfDay)}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">מספר רחובות</div>
                <div class="detail-value">${stats.n_edges || 0}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">מספר צמתים</div>
                <div class="detail-value">${stats.n_nodes || 0}</div>
            </div>

            <div class="detail-item">
                <div class="detail-label">זמן עיבוד</div>
                <div class="detail-value">${data.processing_time ?? 'לא זמין'}s</div>
            </div>

            ${data.validation?.warnings?.length > 0 ? `
                <div class="detail-item">
                    <div class="detail-label">אזהרות</div>
                    <div class="detail-value">${data.validation.warnings.join(', ')}</div>
                </div>
            ` : ''}
        `;
    }

    // -----------------------------
    // Status & Buttons
    // -----------------------------
    setLoading(loading) {
        if (this.searchBtn) this.searchBtn.disabled = loading;
        if (this.cityInput) this.cityInput.disabled = loading;

        // Disable all parameter inputs during loading
        if (this.seasonSelect) this.seasonSelect.disabled = loading;
        if (this.weekTypeSelect) this.weekTypeSelect.disabled = loading;
        if (this.timeOfDaySelect) this.timeOfDaySelect.disabled = loading;

        if (loading) {
            this.buttonText?.classList.add('hidden');
            this.loadingSpinner?.classList.remove('hidden');
        } else {
            this.buttonText?.classList.remove('hidden');
            this.loadingSpinner?.classList.add('hidden');
        }
    }

    showStatusMessage(message, type = 'info') {
        if (!this.statusMessage) return;
        this.statusMessage.textContent = message;
        this.statusMessage.className = `status-message ${type}`;
        this.statusMessage.classList.remove('hidden');

        // Auto-hide success messages
        if (type === 'success') {
            setTimeout(() => this.hideStatusMessage(), 3000);
        }
    }

    hideStatusMessage() {
        if (!this.statusMessage) return;
        this.statusMessage.classList.add('hidden');
    }

    // async handleDownloadGpkg() {
    //     const city = (this.cityInput?.value || '').trim();
    //     if (!city) {
    //         this.showStatusMessage('אנא הזן שם עיר תחילה', 'error');
    //         return;
    //     }

    //     this.setDownloadLoading(true);

    //     try {
    //         const searchDate = this.buildSearchDate();
    //         const url = new URL(`${this.API_BASE_URL}/predict-gpkg`);
    //         url.searchParams.set('place', city);
    //         url.searchParams.set('date', searchDate);

    //         // Open download in new tab
    //         window.open(url.toString(), '_blank');

    //         this.showStatusMessage('הורדת קובץ GPKG החלה!', 'success');
    //     } catch (error) {
    //         console.error('Download error:', error);
    //         this.showStatusMessage(`שגיאה בהורדת קובץ GPKG: ${error.message}`, 'error');
    //     } finally {
    //         this.setDownloadLoading(false);
    //     }
    // }

    // async handleDownloadGpkg() {
    //     const city = (this.cityInput?.value || '').trim();
    //     if (!city) { this.showStatusMessage('אנא הזן שם עיר תחילה', 'error'); return; }

    //     this.setDownloadLoading(true);
    //     try {
    //         const date      = this.buildSearchDate();
    //         const timeOfDay = this.timeOfDaySelect?.value || 'morning';
    //         const weekType  = this.weekTypeSelect?.value || 'weekday';
    //         const season    = this.seasonSelect?.value || 'summer';

    //         const params = new URLSearchParams({
    //         date,
    //         season,
    //         week_type: weekType,
    //         time_of_day: timeOfDay
    //         });

    //         if (this.lastGeocodeBBox) {
    //         const { west, south, east, north } = this.lastGeocodeBBox;
    //         params.set('bbox', `${west},${south},${east},${north}`);
    //         } else {
    //         params.set('place', city);
    //         }

    //         const url = `${this.API_BASE_URL}/predict-gpkg?${params.toString()}`;
    //         window.open(url, '_blank');
    //         this.showStatusMessage('הורדת קובץ GPKG החלה!', 'success');
    //     } catch (error) {
    //         console.error('Download error:', error);
    //         this.showStatusMessage(`שגיאה בהורדת קובץ GPKG: ${error.message}`, 'error');
    //     } finally {
    //         this.setDownloadLoading(false);
    //     }
    // }

        // ----- handleDownloadGpkg: place תמיד, bbox אופציונלי -----
    async handleDownloadGpkg() {
        const city = (this.cityInput?.value || '').trim();
        if (!city) { this.showStatusMessage('אנא הזן שם עיר תחילה', 'error'); return; }

        this.setDownloadLoading(true);
        try {
            const date      = this.buildSearchDate();
            const timeOfDay = this.timeOfDaySelect?.value || 'morning';
            const weekType  = this.weekTypeSelect?.value || 'weekday';
            const season    = this.seasonSelect?.value || 'summer';

            const params = new URLSearchParams({
            place: city,             // << תמיד שולחים place
            date,
            season,
            week_type: weekType,
            time_of_day: timeOfDay
            });

            // if (this.lastGeocodeBBox) {
            // const { west, south, east, north } = this.lastGeocodeBBox;
            // params.set('bbox', `${west},${south},${east},${north}`);
            // }
            // ברירת מחדל: קובץ לפי שם העיר; אם תרצה כפתור/מצב "BBox" – נוסיף בהמשך.
            params.set('place', city);

            const url = `${this.API_BASE_URL}/predict-gpkg?${params.toString()}`;
            // הורדה באותה לשונית (לא פותח כרטיסייה חדשה)
            window.location.href = url;
            this.showStatusMessage('הורדת קובץ GPKG החלה!', 'success');
        } catch (error) {
            console.error('Download error:', error);
            this.showStatusMessage(`שגיאה בהורדת קובץ GPKG: ${error.message}`, 'error');
        } finally {
            this.setDownloadLoading(false);
        }
    }



    setDownloadLoading(loading) {
        if (!this.downloadGpkgBtn) return;
        this.downloadGpkgBtn.disabled = loading;

        if (loading) {
            this.downloadBtnText?.classList.add('hidden');
            this.downloadLoadingSpinner?.classList.remove('hidden');
        } else {
            this.downloadBtnText?.classList.remove('hidden');
            this.downloadLoadingSpinner?.classList.add('hidden');
        }
    }

    showDownloadButton(show = true) {
        if (!this.downloadGpkgBtn) return;
        if (show) {
            this.downloadGpkgBtn.classList.remove('invisible');
        } else {
            this.downloadGpkgBtn.classList.add('invisible');
        }
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // eslint-disable-next-line no-unused-vars
    const app = new PedestrianPredictionApp();
});
