// wkbParser.js - Enhanced WKB (Well-Known Binary) Parser for GeoPackage

/**
 * Enhanced WKB Parser with support for all geometry types
 * Handles GeoPackage specific binary format
 */
class WKBParser {
	constructor() {
		// WKB Type constants
		this.WKB_POINT = 1;
		this.WKB_LINESTRING = 2;
		this.WKB_POLYGON = 3;
		this.WKB_MULTIPOINT = 4;
		this.WKB_MULTILINESTRING = 5;
		this.WKB_MULTIPOLYGON = 6;
		this.WKB_GEOMETRYCOLLECTION = 7;

		// Dimension flags
		this.WKB_Z = 0x80000000;
		this.WKB_M = 0x40000000;
		this.WKB_ZM = 0xc0000000;
	}

	/**
	 * Parse GeoPackage Binary geometry
	 * @param {Uint8Array} gpb - GeoPackage Binary data
	 * @returns {Object|null} GeoJSON geometry object
	 */
	parseGeoPackageBinary(gpb) {
		if (!gpb || gpb.length < 8) return null;

		try {
			const view = new DataView(gpb.buffer || gpb);
			let offset = 0;

			// Read GeoPackage Binary Header
			// Magic bytes: 'G' 'P'
			const magic1 = view.getUint8(offset++);
			const magic2 = view.getUint8(offset++);

			if (magic1 !== 0x47 || magic2 !== 0x50) {
				// Not a GeoPackage Binary, try as standard WKB
				return this.parseWKB(gpb);
			}

			// Version
			const version = view.getUint8(offset++);

			// Flags
			const flags = view.getUint8(offset++);
			const envelopeType = (flags >> 1) & 0x07;
			const isEmpty = (flags & 0x20) !== 0;
			const endianness = (flags & 0x01) !== 0;
			const binary_type = (flags & 0x20) >> 5;

			if (isEmpty) {
				return null;
			}

			// SRS ID (4 bytes)
			const srsId = view.getInt32(offset, !endianness);
			offset += 4;

			// Skip envelope based on type
			const envelopeSize = this.getEnvelopeSize(envelopeType);
			offset += envelopeSize * 8; // 8 bytes per coordinate

			// Parse WKB geometry
			const wkbData = new Uint8Array(gpb.buffer || gpb, offset);
			return this.parseWKB(wkbData);
		} catch (error) {
			console.warn("Error parsing GeoPackage Binary:", error);
			return null;
		}
	}

	/**
	 * Get envelope size based on type
	 */
	getEnvelopeSize(envelopeType) {
		switch (envelopeType) {
			case 0:
				return 0; // No envelope
			case 1:
				return 4; // XY
			case 2:
				return 6; // XYZ
			case 3:
				return 6; // XYM
			case 4:
				return 8; // XYZM
			default:
				return 0;
		}
	}

	/**
	 * Parse standard WKB
	 * @param {Uint8Array} wkb - WKB data
	 * @returns {Object|null} GeoJSON geometry object
	 */
	parseWKB(wkb) {
		if (!wkb || wkb.length < 5) return null;

		try {
			const view = new DataView(wkb.buffer || wkb);
			let offset = 0;

			// Read byte order
			const byteOrder = view.getUint8(offset++);
			const littleEndian = byteOrder === 1;

			// Read geometry type
			const geomTypeRaw = view.getUint32(offset, littleEndian);
			offset += 4;

			// Extract base type and dimension info
			const hasZ = (geomTypeRaw & this.WKB_Z) !== 0;
			const hasM = (geomTypeRaw & this.WKB_M) !== 0;
			const dimensions = 2 + (hasZ ? 1 : 0) + (hasM ? 1 : 0);
			const geomType = geomTypeRaw & 0xff;

			// Parse based on geometry type
			switch (geomType) {
				case this.WKB_POINT:
					return this.parsePoint(
						view,
						offset,
						littleEndian,
						dimensions
					);

				case this.WKB_LINESTRING:
					return this.parseLineString(
						view,
						offset,
						littleEndian,
						dimensions
					);

				case this.WKB_POLYGON:
					return this.parsePolygon(
						view,
						offset,
						littleEndian,
						dimensions
					);

				case this.WKB_MULTIPOINT:
					return this.parseMultiPoint(
						view,
						offset,
						littleEndian,
						dimensions
					);

				case this.WKB_MULTILINESTRING:
					return this.parseMultiLineString(
						view,
						offset,
						littleEndian,
						dimensions
					);

				case this.WKB_MULTIPOLYGON:
					return this.parseMultiPolygon(
						view,
						offset,
						littleEndian,
						dimensions
					);

				case this.WKB_GEOMETRYCOLLECTION:
					return this.parseGeometryCollection(
						view,
						offset,
						littleEndian
					);

				default:
					console.warn(`Unsupported WKB geometry type: ${geomType}`);
					return null;
			}
		} catch (error) {
			console.warn("Error parsing WKB:", error);
			return null;
		}
	}

	/**
	 * Read a coordinate based on dimensions
	 */
	readCoordinate(view, offset, littleEndian, dimensions) {
		const coord = [];
		for (let i = 0; i < dimensions; i++) {
			coord.push(view.getFloat64(offset.value, littleEndian));
			offset.value += 8;
		}
		// Return only X,Y for GeoJSON (ignore Z and M)
		return [coord[0], coord[1]];
	}

	/**
	 * Parse Point geometry
	 */
	parsePoint(view, offset, littleEndian, dimensions) {
		const offsetObj = { value: offset };
		const coordinates = this.readCoordinate(
			view,
			offsetObj,
			littleEndian,
			dimensions
		);

		return {
			type: "Point",
			coordinates: coordinates,
		};
	}

	/**
	 * Parse LineString geometry
	 */
	parseLineString(view, offset, littleEndian, dimensions) {
		const numPoints = view.getUint32(offset, littleEndian);
		offset += 4;

		const coordinates = [];
		const offsetObj = { value: offset };

		for (let i = 0; i < numPoints; i++) {
			coordinates.push(
				this.readCoordinate(view, offsetObj, littleEndian, dimensions)
			);
		}

		return {
			type: "LineString",
			coordinates: coordinates,
		};
	}

	/**
	 * Parse Polygon geometry
	 */
	parsePolygon(view, offset, littleEndian, dimensions) {
		const numRings = view.getUint32(offset, littleEndian);
		offset += 4;

		const coordinates = [];
		const offsetObj = { value: offset };

		for (let r = 0; r < numRings; r++) {
			const numPoints = view.getUint32(offsetObj.value, littleEndian);
			offsetObj.value += 4;

			const ring = [];
			for (let i = 0; i < numPoints; i++) {
				ring.push(
					this.readCoordinate(
						view,
						offsetObj,
						littleEndian,
						dimensions
					)
				);
			}
			coordinates.push(ring);
		}

		return {
			type: "Polygon",
			coordinates: coordinates,
		};
	}

	/**
	 * Parse MultiPoint geometry
	 */
	parseMultiPoint(view, offset, littleEndian, dimensions) {
		const numPoints = view.getUint32(offset, littleEndian);
		offset += 4;

		const points = [];

		for (let i = 0; i < numPoints; i++) {
			// Each point has its own WKB header
			offset++; // Skip byte order
			offset += 4; // Skip geometry type

			const offsetObj = { value: offset };
			points.push(
				this.readCoordinate(view, offsetObj, littleEndian, dimensions)
			);
			offset = offsetObj.value;
		}

		return {
			type: "MultiPoint",
			coordinates: points,
		};
	}

	/**
	 * Parse MultiLineString geometry
	 */
	parseMultiLineString(view, offset, littleEndian, dimensions) {
		const numLineStrings = view.getUint32(offset, littleEndian);
		offset += 4;

		const lineStrings = [];

		for (let i = 0; i < numLineStrings; i++) {
			// Each LineString has its own WKB header
			offset++; // Skip byte order
			offset += 4; // Skip geometry type

			const numPoints = view.getUint32(offset, littleEndian);
			offset += 4;

			const coordinates = [];
			const offsetObj = { value: offset };

			for (let j = 0; j < numPoints; j++) {
				coordinates.push(
					this.readCoordinate(
						view,
						offsetObj,
						littleEndian,
						dimensions
					)
				);
			}

			lineStrings.push(coordinates);
			offset = offsetObj.value;
		}

		return {
			type: "MultiLineString",
			coordinates: lineStrings,
		};
	}

	/**
	 * Parse MultiPolygon geometry
	 */
	parseMultiPolygon(view, offset, littleEndian, dimensions) {
		const numPolygons = view.getUint32(offset, littleEndian);
		offset += 4;

		const polygons = [];

		for (let i = 0; i < numPolygons; i++) {
			// Each Polygon has its own WKB header
			offset++; // Skip byte order
			offset += 4; // Skip geometry type

			const numRings = view.getUint32(offset, littleEndian);
			offset += 4;

			const rings = [];
			const offsetObj = { value: offset };

			for (let r = 0; r < numRings; r++) {
				const numPoints = view.getUint32(offsetObj.value, littleEndian);
				offsetObj.value += 4;

				const ring = [];
				for (let j = 0; j < numPoints; j++) {
					ring.push(
						this.readCoordinate(
							view,
							offsetObj,
							littleEndian,
							dimensions
						)
					);
				}
				rings.push(ring);
			}

			polygons.push(rings);
			offset = offsetObj.value;
		}

		return {
			type: "MultiPolygon",
			coordinates: polygons,
		};
	}

	/**
	 * Parse GeometryCollection
	 */
	parseGeometryCollection(view, offset, littleEndian) {
		const numGeometries = view.getUint32(offset, littleEndian);
		offset += 4;

		const geometries = [];

		for (let i = 0; i < numGeometries; i++) {
			const wkbSlice = new Uint8Array(view.buffer, offset);
			const geom = this.parseWKB(wkbSlice);

			if (geom) {
				geometries.push(geom);
				// Calculate size of parsed geometry to advance offset
				// This is simplified - in production use proper size calculation
				offset += this.estimateWKBSize(geom);
			}
		}

		return {
			type: "GeometryCollection",
			geometries: geometries,
		};
	}

	/**
	 * Estimate WKB size for a geometry (simplified)
	 */
	estimateWKBSize(geom) {
		// This is a simplified estimation
		// In production, calculate exact size based on geometry
		let size = 5; // Header (1 byte order + 4 type)

		switch (geom.type) {
			case "Point":
				size += 16; // 2 coordinates * 8 bytes
				break;
			case "LineString":
				size += 4 + geom.coordinates.length * 16;
				break;
			case "Polygon":
				size += 4; // Number of rings
				geom.coordinates.forEach((ring) => {
					size += 4 + ring.length * 16;
				});
				break;
			// Add more cases as needed
		}

		return size;
	}
}

// Export for use
window.WKBParser = WKBParser;
