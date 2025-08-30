#!/usr/bin/env python3
"""
Pedestrian Volume Prediction API
Standalone Flask backend for the pedestrian web frontend
"""

import os
import sys
from pathlib import Path

# Add the parent directory to Python path for imports
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS configuration for local development
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:5173", "http://127.0.0.1:5173",  # Vite dev
            "http://localhost:3000", "http://127.0.0.1:3000",  # CRA dev
            "http://localhost:3001", "http://127.0.0.1:3001",  # Alternative port
            "http://localhost:8080", "http://127.0.0.1:8080",  # Alternative port
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "pedestrian-api", "port": 8000})

@app.route("/ping", methods=["GET"])
def ping():
    """Simple ping endpoint."""
    return jsonify({"pong": True})

# === BEGIN LEGACY INTEGRATION AREA =========================================
# This is where the legacy app.py logic will be integrated

@app.route("/predict", methods=["GET"])
def predict():
    """
    Predict pedestrian volume bins for the given place.
    
    Query Parameters:
        place (str, required): Place name (e.g., "Monaco", "Tel Aviv")
        
    Returns:
        JSON response with predictions and metadata
    """
    logger.info("Received prediction request")
    
    place = request.args.get("place")
    if not place:
        return jsonify({
            "error": "Missing required parameter 'place'",
            "code": 400
        }), 400
    
    logger.info(f"Predicting for place: {place}")
    
    # TODO: Integrate legacy prediction logic here
    # For now, return a mock response that matches frontend expectations
    
    mock_response = {
        "success": True,
        "location": place,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "processing_time": 1.5,
        "network_stats": {
            "n_edges": 150,
            "n_nodes": 120,
            "total_length_km": 12.5
        },
        "sample_prediction": {
            "volume_bin": 3,
            "features": {
                "Hour": 14,
                "is_weekend": False,
                "time_of_day": "afternoon",
                "highway": "residential",
                "land_use": "commercial"
            }
        },
        "validation": {
            "warnings": []
        },
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[7.418, 43.728], [7.420, 43.730]]
                    },
                    "properties": {
                        "volume_bin": 3,
                        "highway": "residential",
                        "land_use": "commercial",
                        "length": 150,
                        "osmid": "12345"
                    }
                },
                {
                    "type": "Feature", 
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[7.420, 43.730], [7.422, 43.732]]
                    },
                    "properties": {
                        "volume_bin": 2,
                        "highway": "tertiary",
                        "land_use": "residential", 
                        "length": 200,
                        "osmid": "12346"
                    }
                }
            ]
        }
    }
    
    return jsonify(mock_response)

@app.route("/base-network", methods=["GET"])
def base_network():
    """Get OSM walk network edges."""
    logger.info("Received base-network request")
    
    place = request.args.get("place")
    bbox = request.args.get("bbox")
    
    if not place and not bbox:
        return jsonify({"error": "provide ?place=... or ?bbox=w,s,e,n"}), 400
    
    # TODO: Integrate legacy base-network logic here
    
    # Mock response for now
    mock_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString", 
                    "coordinates": [[7.418, 43.728], [7.420, 43.730]]
                },
                "properties": {
                    "edge_id": "e_001",
                    "highway": "residential",
                    "length": 150,
                    "osmid": "12345"
                }
            }
        ]
    }
    
    return jsonify(mock_geojson)

@app.route("/simulate", methods=["POST"])
def simulate():
    """Simulate pedestrian volume with network edits."""
    logger.info("Received simulate request")
    
    try:
        payload = request.get_json(silent=True) or {}
        place = payload.get("place")
        bbox = payload.get("bbox")
        edits = payload.get("edits", [])
        
        if not place and not bbox:
            return jsonify({"error": "provide 'place' or 'bbox'"}), 400
        
        # TODO: Integrate legacy simulation logic here
        
        # Mock response for now
        mock_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[7.418, 43.728], [7.420, 43.730]]
                    },
                    "properties": {
                        "edge_id": "e_001",
                        "pred_before": 50.0,
                        "pred_after": 75.0,
                        "delta": 25.0
                    }
                }
            ]
        }
        
        return jsonify(mock_geojson)
        
    except Exception as e:
        logger.error(f"Simulate error: {e}")
        return jsonify({"error": str(e)}), 500

# === END LEGACY INTEGRATION AREA ===========================================

if __name__ == "__main__":
    # Development server configuration
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "8000"))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    
    logger.info(f"Starting Flask development server on {host}:{port}")
    app.run(host=host, port=port, debug=debug)