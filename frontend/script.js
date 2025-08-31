// script.js

class PedestrianPredictionApp {
    constructor() {
        this.API_BASE_URL = 'http://127.0.0.1:8000';
        this.map = null;
        this.currentLayer = null;
        
        this.initializeElements();
        this.setDefaultSearchParameters();
        this.initializeEventListeners();
        this.initializeMap();
        this.updateLegend();
    }
    
    initializeElements() {
        this.searchForm = document.getElementById('searchForm');
        this.cityInput = document.getElementById('cityInput');
        this.searchBtn = document.getElementById('searchBtn');
        this.buttonText = document.getElementById('buttonText');
        this.loadingSpinner = document.getElementById('loadingSpinner');
        this.statusMessage = document.getElementById('statusMessage');
        this.mapContainer = document.getElementById('mapContainer');
        this.mapTitle = document.getElementById('mapTitle');
        this.mapStats = document.getElementById('mapStats');
        this.loadingMessage = document.getElementById('loadingMessage');
        this.detailsContainer = document.getElementById('detailsContainer');
        this.predictionDetails = document.getElementById('predictionDetails');
        
        // Download GPKG button elements
        this.downloadGpkgBtn = document.getElementById('downloadGpkgBtn');
        this.downloadBtnText = document.getElementById('downloadBtnText');
        this.downloadLoadingSpinner = document.getElementById('downloadLoadingSpinner');
        
        // New search parameter elements
        this.seasonSelect = document.getElementById('seasonSelect');
        this.weekTypeSelect = document.getElementById('weekTypeSelect');
        this.timeOfDaySelect = document.getElementById('timeOfDaySelect');
    }
    
    setDefaultSearchParameters() {
        const now = new Date();
        
        // Set default season based on Israeli seasons
        const currentSeason = this.getCurrentSeason(now);
        this.seasonSelect.value = currentSeason;
        
        // Set default week type (weekend includes Thursday, Friday, Saturday)
        const isWeekend = this.isIsraeliWeekend(now);
        this.weekTypeSelect.value = isWeekend ? 'weekend' : 'weekday';
        
        // Set default time of day
        const currentTimeOfDay = this.getCurrentTimeOfDay(now);
        this.timeOfDaySelect.value = currentTimeOfDay;
    }
    
    getCurrentSeason(date) {
        const month = date.getMonth() + 1; // getMonth() returns 0-11
        
        // Israeli seasons (roughly):
        // Winter: December, January, February
        // Spring: March, April, May
        // Summer: June, July, August
        // Autumn: September, October, November
        if (month === 12 || month <= 2) {
            return 'winter';
        } else if (month >= 3 && month <= 5) {
            return 'spring';
        } else if (month >= 6 && month <= 8) {
            return 'summer';
        } else {
            return 'autumn';
        }
    }
    
    isIsraeliWeekend(date) {
        const day = date.getDay(); // 0 = Sunday, 1 = Monday, ..., 6 = Saturday
        // Israeli weekend: Thursday (4), Friday (5), Saturday (6)
        return day === 4 || day === 5 || day === 6;
    }
    
    getCurrentTimeOfDay(date) {
        const hour = date.getHours();
        
        if (hour >= 5 && hour < 12) {
            return 'morning';
        } else if (hour >= 12 && hour < 17) {
            return 'afternoon';
        } else if (hour >= 17 && hour < 21) {
            return 'evening';
        } else {
            return 'night';
        }
    }
    
    getHourFromTimeOfDay(timeOfDay) {
        // Return typical hour for each time period
        const defaultHours = {
            'morning': 8,
            'afternoon': 14,
            'evening': 20,
            'night': 2
        };
        
        return defaultHours[timeOfDay] || 8;
    }
    
    initializeEventListeners() {
        this.searchForm.addEventListener('submit', (e) => this.handleSearch(e));
        
        // Clear error messages when user starts typing
        this.cityInput.addEventListener('input', () => {
            if (!this.statusMessage.classList.contains('hidden') && 
                this.statusMessage.classList.contains('error')) {
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
        
        // Download GPKG button
        if (this.downloadGpkgBtn) {
            this.downloadGpkgBtn.addEventListener('click', () => this.handleDownloadGpkg());
        }
    }
    
    initializeMap() {
        // Create map with default view (Israel as default)
        this.map = L.map('map').setView([31.5, 35.0], 8);
        
        // Add tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);
    }
    
    apply_week_type_to_datetime(dt, week_type) {
        "Adjust datetime to represent weekday or weekend."
        const current_is_weekend = this.isIsraeliWeekend(dt);
        const target_is_weekend = (week_type === 'weekend');
        
        if (current_is_weekend === target_is_weekend) {
            return dt;
        }
        
        // Find next appropriate day
        let days_ahead = 0;
        for (let i = 1; i <= 7; i++) {
            const test_date = new Date(dt.getTime() + (i * 24 * 60 * 60 * 1000));
            if (this.isIsraeliWeekend(test_date) === target_is_weekend) {
                days_ahead = i;
                break;
            }
        }
        
        return new Date(dt.getTime() + (days_ahead * 24 * 60 * 60 * 1000));
    }
    
    initializeMap() {
        // Create map with default view (Israel as default)
        this.map = L.map('map').setView([31.5, 35.0], 8);
        
        // Add tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);
    }
    
    buildSearchDate() {
        const season = this.seasonSelect.value;
        const weekType = this.weekTypeSelect.value;
        const timeOfDay = this.timeOfDaySelect.value;
        
        const hour = this.getHourFromTimeOfDay(timeOfDay);
        const isWeekend = weekType === 'weekend';
        
        // Create a date object representing the search parameters
        let searchDate = new Date();
        
        // Adjust to correct day of week if needed
        searchDate = this.apply_week_type_to_datetime(searchDate, weekType);
        
        // Set the hour
        searchDate.setHours(hour, 0, 0, 0);
        
        return searchDate.toISOString();
    }

    async handleSearch(event) {
        event.preventDefault();
        if (this._inFlight) return;
        this._inFlight = true;
        
        const city = this.cityInput.value.trim();
        if (!city) {
            this.showStatusMessage('אנא הזן שם עיר', 'error');
            this._inFlight = false;
            return;
        }
        
        // Clear any existing error messages
        this.hideStatusMessage();
        
        this.setLoading(true);
        this.showLoadingOnMap(true);
        
        // זוז למיקום מיד לפני הבקשה לשרת
        await this.searchAndMoveToLocation(city);
        
        try {
            const predictions = await this.fetchPredictions(city);
            this.displayResults(predictions, city);
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
        if (show) {
            this.loadingMessage.classList.remove('hidden');
            this.mapTitle.textContent = 'מפת רחובות';
            this.mapStats.innerHTML = '';
        } else {
            this.loadingMessage.classList.add('hidden');
        }
    }
    
    async searchAndMoveToLocation(cityName) {
        try {
            // חיפוש מיקום באמצעות Nominatim
            const geocodeUrl = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(cityName)}&limit=1`;
            
            const response = await fetch(geocodeUrl);
            const results = await response.json();
            
            if (results && results.length > 0) {
                const location = results[0];
                const lat = parseFloat(location.lat);
                const lon = parseFloat(location.lon);
                
                // זוז למיקום מיד
                this.map.setView([lat, lon], 12, { animate: true });
                
                console.log(`Moved to ${cityName}: ${lat}, ${lon}`);
            } else {
                console.log(`Location not found for: ${cityName}`);
            }
        } catch (error) {
            console.error('Error finding location:', error);
            // אם החיפוש נכשל, לא נעשה כלום - המפה תישאר במיקום הנוכחי
        }
    }
    
    async fetchPredictions(city) {
        const searchDate = this.buildSearchDate();
        
        const params = new URLSearchParams({
            place: city,
            date: searchDate
        });
        
        // Log search parameters for debugging
        console.log('Search parameters:', {
            place: city,
            season: this.seasonSelect.value,
            weekType: this.weekTypeSelect.value,
            timeOfDay: this.timeOfDaySelect.value,
            hour: this.getHourFromTimeOfDay(this.timeOfDaySelect.value),
            searchDate: searchDate
        });
        
        try {
            const response = await fetch(`${this.API_BASE_URL}/predict?${params.toString()}`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Response error:', errorText);
                
                if (response.status === 404) {
                    throw new Error('העיר לא נמצאה. אנא בדוק את השם ונסה שוב');
                } else if (response.status === 500) {
                    throw new Error('שגיאה בשרת. אנא נסה שוב מאוחר יותר');
                } else if (response.status === 503) {
                    throw new Error('השירות אינו זמין כרגע');
                } else {
                    throw new Error(`שגיאת HTTP ${response.status}: ${response.statusText}`);
                }
            }
            
            const data = await response.json();
            console.log('Received data:', data);
            
            // בדוק אם יש geojson בתשובה
            if (!data.geojson || !data.geojson.features) {
                throw new Error('לא התקבלו נתוני מפה מהשרת');
            }
            
            return data;
            
        } catch (error) {
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                throw new Error('לא ניתן להתחבר לשרת. ודא שהשרת רץ על http://127.0.0.1:8000');
            }
            throw error;
        }
    }
    
    displayResults(data, cityName) {
        // Show details container
        this.detailsContainer.classList.remove('hidden');
        
        // Extract stats from response
        const numFeatures = data.geojson && data.geojson.features ? data.geojson.features.length : 0;
        const processingTime = data.processing_time || 'לא זמין';
        const networkStats = data.network_stats || { n_edges: numFeatures, n_nodes: 0 };
        
        // Get current search parameters for display
        const searchParams = this.getCurrentSearchParams();
        
        // Update title and stats
        this.mapTitle.textContent = `תחזית נפח הולכי רגל - ${cityName}`;
        this.mapStats.innerHTML = `
            <span>מספר רחובות: ${networkStats.n_edges}</span>
            <span>זמן עיבוד: ${processingTime}s</span>
        `;
        
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
            search_params: searchParams
        });
        
        // Show GPKG download button
        this.showDownloadButton(true);
        
        // Scroll to results
        this.mapContainer.scrollIntoView({ behavior: 'smooth' });
    }
    
    getCurrentSearchParams() {
        const hour = this.getHourFromTimeOfDay(this.timeOfDaySelect.value);
        
        return {
            season: this.seasonSelect.value,
            weekType: this.weekTypeSelect.value,
            timeOfDay: this.timeOfDaySelect.value,
            hour: hour,
            isWeekend: this.weekTypeSelect.value === 'weekend'
        };
    }
    
    updateMapWithData(geojson) {
        // Remove previous layer
        if (this.currentLayer) {
            this.map.removeLayer(this.currentLayer);
        }
        
        // Add GeoJSON layer
        this.currentLayer = L.geoJSON(geojson, {
            style: (feature) => this.getFeatureStyle(feature),
            onEachFeature: (feature, layer) => this.bindFeaturePopup(feature, layer)
        }).addTo(this.map);
        
        // Fit map to bounds
        if (this.currentLayer.getBounds().isValid()) {
            this.map.fitBounds(this.currentLayer.getBounds(), { padding: [20, 20] });
        }
    }
    
    getFeatureStyle(feature) {
        const volumeBin = feature.properties.volume_bin || 1;
        
        // Color scheme based on volume bin
        const colors = {
            1: '#00FF00',
            2: '#FFFF00',
            3: '#FFA500',
            4: '#FF0000',
            5: '#660000'
        };
        
        // Width based on volume bin
        const widths = {
            1: 2,
            2: 2.5,
            3: 3,
            4: 3.5,
            5: 4
        };
        
        return {
            color: colors[volumeBin] || colors[1],
            weight: widths[volumeBin] || widths[1],
            opacity: 0.8
        };
    }
    
    updateLegend() {
        const legendContainer = document.getElementById('legendItems');
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
    
    bindFeaturePopup(feature, layer) {
        const props = feature.properties;
        
        const popupContent = `
            <div style="direction: rtl; text-align: right;">
                <h3>פרטי רחוב</h3>

                <p><span style="color: ${this.getFeatureStyle(feature).color}; font-weight: bold;">נפח חזוי: ${props.volume_bin || 'N/A'}</span></p>
                <p><strong>סוג רחוב:</strong> ${this.translateHighway(props.highway) || 'לא ידוע'}</p>
                <p><strong>שימוש קרקע:</strong> ${this.translateLandUse(props.land_use) || 'לא ידוע'}</p>
                <p><strong>הסתברות התאמה לנפח נמוך:</strong> ${props.proba_1?.toFixed(5) || 'לא ידוע'}</p>
                <p><strong>הסתברות התאמה לנפח בינוני-נמוך:</strong> ${props.proba_2?.toFixed(5) || 'לא ידוע'}</p>
                <p><strong>הסתברות התאמה לנפח בינוני:</strong> ${props.proba_3?.toFixed(5) || 'לא ידוע'}</p>
                <p><strong>הסתברות התאמה לנפח גבוה:</strong> ${props.proba_4?.toFixed(5) || 'לא ידוע'}</p>
                <p><strong>הסתברות התאמה לנפח גבוה מאוד:</strong> ${props.proba_5?.toFixed(5) || 'לא ידוע'}</p>
                <p><strong>Betweenness:</strong> ${props.betweenness || 'לא ידוע'}</p>
                <p><strong>Closeness:</strong> ${props.closeness || 'לא ידוע'}</p>
                ${props.osmid ? `<p><strong>מזהה OSM:</strong> ${props.osmid}</p>` : ''}
            </div>
        `;
        
        layer.bindPopup(popupContent);
    }
    
    translateHighway(highway) {
        const translations = {
            'primary': 'כביש ראשי',
            'secondary': 'כביש משני', 
            'tertiary': 'כביש שלישוני',
            'residential': 'רחוב מגורים',
            'footway': 'שביל הולכי רגל',
            'path': 'שביל',
            'pedestrian': 'אזור הולכי רגל',
            'living_street': 'רחוב מגורים שקט',
            'unclassified': 'לא מסווג',
            'service': 'דרך שירות'
        };
        return translations[highway] || highway;
    }
    
    translateLandUse(landUse) {
        const translations = {
            'residential': 'מגורים',
            'commercial': 'מסחרי',
            'retail': 'קמעונאי',
            'industrial': 'תעשייתי',
            'other': 'אחר'
        };
        return translations[landUse] || landUse;
    }
    
    translateSeason(season) {
        const translations = {
            'winter': 'חורף',
            'spring': 'אביב',
            'summer': 'קיץ',
            'autumn': 'סתיו'
        };
        return translations[season] || season;
    }
    
    translateWeekType(weekType) {
        const translations = {
            'weekday': 'אמצע שבוע',
            'weekend': 'סוף שבוע'
        };
        return translations[weekType] || weekType;
    }
    
    updatePredictionDetails(data) {
        const sample = data.sample_prediction;
        const features = sample?.features || {};
        const stats = data.network_stats;
        const searchParams = data.search_params || {};
        
        this.predictionDetails.innerHTML = `
            <div class="detail-item">
                <div class="detail-label">נפח חזוי לדוגמה</div>
                <div class="detail-value highlight">${sample?.volume_bin || 'N/A'}</div>
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
                <div class="detail-value">${data.processing_time}s</div>
            </div>
            
            ${data.validation?.warnings?.length > 0 ? `
                <div class="detail-item">
                    <div class="detail-label">אזהרות</div>
                    <div class="detail-value">${data.validation.warnings.join(', ')}</div>
                </div>
            ` : ''}
        `;
    }
    
    translateTimeOfDay(timeOfDay) {
        const translations = {
            'morning': 'בוקר',
            'afternoon': 'אחר צהריים', 
            'evening': 'ערב',
            'night': 'לילה'
        };
        return translations[timeOfDay] || timeOfDay;
    }
    
    setLoading(loading) {
        this.searchBtn.disabled = loading;
        this.cityInput.disabled = loading;
        
        // Disable all parameter inputs during loading
        this.seasonSelect.disabled = loading;
        this.weekTypeSelect.disabled = loading;
        this.timeOfDaySelect.disabled = loading;
        
        if (loading) {
            this.buttonText.classList.add('hidden');
            this.loadingSpinner.classList.remove('hidden');
        } else {
            this.buttonText.classList.remove('hidden');
            this.loadingSpinner.classList.add('hidden');
        }
    }
    
    showStatusMessage(message, type = 'info') {
        this.statusMessage.textContent = message;
        this.statusMessage.className = `status-message ${type}`;
        this.statusMessage.classList.remove('hidden');
        
        // Only auto-hide success messages, keep error messages until user action
        if (type === 'success') {
            setTimeout(() => {
                this.hideStatusMessage();
            }, 3000);
        }
    }
    
    hideStatusMessage() {
        this.statusMessage.classList.add('hidden');
    }
    
    async handleDownloadGpkg() {
        const city = this.cityInput.value.trim();
        if (!city) {
            this.showStatusMessage('אנא הזן שם עיר תחילה', 'error');
            return;
        }
        
        this.setDownloadLoading(true);
        
        try {
            const searchDate = this.buildSearchDate();
            
            const url = new URL(`${this.API_BASE_URL}/predict-gpkg`);
            url.searchParams.set('place', city);
            url.searchParams.set('date', searchDate);
            
            // Open download in new tab
            window.open(url.toString(), '_blank');
            
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
            this.downloadBtnText.classList.add('hidden');
            this.downloadLoadingSpinner.classList.remove('hidden');
        } else {
            this.downloadBtnText.classList.remove('hidden');
            this.downloadLoadingSpinner.classList.add('hidden');
        }
    }
    
    showDownloadButton(show = true) {
        if (!this.downloadGpkgBtn) return;
        
        if (show) {
            this.downloadGpkgBtn.classList.remove('hidden');
        } else {
            this.downloadGpkgBtn.classList.add('hidden');
        }
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    const app = new PedestrianPredictionApp();
});