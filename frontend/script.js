// script.js - Pedestrian Volume Prediction Application with Enhanced Features

/**
 * Main application class for pedestrian volume prediction
 * Manages the entire application lifecycle including map, UI, and data
 */
class PedestrianPredictionApp {
	constructor() {
		this.API_BASE_URL = window.API_BASE || "http://127.0.0.1:8000";
		console.log("[PedestrianPredictionApp] Using API:", this.API_BASE_URL);

		// Application state
		this.map = null;
		this.currentLayers = {}; // Store multiple layers
		this.currentLayerName = null; // Currently visible layer
		this.allLayersData = []; // Store all layers from server
		this.drawnBbox = null; // Store drawn bbox
		this.selectedFile = null;
		this.isProcessing = false;
		this.currentGpkgBlob = null;

		// Progress tracking
		this.totalRequests = 32; // 4 seasons * 2 week types * 4 times of day
		this.completedRequests = 0;
		this.progressInterval = null;

		// Initialize components
		this.initializeElements();
		this.initializeEventListeners();
		this.initializeMap();
		this.initializeLegend();
		this.initializeDetailsPanel();
	}

	/**
	 * Initialize all DOM element references
	 */
	initializeElements() {
		// Panel elements
		this.searchPanel = document.getElementById("searchPanel");
		this.panelCollapseBtn = document.getElementById("panelCollapseBtn");

		// City search elements
		this.citySearchInput = document.getElementById("citySearchInput");
		this.searchCityBtn = document.getElementById("searchCityBtn");
		this.searchCityBtnText = document.getElementById("searchCityBtnText");
		this.searchCitySpinner = document.getElementById("searchCitySpinner");

		// GPKG upload elements
		this.gpkgFileInput = document.getElementById("gpkgFileInput");
		this.uploadGpkgBtn = document.getElementById("uploadGpkgBtn");
		this.uploadGpkgBtnText = document.getElementById("uploadGpkgBtnText");
		this.uploadGpkgSpinner = document.getElementById("uploadGpkgSpinner");

		// Local navigation and bbox elements
		this.findCityBtn = document.getElementById("findCityBtn");
		this.drawBboxBtn = document.getElementById("drawBboxBtn");
		this.clearBboxBtn = document.getElementById("clearBboxBtn");
		this.sendBboxBtn = document.getElementById("sendBboxBtn");
		this.sendBboxBtnText = document.getElementById("sendBboxBtnText");
		this.sendBboxSpinner = document.getElementById("sendBboxSpinner");

		// Progress section
		this.progressSection = document.getElementById("progressSection");
		this.progressBar = document.getElementById("progressBar");
		this.progressText = document.getElementById("progressText");

		// Layer selection elements
		this.layerSelectionSection = document.getElementById(
			"layerSelectionSection"
		);
		this.layerButtonsContainer = document.getElementById(
			"layerButtonsContainer"
		);
		this.clearLayersBtn = document.getElementById("clearLayersBtn");

		// Download elements
		this.downloadSection = document.getElementById("downloadSection");
		this.downloadGpkgBtn = document.getElementById("downloadGpkgBtn");
		this.downloadBtnText = document.getElementById("downloadBtnText");
		this.downloadSpinner = document.getElementById("downloadSpinner");

		// Weather summary elements
		this.weatherSummarySection = document.getElementById("weatherSummarySection");
		this.weatherSummaryContent = document.getElementById("weatherSummaryContent");

		// Status and details
		this.statusMessage = document.getElementById("statusMessage");
		this.detailsPanel = document.getElementById("detailsPanel");
		this.cityName = document.getElementById("cityName");
		this.streetCount = document.getElementById("streetCount");
		this.layerName = document.getElementById("layerName");
	}

	/**
	 * Initialize all event listeners for UI interactions
	 */
	initializeEventListeners() {
		// Panel collapse/expand
		this.panelCollapseBtn.addEventListener("click", () =>
			this.togglePanelCollapse()
		);

		// City search
		this.searchCityBtn.addEventListener("click", () =>
			this.handleCitySearchAndSendToServerForPredictions()
		);
		this.citySearchInput.addEventListener("keypress", (e) => {
			if (e.key === "Enter")
				this.handleCitySearchAndSendToServerForPredictions();
		});

		// GPKG upload
		this.gpkgFileInput.addEventListener("change", () =>
			this.handleFileSelection()
		);
		this.uploadGpkgBtn.addEventListener("click", () =>
			this.handleGpkgUpload()
		);

		// Local navigation and bbox
		this.findCityBtn.addEventListener("click", () => this.handleFindCity());
		this.drawBboxBtn.addEventListener("click", () =>
			this.enableBboxDrawing()
		);
		this.clearBboxBtn.addEventListener("click", () => this.clearBbox());
		this.sendBboxBtn.addEventListener("click", () => this.handleSendBbox());

		// Download
		this.downloadGpkgBtn.addEventListener("click", () =>
			this.handleDownloadGpkg()
		);

		// Clear layers
		this.clearLayersBtn.addEventListener("click", () =>
			this.handleClearLayers()
		);

		// Details panel is now always visible when there's data
	}

	/**
	 * Initialize Leaflet map with Israeli coordinates
	 */
	initializeMap() {
		// Create map centered on Israel
		this.map = L.map("map").setView([31.5, 35.0], 8);

		// Add OpenStreetMap tile layer
		L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
			attribution:
				'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
			maxZoom: 19,
			subdomains: ["a", "b", "c"],
		}).addTo(this.map);

		// Initialize drawing tools
		this.initializeDrawingTools();
	}

	/**
	 * Initialize Leaflet Draw plugin for bbox selection
	 */
	initializeDrawingTools() {
		// Create FeatureGroup for drawn items
		this.drawnItems = new L.FeatureGroup();
		this.map.addLayer(this.drawnItems);

		// Create draw control (initially disabled)
		this.drawControl = new L.Control.Draw({
			draw: {
				polygon: false,
				polyline: false,
				circle: false,
				marker: false,
				circlemarker: false,
				rectangle: false, // Will enable programmatically
			},
			edit: {
				featureGroup: this.drawnItems,
				edit: false,
				remove: false,
			},
		});
	}

	/**
	 * Initialize legend for volume predictions
	 */
	initializeLegend() {
		const legendContainer = document.getElementById("legendItems");
		if (!legendContainer) return;

		const labels = {
			1: "נפח נמוך מאוד (1)",
			2: "נפח נמוך (2)",
			3: "נפח בינוני (3)",
			4: "נפח גבוה (4)",
			5: "נפח גבוה מאוד (5)",
		};

		legendContainer.innerHTML = "";
		for (let i = 1; i <= 5; i++) {
			const color = this.getVolumeColor(i);
			const item = document.createElement("div");
			item.className = "legend-item";
			item.innerHTML = `
                <span class="legend-color" style="background-color:${color}"></span>
                <span>${labels[i]}</span>
            `;
			legendContainer.appendChild(item);
		}
	}

	/**
	 * Initialize details panel with default values
	 */
	initializeDetailsPanel() {
		if (!this.cityName || !this.streetCount || !this.layerName) return;

		this.cityName.textContent = "אין עיר נבחרת";
		this.streetCount.textContent = "0 רחובות";
		this.layerName.textContent = "אין שכבה נבחרת";
	}

	// ============== UI Control Methods ==============

	/**
	 * Toggle the right panel collapse/expand state
	 * Updates the collapse button icon accordingly
	 * סמן הצגה/הסתרה של הפאנל הימני
	 */
	togglePanelCollapse() {
		this.searchPanel.classList.toggle("collapsed");
		const icon = this.panelCollapseBtn.querySelector(".collapse-icon");
		if (icon) {
			icon.textContent = this.searchPanel.classList.contains("collapsed")
				? "▶"
				: "X";
		}
	}


	/**
	 * Show status message to user
	 */
	showStatusMessage(message, type = "info", duration = 3000) {
		if (!this.statusMessage) return;

		this.statusMessage.textContent = message;
		this.statusMessage.className = `status-message ${type}`;
		this.statusMessage.classList.remove("hidden");

		if (duration > 0) {
			setTimeout(() => this.hideStatusMessage(), duration);
		}
	}

	/**
	 * Hide status message
	 */
	hideStatusMessage() {
		if (!this.statusMessage) return;
		this.statusMessage.classList.add("hidden");
	}

	/**
	 * Set loading state for a button
	 */
	setButtonLoading(button, textSpan, spinner, isLoading) {
		if (button) {
			button.disabled = isLoading;
		}

		if (textSpan) {
			if (isLoading) {
				textSpan.classList.add("hidden");
			} else {
				textSpan.classList.remove("hidden");
			}
		}

		if (spinner) {
			if (isLoading) {
				spinner.classList.remove("hidden");
			} else {
				spinner.classList.add("hidden");
			}
		}
	}

	/**
	 * Set loading state for the entire application
	 */
	setAppLoading(isLoading) {
		if (isLoading) {
			// Add loading cursor to panels and map
			this.searchPanel.classList.add("loading-cursor");
			this.detailsPanel.classList.add("loading-cursor");
			document.getElementById("map").classList.add("map-loading");
			
			// Disable all interactive elements
			this.disableAllInteractions();
		} else {
			// Remove loading cursor
			this.searchPanel.classList.remove("loading-cursor");
			this.detailsPanel.classList.remove("loading-cursor");
			document.getElementById("map").classList.remove("map-loading");
			
			// Re-enable interactive elements
			this.enableAllInteractions();
		}
	}

	/**
	 * Disable all interactive elements during loading
	 */
	disableAllInteractions() {
		// Disable all buttons
		const buttons = this.searchPanel.querySelectorAll("button");
		buttons.forEach(btn => {
			btn.disabled = true;
		});

		// Disable input fields
		const inputs = this.searchPanel.querySelectorAll("input");
		inputs.forEach(input => {
			input.disabled = true;
		});

		// Disable map interactions
		if (this.map) {
			this.map.dragging.disable();
			this.map.touchZoom.disable();
			this.map.doubleClickZoom.disable();
			this.map.scrollWheelZoom.disable();
			this.map.boxZoom.disable();
			this.map.keyboard.disable();
		}
	}

	/**
	 * Enable all interactive elements after loading
	 */
	enableAllInteractions() {
		// Re-enable buttons (except those that should remain disabled)
		const buttons = this.searchPanel.querySelectorAll("button");
		buttons.forEach(btn => {
			// Don't re-enable buttons that should be disabled based on state
			if (btn.id === "clearBboxBtn" && !this.drawnBbox) {
				btn.disabled = true;
			} else if (btn.id === "sendBboxBtn" && !this.drawnBbox) {
				btn.disabled = true;
			} else if (btn.id === "uploadGpkgBtn" && !this.selectedFile) {
				btn.disabled = true;
			} else {
				btn.disabled = false;
			}
		});

		// Re-enable input fields
		const inputs = this.searchPanel.querySelectorAll("input");
		inputs.forEach(input => {
			input.disabled = false;
		});

		// Re-enable map interactions
		if (this.map) {
			this.map.dragging.enable();
			this.map.touchZoom.enable();
			this.map.doubleClickZoom.enable();
			this.map.scrollWheelZoom.enable();
			this.map.boxZoom.enable();
			this.map.keyboard.enable();
		}
	}

	/**
	 * Show progress bar
	 */
	showProgress() {
		this.progressSection.classList.remove("hidden");
		this.updateProgress(0, this.totalRequests);
	}

	/**
	 * Hide progress bar
	 */
	hideProgress() {
		this.progressSection.classList.add("hidden");
	}

	/**
	 * Update progress bar
	 */
	updateProgress(completed, total) {
		const percentage = (completed / total) * 100;
		this.progressBar.style.width = `${percentage}%`;
		this.progressText.textContent = `${completed} / ${total}`;
	}

	/**
	 * Start monitoring progress updates from server
	 */
	startProgressMonitoring() {
		if (this.progressInterval) {
			clearInterval(this.progressInterval);
		}
		
		this.progressInterval = setInterval(async () => {
			try {
				const response = await fetch(`${this.API_BASE_URL}/progress`);
				if (response.ok) {
					const progress = await response.json();
					this.updateProgressFromServer(progress);
				}
			} catch (error) {
				console.warn("Failed to fetch progress:", error);
			}
		}, 1000); // Check every second
	}

	/**
	 * Stop monitoring progress updates
	 */
	stopProgressMonitoring() {
		if (this.progressInterval) {
			clearInterval(this.progressInterval);
			this.progressInterval = null;
		}
	}

	/**
	 * Update progress from server response
	 */
	updateProgressFromServer(progress) {
		if (progress.progress > 0 && progress.total_steps > 0) {
			this.updateProgress(progress.progress, progress.total_steps);
			
			// Update progress text with server message
			if (progress.message) {
				this.progressText.textContent = `${progress.progress} / ${progress.total_steps} - ${progress.message}`;
			}
		}
	}

	// ============== City Search Methods ==============

	/**
	 * Handle city search and prediction request
	 */
	async handleCitySearchAndSendToServerForPredictions() {
		this.hideStatusMessage();
		const city = this.citySearchInput.value.trim();
		if (!city) {
			this.showStatusMessage("נא להזין שם עיר", "error");
			return;
		}

		if (this.isProcessing) {
			this.showStatusMessage("מעבד בקשה קודמת, נא להמתין", "info");
			return;
		}

		this.isProcessing = true;
		this.setButtonLoading(
			this.searchCityBtn,
			this.searchCityBtnText,
			this.searchCitySpinner,
			true
		);
		this.setAppLoading(true);
		this.startProgressMonitoring();

		try {
			// First, find and navigate to the city
			await this.navigateToCity(city);

			// Then, request predictions for all time combinations
			await this.requestAllPredictionsCombinations(city);
		} catch (error) {
			console.error("City search error:", error);
			this.showStatusMessage(`שגיאה: ${error.message}`, "error");
		} finally {
			this.isProcessing = false;
			this.setButtonLoading(
				this.searchCityBtn,
				this.searchCityBtnText,
				this.searchCitySpinner,
				false
			);
			this.setAppLoading(false);
			this.stopProgressMonitoring();
		}
	}

	/**
	 * Navigate map to a specific city location
	 */
	async navigateToCity(city) {
		this.layerSelectionSection.classList.add("hidden");
		this.downloadSection.classList.add("hidden");
		this.weatherSummarySection.classList.add("hidden");
		this.clearCurrentLayer();

		try {
			const response = await fetch(
				`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(
					city
				)}&format=json&limit=1`
			);
			const data = await response.json();

			if (data && data.length > 0) {
				const lat = parseFloat(data[0].lat);
				const lon = parseFloat(data[0].lon);
				this.map.flyTo([lat, lon], 14, {
					animate: true,
					duration: 1.5,
				});
				console.log(`Navigated to ${city}: [${lat}, ${lon}]`);
			} else {
				throw new Error(`לא נמצא מיקום עבור "${city}"`);
			}
		} catch (error) {
			throw new Error(`שגיאה בחיפוש מיקום: ${error.message}`);
		}
	}

	/**
	 * Request predictions for all time combinations with parallel requests
	 */
	async requestAllPredictionsCombinations(place, bbox = null) {
		// Reset state
		this.allLayersData = [];
		this.completedRequests = 0;

		// Clear all existing layers from map and memory
		this.clearAllLayers();

		// Show progress
		this.showProgress();
		this.showStatusMessage("מבקש חיזויים עבור כל השילובים...", "info", 0);

		// Build single request to server multi endpoint
		const seasons = ["winter", "spring", "summer", "autumn"];
		const weekTypes = ["weekday", "weekend"];
		const timesOfDay = ["morning", "afternoon", "evening", "night"];

		const params = new URLSearchParams({
			seasons: seasons.join(","),
			week_types: weekTypes.join(","),
			times_of_day: timesOfDay.join(","),
		});
		if (place) params.set("place", place);
		if (bbox) {
			params.set(
				"bbox",
				`${bbox.west},${bbox.south},${bbox.east},${bbox.north}`
			);
		}
		
		// Always include average layer
		params.set("include_average", "true");

		this.totalRequests = 1;
		try {
			const resp = await fetch(`${this.API_BASE_URL}/predict-multi?${params.toString()}`);
			if (!resp.ok) {
				const err = await resp.json().catch(() => ({}));
				throw new Error(err.error || `Server error: ${resp.status}`);
			}
			const data = await resp.json();
			const layers = Array.isArray(data.layers) ? data.layers : [];
			this.allLayersData = layers.map((layer) => {
				const name = String(layer.name || "");

				// Handle average layer differently
				if (name === "average") {
					return {
						name,
						displayName: "שכבה ממוצעת",
						geojson: layer.geojson,
						metadata: {
							featureCount: layer.feature_count || layer.geojson?.features?.length || 0,
							location: data.place || place || "",
							timestamp: new Date().toISOString(),
						},
					};
				}

				// Handle regular layers
				const [season, weekType, timeOfDay] = name.split("_");
				return {
					name,
					displayName: `${this.translateSeason(season)} - ${this.translateWeekType(weekType)} - ${this.translateTimeOfDay(timeOfDay)}`,
					geojson: layer.geojson,
					metadata: {
						season,
						weekType,
						timeOfDay,
						featureCount: layer.feature_count || layer.geojson?.features?.length || 0,
						location: data.place || place || "",
						timestamp: new Date().toISOString(),
					},
					weather: layer.weather || {},
				};
			});

			this.completedRequests = 1;
			this.updateProgress(this.completedRequests, this.totalRequests);

			this.hideProgress();
			if (this.allLayersData.length > 0) {
				this.displayLayerSelection(this.allLayersData);
				this.displayWeatherSummary(this.allLayersData);
				this.downloadSection.classList.remove("hidden");
				this.showStatusMessage(`נטענו ${this.allLayersData.length} שכבות בהצלחה`, "success");
				await this.createCombinedGpkg(data.place || place || "");
			} else {
				this.showStatusMessage("לא התקבלו תוצאות חיזוי", "error", 0);
			}
		} catch (error) {
			this.hideProgress();
			throw new Error(`שגיאה בקבלת חיזויים: ${error.message}`);
		}
	}

	/**
	 * Request a single prediction for specific time parameters
	 */
	async requestSinglePrediction(
		place,
		bbox,
		{ season, weekType, timeOfDay }
	) {
		try {
			const params = new URLSearchParams({
				place: place || "",
				season: season,
				week_type: weekType,
				time_of_day: timeOfDay,
			});

			if (bbox) {
				params.set(
					"bbox",
					`${bbox.west},${bbox.south},${bbox.east},${bbox.north}`
				);
			}

			const response = await fetch(
				`${this.API_BASE_URL}/predict?${params.toString()}`
			);

			if (!response.ok) {
				const error = await response.json();
				throw new Error(
					error.error || `Server error: ${response.status}`
				);
			}

			const data = await response.json();

			// Transform the response to layer format
			return {
				name: `${season}_${weekType}_${timeOfDay}`,
				displayName: `${this.translateSeason(
					season
				)} - ${this.translateWeekType(
					weekType
				)} - ${this.translateTimeOfDay(timeOfDay)}`,
				geojson: data.geojson,
				metadata: {
					season: season,
					weekType: weekType,
					timeOfDay: timeOfDay,
					featureCount: data.geojson?.features?.length || 0,
					location: data.location,
					timestamp: data.timestamp,
				},
			};
		} catch (error) {
			console.error(
				`Error getting prediction for ${season}_${weekType}_${timeOfDay}:`,
				error
			);
			throw error;
		}
	}

	/**
	 * Create combined GPKG from all layers (using server endpoint)
	 */
	async createCombinedGpkg(place) {
		try {
			// For now, we'll download individual GPKGs and combine client-side
			// In production, you'd want a server endpoint that combines them

			// Get the first prediction as GPKG to use as base
			const params = new URLSearchParams({
				place: place,
				season: "winter",
				week_type: "weekday",
				time_of_day: "morning",
			});

			const response = await fetch(
				`${this.API_BASE_URL}/predict-gpkg?${params.toString()}`
			);

			if (response.ok) {
				this.currentGpkgBlob = await response.blob();
			}
		} catch (error) {
			console.error("Error creating combined GPKG:", error);
		}
	}

	// ============== GPKG Upload Methods ==============

	/**
	 * Handle GPKG file selection
	 */
	handleFileSelection() {
		const file = this.gpkgFileInput.files?.[0];
		if (file) {
			if (!file.name.toLowerCase().endsWith(".gpkg")) {
				this.showStatusMessage("יש לבחור קובץ GPKG", "error");
				this.uploadGpkgBtn.disabled = true;
				return;
			}

			this.selectedFile = file;
			this.uploadGpkgBtn.disabled = false;
			this.showStatusMessage(`נבחר קובץ: ${file.name}`, "info");
		} else {
			this.selectedFile = null;
			this.uploadGpkgBtn.disabled = true;
		}
	}

	/**
	 * Handle GPKG file upload to server
	 */
	async handleGpkgUpload() {
		this.hideStatusMessage();
		if (!this.selectedFile) {
			this.showStatusMessage("נא לבחור קובץ GPKG", "error");
			return;
		}

		if (this.isProcessing) {
			this.showStatusMessage("מעבד בקשה קודמת, נא להמתין", "info");
			return;
		}

		this.isProcessing = true;
		this.setButtonLoading(
			this.uploadGpkgBtn,
			this.uploadGpkgBtnText,
			this.uploadGpkgSpinner,
			true
		);
		this.setAppLoading(true);
		this.startProgressMonitoring();

		try {
			const formData = new FormData();
			formData.append("file", this.selectedFile);

			const response = await fetch(`${this.API_BASE_URL}/read-gpkg`, {
				method: "POST",
				body: formData,
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.error || `שגיאת שרת: ${response.status}`);
			}

			const result = await response.json();

			// Process the returned layers
			if (result.layers && result.layers.length > 0) {
				this.allLayersData = result.layers.map((layer) => ({
					name: layer.name,
					displayName: layer.name,
					geojson: layer.geojson,
					metadata: {
						featureCount: layer.feature_count,
						is_prediction_layer: layer.is_prediction_layer,
					},
				}));

				this.displayLayerSelection(this.allLayersData);

				// If bbox is available, fit map
				if (result.bbox) {
					const [west, south, east, north] = result.bbox;
					this.map.fitBounds(
						[
							[south, west],
							[north, east],
						],
						{
							padding: [50, 50],
							maxZoom: 15,
						}
					);
				}

				this.showStatusMessage("הקובץ עובד בהצלחה", "success");
			}
		} catch (error) {
			console.error("GPKG upload error:", error);
			this.showStatusMessage(`שגיאה: ${error.message}`, "error");
		} finally {
			this.isProcessing = false;
			this.setButtonLoading(
				this.uploadGpkgBtn,
				this.uploadGpkgBtnText,
				this.uploadGpkgSpinner,
				false
			);
			this.setAppLoading(false);
			this.stopProgressMonitoring();
		}
	}

	// ============== Local Navigation Methods ==============

	/**
	 * Handle find city locally (without server request)
	 */
	handleFindCity() {
		const city = this.citySearchInput.value.trim();
		if (!city) {
			this.showStatusMessage("נא להזין שם עיר", "error");
			return;
		}

		this.navigateToCity(city)
			.then(() => this.showStatusMessage(`נמצא: ${city}`, "success"))
			.catch((error) => this.showStatusMessage(error.message, "error"));
	}

	// ============== BBox Drawing Methods ==============

	/**
	 * Enable bbox drawing mode
	 */
	enableBboxDrawing() {
		// Clear any existing bbox
		this.clearBbox();

		// Create custom draw handler
		const rectangleDrawer = new L.Draw.Rectangle(this.map, {
			shapeOptions: {
				color: "#ff7800",
				weight: 2,
				fillOpacity: 0.1,
			},
		});

		rectangleDrawer.enable();

		// Handle drawing completion
		this.map.once("draw:created", (e) => {
			this.drawnBbox = e.layer;
			this.drawnItems.addLayer(this.drawnBbox);

			// Enable clear and send buttons, disable city search
			this.clearBboxBtn.disabled = false;
			this.sendBboxBtn.disabled = false;
			this.searchCityBtn.disabled = true;

			// Get bbox bounds
			const bounds = this.drawnBbox.getBounds();
			const bbox = {
				west: bounds.getWest(),
				south: bounds.getSouth(),
				east: bounds.getEast(),
				north: bounds.getNorth(),
			};

			console.log("BBox drawn:", bbox);
			this.showStatusMessage("האזור סומן בהצלחה", "success");
		});
	}

	/**
	 * Clear drawn bbox from map
	 */
	clearBbox() {
		if (this.drawnBbox) {
			this.drawnItems.removeLayer(this.drawnBbox);
			this.drawnBbox = null;
		}

		this.clearBboxBtn.disabled = true;
		this.sendBboxBtn.disabled = true;
		this.searchCityBtn.disabled = false;

		this.showStatusMessage("האזור המסומן נמחק", "info");
	}

	/**
	 * Send bbox to server for predictions
	 */
	async handleSendBbox() {
		this.hideStatusMessage();
		if (!this.drawnBbox) {
			this.showStatusMessage("נא לסמן אזור תחילה", "error");
			return;
		}

		if (this.isProcessing) {
			this.showStatusMessage("מעבד בקשה קודמת, נא להמתין", "info");
			return;
		}

		const bounds = this.drawnBbox.getBounds();
		const bbox = {
			west: bounds.getWest(),
			south: bounds.getSouth(),
			east: bounds.getEast(),
			north: bounds.getNorth(),
		};

		this.isProcessing = true;
		this.setButtonLoading(
			this.sendBboxBtn,
			this.sendBboxBtnText,
			this.sendBboxSpinner,
			true
		);
		this.setAppLoading(true);
		this.startProgressMonitoring();

		try {
			await this.requestAllPredictionsCombinations(null, bbox);
			this.showStatusMessage(
				"החיזויים עבור האזור נטענו בהצלחה",
				"success"
			);
		} catch (error) {
			console.error("BBox send error:", error);
			this.showStatusMessage(`שגיאה: ${error.message}`, "error");
		} finally {
			this.isProcessing = false;
			this.setButtonLoading(
				this.sendBboxBtn,
				this.sendBboxBtnText,
				this.sendBboxSpinner,
				false
			);
			this.setAppLoading(false);
			this.stopProgressMonitoring();
		}
	}

	// ============== Layer Management Methods ==============

	/**
	 * Handle clear layers button click
	 */
	handleClearLayers() {
		// Clear current layer from map
		this.clearCurrentLayer();
		
		// Remove active class from all layer buttons
		this.layerButtonsContainer
			.querySelectorAll(".layer-btn")
			.forEach((btn) => {
				btn.classList.remove("active");
			});
		
		this.showStatusMessage("השכבות הוסרו מהמפה", "info");
	}

	/**
	 * Display layer selection buttons
	 */
	displayLayerSelection(layers) {
		this.layerSelectionSection.classList.remove("hidden");
		this.layerButtonsContainer.innerHTML = "";

		// Check if we have an average layer from server
		console.log("All layers received:", layers.map(l => l.name));
		const hasAverageLayer = layers.some(layer => layer.name === 'average');
		console.log("Has average layer:", hasAverageLayer);
		
		// Add average layer button first if we have one from server
		if (hasAverageLayer) {
			const averageButton = document.createElement("button");
			averageButton.className = "layer-btn average-layer-btn";
			averageButton.textContent = "שכבה ממוצעת";
			averageButton.dataset.layerName = "average";

			averageButton.addEventListener("click", () => {
				// Remove active class from all buttons
				this.layerButtonsContainer
					.querySelectorAll(".layer-btn")
					.forEach((btn) => {
						btn.classList.remove("active");
					});

				// Add active class to clicked button
				averageButton.classList.add("active");

				// Display the average layer from server
				this.displayLayer("average");
			});

			this.layerButtonsContainer.appendChild(averageButton);
		}

		// Add individual layer buttons
		layers.forEach((layer) => {
			const button = document.createElement("button");
			button.className = "layer-btn";
			button.textContent = layer.displayName;
			button.dataset.layerName = layer.name;

			button.addEventListener("click", () => {
				// Remove active class from all buttons
				this.layerButtonsContainer
					.querySelectorAll(".layer-btn")
					.forEach((btn) => {
						btn.classList.remove("active");
					});

				// Add active class to clicked button
				button.classList.add("active");

				// Display the selected layer
				this.displayLayer(layer.name);
			});

			this.layerButtonsContainer.appendChild(button);
		});

		// Don't automatically display any layer - let user choose
	}

	/**
	 * Display weather summary for all layers
	 */
	displayWeatherSummary(layers) {
		// Filter out layers without weather data
		const layersWithWeather = layers.filter(
			(layer) => layer.weather && Object.keys(layer.weather).length > 0
		);

		if (layersWithWeather.length === 0) {
			this.weatherSummarySection.classList.add("hidden");
			return;
		}

		// Show the section
		this.weatherSummarySection.classList.remove("hidden");

		// Group by season and time_of_day for a cleaner display
		const weatherBySeason = {};

		layersWithWeather.forEach((layer) => {
			const season = layer.metadata?.season || "unknown";
			const timeOfDay = layer.metadata?.timeOfDay || "unknown";

			if (!weatherBySeason[season]) {
				weatherBySeason[season] = {};
			}
			if (!weatherBySeason[season][timeOfDay]) {
				weatherBySeason[season][timeOfDay] = layer.weather;
			}
		});

		// Create the weather summary HTML
		let html = '<div style="display: grid; gap: 10px;">';

		const seasons = ["winter", "spring", "summer", "autumn"];
		const timesOfDay = ["morning", "afternoon", "evening", "night"];

		seasons.forEach((season) => {
			if (weatherBySeason[season]) {
				html += `
					<div style="background: #f8f9fa; padding: 10px; border-radius: 6px;">
						<h4 style="margin: 0 0 8px 0; color: #333;">${this.translateSeason(
							season
						)}</h4>
						<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px;">
				`;

				timesOfDay.forEach((tod) => {
					if (weatherBySeason[season][tod]) {
						const weather = weatherBySeason[season][tod];
						html += `
							<div style="background: white; padding: 8px; border-radius: 4px; border: 1px solid #dee2e6;">
								<strong>${this.translateTimeOfDay(tod)}</strong><br/>
								${
									weather.temperature !== undefined
										? `<span style="font-size: 0.9em;">🌡️ ${this.formatTemp(
												weather.temperature
										  )}</span><br/>`
										: ""
								}
								${
									weather.precipitation !== undefined
										? `<span style="font-size: 0.9em;">💧 ${this.formatPrecip(
												weather.precipitation
										  )}</span><br/>`
										: ""
								}
								${
									weather.wind_speed !== undefined
										? `<span style="font-size: 0.9em;">💨 ${this.formatWind(
												weather.wind_speed
										  )}</span>`
										: ""
								}
							</div>
						`;
					}
				});

				html += `
						</div>
					</div>
				`;
			}
		});

		html += "</div>";

		this.weatherSummaryContent.innerHTML = html;
	}

	/**
	 * Display a specific layer on the map
	 */
	displayLayer(layerName) {
		// Clear current layer if exists
		if (this.currentLayers[this.currentLayerName]) {
			this.map.removeLayer(this.currentLayers[this.currentLayerName]);
		}

		// Find layer data
		const layerData = this.allLayersData?.find((l) => l.name === layerName);
		if (!layerData) {
			console.error(`Layer ${layerName} not found`);
			return;
		}

		// Create layer if not exists
		if (!this.currentLayers[layerName]) {
			this.currentLayers[layerName] = this.createGeoJSONLayer(
				layerData.geojson
			);
		}

		// Add layer to map
		this.currentLayers[layerName].addTo(this.map);
		this.currentLayerName = layerName;

		// Update details panel
		this.updateDetailsPanel(layerData);

		console.log(
			`Displaying layer: ${layerName} with ${
				layerData.geojson?.features?.length || 0
			} features`
		);
	}



	/**
	 * Clear the current layer from the map
	 */
	clearCurrentLayer() {
		if (
			this.currentLayerName &&
			this.currentLayers[this.currentLayerName]
		) {
			this.map.removeLayer(this.currentLayers[this.currentLayerName]);
			// אם רוצים רק להסתיר ולהשאיר בזיכרון:
			// השאירו את האובייקט ב־currentLayers
			// ואם רוצים למחוק גם מהזיכרון, בטלו את ההערה בשורה הבאה:
			delete this.currentLayers[this.currentLayerName];

			this.currentLayerName = null;
		}
	}

	/**
	 * Clear all layers from map and memory
	 */
	clearAllLayers() {
		// Remove all layers from map
		for (const name in this.currentLayers) {
			if (this.currentLayers[name]) {
				this.map.removeLayer(this.currentLayers[name]);
			}
		}

		// Clear all layer data
		this.currentLayers = {};
		this.currentLayerName = null;
	}
	/**
	 * Create GeoJSON layer with styling
	 */
	createGeoJSONLayer(geojson) {
		if (!geojson || !geojson.features) {
			console.warn("Invalid GeoJSON data");
			return L.geoJSON(null);
		}

		return L.geoJSON(geojson, {
			style: (feature) => this.getFeatureStyle(feature),
			onEachFeature: (feature, layer) =>
				this.bindFeaturePopup(feature, layer),
		});
	}

	/**
	 * Get style for a feature based on volume
	 */
	getFeatureStyle(feature) {
		const volume =
			feature.properties?.volume_bin ||
			feature.properties?.volume_class ||
			1;

		return {
			color: this.getVolumeColor(volume),
			weight: this.getVolumeWidth(volume),
			opacity: 0.85,
		};
	}

	/**
	 * Get color for volume level
	 */
	getVolumeColor(volume) {
		const colors = {
			1: "#00FF00", // Green
			2: "#FFFF00", // Yellow
			3: "#FFA500", // Orange
			4: "#FF0000", // Red
			5: "#660000", // Dark Red
		};
		return colors[volume] || colors[1];
	}

	/**
	 * Get line width for volume level
	 */
	getVolumeWidth(volume) {
		const widths = {
			1: 2,
			2: 3,
			3: 4,
			4: 5,
			5: 6,
		};
		return widths[volume] || widths[1];
	}

	/**
	 * Bind popup to feature
	 */
	bindFeaturePopup(feature, layer) {
		const props = feature.properties || {};

		// Check if this is an average layer feature
		const isAverageLayer = props.is_average_layer === true || props.average_from_layers !== undefined;

		const popupContent = `
			<div style="direction: rtl; text-align: right; min-width: 280px;">
				<h3 style="margin: 0 0 10px 0; color: #333;">
					${props.name || "רחוב ללא שם"}
				</h3>

				<div style="background: ${this.getFeatureStyle(feature).color};
								color: white; padding: 8px; border-radius: 6px; margin-bottom: 10px;
								text-shadow: 1px 1px 2px rgba(0,0,0,0.3);">
					<strong>${isAverageLayer ? 'נפח ממוצע:' : 'נפח חזוי:'} </strong>
					<span style="font-size: 1.2em; font-weight: bold;">
						${props.volume_bin ?? props.volume_class ?? "לא ידוע"}
					</span>
				</div>

				<div style="background: #f8f9fa; padding: 10px; border-radius: 6px;">
					<!-- Street Characteristics -->
					<p style="margin: 5px 0;"><strong>סוג רחוב:</strong> ${
						this.translateHighway(props.highway) || "לא ידוע"
					}</p>
					<p style="margin: 5px 0;"><strong>שימוש קרקע:</strong> ${
						this.translateLandUse(props.land_use) || "לא ידוע"
					}</p>

					<!-- Network Metrics -->
					<div style="font-size: 0.85em; color: #666; margin-top: 8px;">
						<p style="margin: 2px 0; font-weight: bold; color: #333;">מדדי רשת:</p>
						<p style="margin: 3px 0; padding-right: 10px;"><strong>Betweenness:</strong> ${this.formatProb(
							props.edge_betweenness ?? props.betweenness
						)}</p>
						<p style="margin: 3px 0; padding-right: 10px;"><strong>Closeness:</strong> ${this.formatProb(
							props.edge_closeness ?? props.closeness
						)}</p>
					</div>

					<!-- Environmental Features -->
					<div style="font-size: 0.85em; color: #666; margin-top: 8px;">
						<p style="margin: 2px 0; font-weight: bold; color: #333;">מאפייני סביבה:</p>
						<p style="margin: 3px 0; padding-right: 10px;"><strong>כיסוי עצים:</strong> ${this.formatPercent(props.sensor_canopy_pct)}</p>
						<p style="margin: 3px 0; padding-right: 10px;"><strong>מורכבות שטח:</strong> ${this.formatNormalized(props.terrain_complexity)}</p>
						<p style="margin: 3px 0; padding-right: 10px;"><strong>מיקום טופוגרפי:</strong> ${this.formatNormalized(props.topographic_position)}</p>
					</div>

					<hr style="margin: 10px 0; border: none; border-top: 1px solid #dee2e6;">
					<div style="font-size: 0.9em;">
						<p style="margin: 3px 0;"><strong>${isAverageLayer ? 'הסתברויות ממוצעות:' : 'הסתברויות:'}</strong></p>
						${this.formatProbabilities(props)}
					</div>
				</div>

				${
					props.osmid
						? `<p style="font-size: 0.8em; color: #999; margin-top: 8px;">OSM ID: ${props.osmid}</p>`
						: ""
				}
			</div>
		`;

		layer.bindPopup(popupContent, {
			maxWidth: 400,
			className: "custom-popup",
			autoPan: true,
			autoPanPaddingTopLeft: [50, 50],
			autoPanPaddingBottomRight: [50, 50],
		});

		// Center map on popup when opened
		layer.on("popupopen", (e) => {
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
							<div style="background: ${
								this.getFeatureStyle({
									properties: { volume_bin: i },
								}).color
							};
												width: ${barWidth}%; height: 100%; border-radius: 7px;"></div>
						</div>
						<span style="width: 45px; text-align: left; font-size: 0.85em;">${percentage}%</span>
					</div>
				`;
			}
		}
		html += "</div>";
		return html;
	}

	formatProb(val) {
		const n = Number(val);
		return Number.isFinite(n) ? n.toFixed(5) : "לא ידוע";
	}

	formatPercent(val) {
		const n = Number(val);
		return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "לא ידוע";
	}

	formatNormalized(val) {
		const n = Number(val);
		return Number.isFinite(n) ? n.toFixed(2) : "לא ידוע";
	}

	formatTemp(val) {
		const n = Number(val);
		return Number.isFinite(n) ? `${n.toFixed(1)}°C` : "לא ידוע";
	}

	formatPrecip(val) {
		const n = Number(val);
		return Number.isFinite(n) ? `${n.toFixed(1)} מ"מ` : "לא ידוע";
	}

	formatWind(val) {
		const n = Number(val);
		return Number.isFinite(n) ? `${n.toFixed(1)} קמ"ש` : "לא ידוע";
	}

	translateTimeOfDay(timeOfDay) {
		const translations = {
			morning: "בוקר",
			afternoon: "צהריים",
			evening: "ערב",
			night: "לילה",
		};
		return translations[timeOfDay] || timeOfDay;
	}


	/**
	 * Update details panel with layer information
	 */
	updateDetailsPanel(layerData) {
		if (!this.detailsPanel || !this.cityName || !this.streetCount || !this.layerName) return;

		const metadata = layerData.metadata || {};

		// Update city name
		if (metadata.location) {
			this.cityName.textContent = metadata.location;
		} else {
			this.cityName.textContent = "מיקום לא ידוע";
		}

		// Update street count
		const count = metadata.featureCount || 0;
		this.streetCount.textContent = `${count} רחובות`;

		// Update layer name
		if (layerData.name === "average") {
			this.layerName.textContent = "שכבה ממוצעת";
		} else {
			this.layerName.textContent = layerData.displayName || layerData.name;
		}
	}

	// ============== Download Methods ==============

	/**
	 * Handle GPKG download
	 */
	async handleDownloadGpkg() {
		this.hideStatusMessage();
		if (this.currentGpkgBlob) {
			// If we have a pre-created GPKG blob, use it
			const url = URL.createObjectURL(this.currentGpkgBlob);
			const a = document.createElement("a");
			a.href = url;
			a.download = `predictions_all_layers_${new Date()
				.toISOString()
				.slice(0, 10)}.gpkg`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);

			this.showStatusMessage("הקובץ הורד בהצלחה", "success");
		} else if (this.allLayersData.length > 0) {
			// If no GPKG blob but we have layer data, try to download from server
			this.setButtonLoading(
				this.downloadGpkgBtn,
				this.downloadBtnText,
				this.downloadSpinner,
				true
			);

			try {
				// Get the place name from the first layer's metadata
				const location =
					this.allLayersData[0]?.metadata?.location ||
					this.citySearchInput.value.trim() ||
					"unknown";

				// Download GPKG for any single combination (server will generate all if needed)
				const params = new URLSearchParams({
					place: location,
					season: "winter",
					week_type: "weekday",
					time_of_day: "morning",
				});

				const response = await fetch(
					`${this.API_BASE_URL}/predict-gpkg?${params.toString()}`
				);

				if (response.ok) {
					const blob = await response.blob();
					const url = URL.createObjectURL(blob);
					const a = document.createElement("a");
					a.href = url;
					a.download = `predictions_${location}_${new Date()
						.toISOString()
						.slice(0, 10)}.gpkg`;
					document.body.appendChild(a);
					a.click();
					document.body.removeChild(a);
					URL.revokeObjectURL(url);

					this.showStatusMessage("הקובץ הורד בהצלחה", "success");
				} else {
					throw new Error("Failed to download GPKG");
				}
			} catch (error) {
				console.error("Download error:", error);
				this.showStatusMessage("שגיאה בהורדת הקובץ", "error");
			} finally {
				this.setButtonLoading(
					this.downloadGpkgBtn,
					this.downloadBtnText,
					this.downloadSpinner,
					false
				);
			}
		} else {
			this.showStatusMessage("אין קובץ להורדה", "error");
		}
	}

	// ============== Translation Methods ==============

	translateSeason(season) {
		const translations = {
			winter: "חורף",
			spring: "אביב",
			summer: "קיץ",
			autumn: "סתיו",
		};
		return translations[season] || season;
	}

	translateWeekType(weekType) {
		const translations = {
			weekday: "אמצע שבוע",
			weekend: "סוף שבוע",
		};
		return translations[weekType] || weekType;
	}

	translateTimeOfDay(timeOfDay) {
		const translations = {
			morning: "בוקר",
			afternoon: "צהריים",
			evening: "ערב",
			night: "לילה",
		};
		return translations[timeOfDay] || timeOfDay;
	}

	translateHighway(highway) {
		const translations = {
			primary: "כביש ראשי",
			secondary: "כביש משני",
			tertiary: "כביש שלישוני",
			residential: "רחוב מגורים",
			footway: "שביל הולכי רגל",
			path: "שביל",
			pedestrian: "אזור הולכי רגל",
			living_street: "רחוב מגורים שקט",
			unclassified: "לא מסווג",
			service: "דרך שירות",
		};
		return translations[highway] || highway;
	}

	translateLandUse(landUse) {
		const translations = {
			residential: "מגורים",
			commercial: "מסחרי",
			retail: "קמעונאי",
			industrial: "תעשייתי",
			other: "אחר",
		};
		return translations[landUse] || landUse;
	}
}

// Initialize app when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
	const app = new PedestrianPredictionApp();
	window.pedestrianApp = app; // Make available globally for debugging
	console.log("Pedestrian Prediction App initialized");
});
