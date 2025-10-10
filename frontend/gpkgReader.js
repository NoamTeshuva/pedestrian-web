// // gpkgReader.js - Module for reading GPKG files in the browser

// /**
//  * GPKG Reader class for parsing GeoPackage files in the browser
//  * Uses sql.js for SQLite operations
//  */
// class GPKGReader {
// 	constructor() {
// 		this.SQL = null;
// 		this.isInitialized = false;
// 	}

// 	/**
// 	 * Initialize SQL.js library
// 	 * Must be called before any GPKG operations
// 	 */
// 	async initialize() {
// 		if (this.isInitialized) return;

// 		try {
// 			// Load SQL.js from CDN
// 			const sqlJsScript = document.createElement("script");
// 			sqlJsScript.src =
// 				"https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/sql-wasm.js";
// 			document.head.appendChild(sqlJsScript);

// 			await new Promise((resolve, reject) => {
// 				sqlJsScript.onload = resolve;
// 				sqlJsScript.onerror = reject;
// 			});

// 			// Initialize SQL.js with WASM
// 			this.SQL = await initSqlJs({
// 				locateFile: (file) =>
// 					`https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}`,
// 			});

// 			this.isInitialized = true;
// 			console.log("GPKG Reader initialized successfully");
// 		} catch (error) {
// 			throw new Error(
// 				`Failed to initialize GPKG Reader: ${error.message}`
// 			);
// 		}
// 	}

// 	/**
// 	 * Read GPKG file and extract all layers
// 	 * @param {Blob|File} blob - GPKG file blob
// 	 * @returns {Promise<Object>} Object containing layers and metadata
// 	 */
// 	async readGPKG(blob) {
// 		if (!this.isInitialized) {
// 			await this.initialize();
// 		}

// 		try {
// 			// Convert blob to ArrayBuffer
// 			const buffer = await blob.arrayBuffer();
// 			const db = new this.SQL.Database(new Uint8Array(buffer));

// 			// Get GPKG metadata
// 			const metadata = this.getGPKGMetadata(db);

// 			// Get all feature layers
// 			const layers = this.getFeatureLayers(db);

// 			// Process each layer
// 			const processedLayers = [];
// 			for (const layer of layers) {
// 				const layerData = await this.processLayer(db, layer);
// 				processedLayers.push(layerData);
// 			}

// 			db.close();

// 			return {
// 				metadata: metadata,
// 				layers: processedLayers,
// 				layerCount: processedLayers.length,
// 			};
// 		} catch (error) {
// 			throw new Error(`Failed to read GPKG file: ${error.message}`);
// 		}
// 	}

// 	/**
// 	 * Get GPKG metadata from gpkg_contents table
// 	 * @param {SQL.Database} db - SQLite database instance
// 	 * @returns {Object} Metadata object
// 	 */
// 	getGPKGMetadata(db) {
// 		try {
// 			const result = db.exec(`
//                 SELECT
//                     table_name,
//                     data_type,
//                     identifier,
//                     description,
//                     min_x, min_y, max_x, max_y,
//                     srs_id
//                 FROM gpkg_contents
//                 WHERE data_type = 'features'
//             `);

// 			if (!result || result.length === 0) {
// 				return { tables: [] };
// 			}

// 			const columns = result[0].columns;
// 			const values = result[0].values;

// 			const tables = values.map((row) => {
// 				const table = {};
// 				columns.forEach((col, idx) => {
// 					table[col] = row[idx];
// 				});
// 				return table;
// 			});

// 			// Calculate overall bounds
// 			let bounds = null;
// 			if (tables.length > 0) {
// 				bounds = {
// 					west: Math.min(...tables.map((t) => t.min_x || 0)),
// 					south: Math.min(...tables.map((t) => t.min_y || 0)),
// 					east: Math.max(...tables.map((t) => t.max_x || 0)),
// 					north: Math.max(...tables.map((t) => t.max_y || 0)),
// 				};
// 			}

// 			return {
// 				tables: tables,
// 				bounds: bounds,
// 				crs: tables[0]?.srs_id || 4326,
// 			};
// 		} catch (error) {
// 			console.warn("Could not read GPKG metadata:", error);
// 			return { tables: [] };
// 		}
// 	}

// 	/**
// 	 * Get list of feature layers from GPKG
// 	 * @param {SQL.Database} db - SQLite database instance
// 	 * @returns {Array} Array of layer names
// 	 */
// 	getFeatureLayers(db) {
// 		try {
// 			const result = db.exec(`
//                 SELECT table_name
//                 FROM gpkg_contents
//                 WHERE data_type = 'features'
//                 ORDER BY table_name
//             `);

// 			if (!result || result.length === 0) {
// 				return [];
// 			}

// 			return result[0].values.map((row) => row[0]);
// 		} catch (error) {
// 			console.warn("Could not get feature layers:", error);
// 			return [];
// 		}
// 	}

// 	/**
// 	 * Process a single layer and convert to GeoJSON
// 	 * @param {SQL.Database} db - SQLite database instance
// 	 * @param {string} layerName - Name of the layer
// 	 * @returns {Promise<Object>} Layer object with GeoJSON data
// 	 */
// 	async processLayer(db, layerName) {
// 		try {
// 			// Get geometry column name
// 			const geomColResult = db.exec(`
//                 SELECT column_name, geometry_type_name, srs_id
//                 FROM gpkg_geometry_columns
//                 WHERE table_name = '${layerName}'
//             `);

// 			const geomColumn = geomColResult[0]?.values[0][0] || "geom";
// 			const geomType = geomColResult[0]?.values[0][1] || "GEOMETRY";
// 			const srsId = geomColResult[0]?.values[0][2] || 4326;

// 			// Get column information
// 			const columnsResult = db.exec(`PRAGMA table_info('${layerName}')`);
// 			const columns = columnsResult[0].values
// 				.map((col) => col[1]) // column name is at index 1
// 				.filter((col) => col !== geomColumn);

// 			// Query features with limit for performance
// 			const featuresResult = db.exec(`
//                 SELECT ${columns.join(",")},
//                        AsWKB(${geomColumn}) as geom_wkb
//                 FROM '${layerName}'
//                 LIMIT 50000
//             `);

// 			if (!featuresResult || featuresResult.length === 0) {
// 				return {
// 					name: layerName,
// 					displayName: this.formatLayerName(layerName),
// 					geojson: {
// 						type: "FeatureCollection",
// 						features: [],
// 					},
// 					metadata: {
// 						geometryType: geomType,
// 						srsId: srsId,
// 						featureCount: 0,
// 					},
// 				};
// 			}

// 			// Convert to GeoJSON
// 			const features = this.convertToGeoJSON(
// 				featuresResult[0].values,
// 				columns,
// 				featuresResult[0].columns.indexOf("geom_wkb")
// 			);

// 			// Parse layer name for time parameters if present
// 			const timeParams = this.parseLayerName(layerName);

// 			return {
// 				name: layerName,
// 				displayName: this.formatLayerName(layerName),
// 				geojson: {
// 					type: "FeatureCollection",
// 					features: features,
// 				},
// 				metadata: {
// 					geometryType: geomType,
// 					srsId: srsId,
// 					featureCount: features.length,
// 					...timeParams,
// 				},
// 			};
// 		} catch (error) {
// 			console.error(`Error processing layer ${layerName}:`, error);
// 			return {
// 				name: layerName,
// 				displayName: layerName,
// 				geojson: {
// 					type: "FeatureCollection",
// 					features: [],
// 				},
// 				metadata: {
// 					error: error.message,
// 				},
// 			};
// 		}
// 	}

// 	/**
// 	 * Convert WKB geometry and attributes to GeoJSON features
// 	 * @param {Array} rows - Database rows
// 	 * @param {Array} columns - Column names
// 	 * @param {number} geomIndex - Index of geometry column
// 	 * @returns {Array} Array of GeoJSON features
// 	 */
// 	convertToGeoJSON(rows, columns, geomIndex) {
// 		const features = [];

// 		for (const row of rows) {
// 			try {
// 				// Parse WKB geometry
// 				const geomWkb = row[geomIndex];
// 				const geometry = this.parseWKB(geomWkb);

// 				if (!geometry) continue;

// 				// Build properties object
// 				const properties = {};
// 				columns.forEach((col, idx) => {
// 					properties[col] = row[idx];
// 				});

// 				features.push({
// 					type: "Feature",
// 					geometry: geometry,
// 					properties: properties,
// 				});
// 			} catch (error) {
// 				console.warn("Error parsing feature:", error);
// 			}
// 		}

// 		return features;
// 	}

// 	/**
// 	 * Parse WKB (Well-Known Binary) to GeoJSON geometry
// 	 * @param {Uint8Array} wkb - WKB data
// 	 * @returns {Object|null} GeoJSON geometry object
// 	 */
// 	parseWKB(wkb) {
// 		if (!wkb || wkb.length < 5) return null;

// 		try {
// 			// This is a simplified WKB parser for LineString (most common for streets)
// 			// For production, use a library like wkx or wellknown

// 			const view = new DataView(wkb.buffer || wkb);
// 			let offset = 0;

// 			// Read byte order (1 byte)
// 			const byteOrder = view.getUint8(offset);
// 			const littleEndian = byteOrder === 1;
// 			offset += 1;

// 			// Read geometry type (4 bytes)
// 			const geomType = view.getUint32(offset, littleEndian);
// 			offset += 4;

// 			// Handle different geometry types
// 			const baseType = geomType & 0xff; // Remove dimension flags

// 			switch (baseType) {
// 				case 1: // Point
// 					return this.parsePoint(view, offset, littleEndian);
// 				case 2: // LineString
// 					return this.parseLineString(view, offset, littleEndian);
// 				case 3: // Polygon
// 					return this.parsePolygon(view, offset, littleEndian);
// 				default:
// 					console.warn(`Unsupported geometry type: ${baseType}`);
// 					return null;
// 			}
// 		} catch (error) {
// 			console.warn("Error parsing WKB:", error);
// 			return null;
// 		}
// 	}

// 	/**
// 	 * Parse WKB Point geometry
// 	 */
// 	parsePoint(view, offset, littleEndian) {
// 		const x = view.getFloat64(offset, littleEndian);
// 		offset += 8;
// 		const y = view.getFloat64(offset, littleEndian);

// 		return {
// 			type: "Point",
// 			coordinates: [x, y],
// 		};
// 	}

// 	/**
// 	 * Parse WKB LineString geometry
// 	 */
// 	parseLineString(view, offset, littleEndian) {
// 		const numPoints = view.getUint32(offset, littleEndian);
// 		offset += 4;

// 		const coordinates = [];
// 		for (let i = 0; i < numPoints; i++) {
// 			const x = view.getFloat64(offset, littleEndian);
// 			offset += 8;
// 			const y = view.getFloat64(offset, littleEndian);
// 			offset += 8;
// 			coordinates.push([x, y]);
// 		}

// 		return {
// 			type: "LineString",
// 			coordinates: coordinates,
// 		};
// 	}

// 	/**
// 	 * Parse WKB Polygon geometry
// 	 */
// 	parsePolygon(view, offset, littleEndian) {
// 		const numRings = view.getUint32(offset, littleEndian);
// 		offset += 4;

// 		const coordinates = [];
// 		for (let r = 0; r < numRings; r++) {
// 			const numPoints = view.getUint32(offset, littleEndian);
// 			offset += 4;

// 			const ring = [];
// 			for (let i = 0; i < numPoints; i++) {
// 				const x = view.getFloat64(offset, littleEndian);
// 				offset += 8;
// 				const y = view.getFloat64(offset, littleEndian);
// 				offset += 8;
// 				ring.push([x, y]);
// 			}
// 			coordinates.push(ring);
// 		}

// 		return {
// 			type: "Polygon",
// 			coordinates: coordinates,
// 		};
// 	}

// 	/**
// 	 * Parse layer name to extract time parameters
// 	 * @param {string} layerName - Layer name (e.g., "winter_weekday_morning")
// 	 * @returns {Object} Parsed time parameters
// 	 */
// 	parseLayerName(layerName) {
// 		const parts = layerName.split("_");

// 		if (parts.length >= 3) {
// 			return {
// 				season: parts[0],
// 				weekType: parts[1],
// 				timeOfDay: parts[2],
// 			};
// 		}

// 		return {};
// 	}

// 	/**
// 	 * Format layer name for display
// 	 * @param {string} layerName - Raw layer name
// 	 * @returns {string} Formatted display name
// 	 */
// 	formatLayerName(layerName) {
// 		const translations = {
// 			winter: "חורף",
// 			spring: "אביב",
// 			summer: "קיץ",
// 			autumn: "סתיו",
// 			weekday: "אמצע שבוע",
// 			weekend: "סוף שבוע",
// 			morning: "בוקר",
// 			afternoon: "צהריים",
// 			evening: "ערב",
// 			night: "לילה",
// 		};

// 		const parts = layerName.split("_");
// 		const translated = parts.map((part) => translations[part] || part);

// 		if (translated.length >= 3) {
// 			return `${translated[0]} - ${translated[1]} - ${translated[2]}`;
// 		}

// 		return layerName;
// 	}
// }

// // Export for use in main application
// window.GPKGReader = GPKGReader;

// gpkgReader.js - Module for reading GPKG files in the browser

/**
 * GPKG Reader class for parsing GeoPackage files in the browser
 * Uses sql.js for SQLite operations
 */
class GPKGReader {
	constructor() {
		this.SQL = null;
		this.isInitialized = false;
	}

	/**
	 * Initialize SQL.js library
	 * Must be called before any GPKG operations
	 */
	async initialize() {
		if (this.isInitialized) return;

		try {
			// Load SQL.js from CDN
			const sqlJsScript = document.createElement("script");
			sqlJsScript.src =
				"https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/sql-wasm.js";
			document.head.appendChild(sqlJsScript);

			await new Promise((resolve, reject) => {
				sqlJsScript.onload = resolve;
				sqlJsScript.onerror = reject;
			});

			// Initialize SQL.js with WASM
			this.SQL = await initSqlJs({
				locateFile: (file) =>
					`https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.8.0/${file}`,
			});

			this.isInitialized = true;
			console.log("GPKG Reader initialized successfully");
		} catch (error) {
			throw new Error(
				`Failed to initialize GPKG Reader: ${error.message}`
			);
		}
	}

	/**
	 * Read GPKG file and extract all layers
	 * @param {Blob|File} blob - GPKG file blob
	 * @returns {Promise<Object>} Object containing layers and metadata
	 */
	async readGPKG(blob) {
		if (!this.isInitialized) {
			await this.initialize();
		}

		try {
			// Convert blob to ArrayBuffer
			const buffer = await blob.arrayBuffer();
			const db = new this.SQL.Database(new Uint8Array(buffer));

			// Get GPKG metadata
			const metadata = this.getGPKGMetadata(db);

			// Get all feature layers
			const layers = this.getFeatureLayers(db);

			// Process each layer
			const processedLayers = [];
			for (const layer of layers) {
				const layerData = await this.processLayer(db, layer);
				processedLayers.push(layerData);
			}

			db.close();

			return {
				metadata: metadata,
				layers: processedLayers,
				layerCount: processedLayers.length,
			};
		} catch (error) {
			throw new Error(`Failed to read GPKG file: ${error.message}`);
		}
	}

	/**
	 * Get GPKG metadata from gpkg_contents table
	 * @param {SQL.Database} db - SQLite database instance
	 * @returns {Object} Metadata object
	 */
	getGPKGMetadata(db) {
		try {
			const result = db.exec(`
                SELECT 
                    table_name,
                    data_type,
                    identifier,
                    description,
                    min_x, min_y, max_x, max_y,
                    srs_id
                FROM gpkg_contents
                WHERE data_type = 'features'
            `);

			if (!result || result.length === 0) {
				return { tables: [] };
			}

			const columns = result[0].columns;
			const values = result[0].values;

			const tables = values.map((row) => {
				const table = {};
				columns.forEach((col, idx) => {
					table[col] = row[idx];
				});
				return table;
			});

			// Calculate overall bounds
			let bounds = null;
			if (tables.length > 0) {
				bounds = {
					west: Math.min(...tables.map((t) => t.min_x || 0)),
					south: Math.min(...tables.map((t) => t.min_y || 0)),
					east: Math.max(...tables.map((t) => t.max_x || 0)),
					north: Math.max(...tables.map((t) => t.max_y || 0)),
				};
			}

			return {
				tables: tables,
				bounds: bounds,
				crs: tables[0]?.srs_id || 4326,
			};
		} catch (error) {
			console.warn("Could not read GPKG metadata:", error);
			return { tables: [] };
		}
	}

	/**
	 * Get list of feature layers from GPKG
	 * @param {SQL.Database} db - SQLite database instance
	 * @returns {Array} Array of layer names
	 */
	getFeatureLayers(db) {
		try {
			const result = db.exec(`
                SELECT table_name 
                FROM gpkg_contents 
                WHERE data_type = 'features'
                ORDER BY table_name
            `);

			if (!result || result.length === 0) {
				return [];
			}

			return result[0].values.map((row) => row[0]);
		} catch (error) {
			console.warn("Could not get feature layers:", error);
			return [];
		}
	}

	/**
	 * Process a single layer and convert to GeoJSON
	 * @param {SQL.Database} db - SQLite database instance
	 * @param {string} layerName - Name of the layer
	 * @returns {Promise<Object>} Layer object with GeoJSON data
	 */
	async processLayer(db, layerName) {
		try {
			// Get geometry column name
			const geomColResult = db.exec(`
                SELECT column_name, geometry_type_name, srs_id
                FROM gpkg_geometry_columns
                WHERE table_name = '${layerName}'
            `);

			const geomColumn = geomColResult[0]?.values[0][0] || "geom";
			const geomType = geomColResult[0]?.values[0][1] || "GEOMETRY";
			const srsId = geomColResult[0]?.values[0][2] || 4326;

			// Get column information
			const columnsResult = db.exec(`PRAGMA table_info('${layerName}')`);
			const columns = columnsResult[0].values
				.map((col) => col[1]) // column name is at index 1
				.filter((col) => col !== geomColumn);

			// Query features with limit for performance
			const featuresResult = db.exec(`
                SELECT ${columns.join(",")}, 
                       AsWKB(${geomColumn}) as geom_wkb
                FROM '${layerName}'
                LIMIT 50000
            `);

			if (!featuresResult || featuresResult.length === 0) {
				return {
					name: layerName,
					displayName: this.formatLayerName(layerName),
					geojson: {
						type: "FeatureCollection",
						features: [],
					},
					metadata: {
						geometryType: geomType,
						srsId: srsId,
						featureCount: 0,
					},
				};
			}

			// Convert to GeoJSON
			const features = this.convertToGeoJSON(
				featuresResult[0].values,
				columns,
				featuresResult[0].columns.indexOf("geom_wkb")
			);

			// Parse layer name for time parameters if present
			const timeParams = this.parseLayerName(layerName);

			return {
				name: layerName,
				displayName: this.formatLayerName(layerName),
				geojson: {
					type: "FeatureCollection",
					features: features,
				},
				metadata: {
					geometryType: geomType,
					srsId: srsId,
					featureCount: features.length,
					...timeParams,
				},
			};
		} catch (error) {
			console.error(`Error processing layer ${layerName}:`, error);
			return {
				name: layerName,
				displayName: layerName,
				geojson: {
					type: "FeatureCollection",
					features: [],
				},
				metadata: {
					error: error.message,
				},
			};
		}
	}

	/**
	 * Convert WKB geometry and attributes to GeoJSON features
	 * @param {Array} rows - Database rows
	 * @param {Array} columns - Column names
	 * @param {number} geomIndex - Index of geometry column
	 * @returns {Array} Array of GeoJSON features
	 */
	convertToGeoJSON(rows, columns, geomIndex) {
		const features = [];

		for (const row of rows) {
			try {
				// Parse WKB geometry
				const geomWkb = row[geomIndex];
				const geometry = this.parseWKB(geomWkb);

				if (!geometry) continue;

				// Build properties object
				const properties = {};
				columns.forEach((col, idx) => {
					properties[col] = row[idx];
				});

				features.push({
					type: "Feature",
					geometry: geometry,
					properties: properties,
				});
			} catch (error) {
				console.warn("Error parsing feature:", error);
			}
		}

		return features;
	}

	/**
	 * Parse WKB or GeoPackage Binary to GeoJSON geometry
	 * @param {Uint8Array} wkb - WKB or GPB data
	 * @returns {Object|null} GeoJSON geometry object
	 */
	parseWKB(wkb) {
		if (!this.wkbParser) {
			this.wkbParser = new WKBParser();
		}

		// Try parsing as GeoPackage Binary first, fallback to standard WKB
		return this.wkbParser.parseGeoPackageBinary(wkb);
	}

	/**
	 * Parse layer name to extract time parameters
	 * @param {string} layerName - Layer name (e.g., "winter_weekday_morning")
	 * @returns {Object} Parsed time parameters
	 */
	parseLayerName(layerName) {
		const parts = layerName.split("_");

		if (parts.length >= 3) {
			return {
				season: parts[0],
				weekType: parts[1],
				timeOfDay: parts[2],
			};
		}

		return {};
	}

	/**
	 * Format layer name for display
	 * @param {string} layerName - Raw layer name
	 * @returns {string} Formatted display name
	 */
	formatLayerName(layerName) {
		const translations = {
			winter: "חורף",
			spring: "אביב",
			summer: "קיץ",
			autumn: "סתיו",
			weekday: "אמצע שבוע",
			weekend: "סוף שבוע",
			morning: "בוקר",
			afternoon: "צהריים",
			evening: "ערב",
			night: "לילה",
		};

		const parts = layerName.split("_");
		const translated = parts.map((part) => translations[part] || part);

		if (translated.length >= 3) {
			return `${translated[0]} - ${translated[1]} - ${translated[2]}`;
		}

		return layerName;
	}
}

// Export for use in main application
window.GPKGReader = GPKGReader;
