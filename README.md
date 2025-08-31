# Standalone Pedestrian Web

A standalone web application for predicting pedestrian volume with an interactive map interface.

## Project Structure

```
/
├── api/                         # Flask backend API
│   ├── app.py                  # Main Flask application
│   ├── requirements.txt        # Python dependencies
│   ├── osm_tiles.py           # OpenStreetMap data utilities
│   ├── __init__.py            # Package marker
│   ├── feature_engineering/    # ML feature processing
│   └── models/                # CatBoost models (Git LFS)
│       └── *.cbm             
├── frontend/                   # Web frontend
│   ├── index.html            # Main HTML page
│   ├── script.js             # Frontend application logic
│   ├── styles.css            # Styling
│   └── lib/
│       └── api.js            # API client library
├── .gitignore                 # Git ignore rules
├── .gitattributes            # Git LFS configuration
└── README.md                 # This file
```

## Quick Start

Run these two commands in separate terminals:

**Backend:**
```bash
cd api && python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt && python app.py
```

**Frontend:**
```bash
cd frontend && python -m http.server 3000 --bind 127.0.0.1
```

Then open `http://localhost:3000` in your browser.

## Local Development

This project consists of two services that run independently:
- **Backend**: Flask API server on port 8000
- **Frontend**: Static web files served locally on port 3000

### Prerequisites

- Python 3.8+ 
- Git LFS (for model files): `git lfs install`

### Backend Setup

1. **Navigate to API directory and set up environment**:
   ```bash
   cd api
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1  # Windows PowerShell
   # OR: source .venv/bin/activate  # macOS/Linux
   pip install -r requirements.txt
   ```

2. **Run the Flask server**:
   ```bash
   python app.py
   ```

   The API will be available at `http://127.0.0.1:8000`

### Frontend Setup

1. **Navigate to frontend directory**:
   ```bash
   cd frontend
   ```

2. **Serve the frontend files**:
   ```bash
   python -m http.server 3000 --bind 127.0.0.1
   ```

   The frontend will be available at `http://localhost:3000`

## API Endpoints

The Flask backend provides the following endpoints:

### Health Check
- **GET** `/health` - Returns API status
- **GET** `/ping` - Simple ping endpoint

### Predictions
- **GET** `/predict?place={city_name}` - Get pedestrian volume predictions for a city
  - **Parameters**:
    - `place` (required): City name (e.g., "Monaco", "Tel Aviv")
  - **Response**: GeoJSON with prediction data

- **POST** `/predict-batch` - Batch prediction endpoint for CatBoost model
  - **Request Body**: JSON with `{"items": [{"edge_id": 1, "betweenness": 0.3, "closeness": 0.1, "Hour": 8, "is_weekend": 0, "time_of_day": "morning", "land_use": "retail", "highway": "primary"}, ...]}` 
  - **Response**: JSON with predictions and probabilities

- **GET** `/predict-sample` - Quick demo endpoint with hardcoded examples
  - **Response**: JSON with sample predictions for 2 street segments

### Network Data
- **GET** `/base-network?place={city_name}` - Get base street network
- **POST** `/simulate` - Simulate pedestrian volume with network modifications

## Testing

Test the setup with these curl commands:

```bash
# Health check
curl "http://127.0.0.1:8000/health"

# Get predictions
curl "http://127.0.0.1:8000/predict?place=Monaco"

# Batch prediction
curl -X POST "http://127.0.0.1:8000/predict-batch" -H "Content-Type: application/json" --data-binary '{"items":[{"edge_id":1,"betweenness":0.3,"closeness":0.1,"Hour":8,"is_weekend":0,"time_of_day":"morning","land_use":"retail","highway":"primary"}]}'

# Quick sample prediction (no JSON required)
curl "http://127.0.0.1:8000/predict-sample"
```

## Environment Configuration

The frontend uses environment variables to configure the API URL:

- **Development**: Edit `frontend/.env.local`
- **Production**: Set `VITE_API_URL` or `REACT_APP_API_URL`

Default API URL: `http://127.0.0.1:8000`

## Development Workflow

1. Start the backend server (Flask API on port 8000)
2. Start the frontend server (static files on port 3000)
3. Open `http://localhost:3000` in your browser
4. The frontend will automatically connect to the backend API

## Troubleshooting

### CORS Issues
If you see CORS errors, make sure:
- The backend is running on port 8000
- The frontend is accessing from an allowed origin (localhost:3000, etc.)

### API Connection Issues
If the frontend can't connect to the API:
- Check that Flask server is running on `http://127.0.0.1:8000`
- Verify the API_BASE_URL in the browser console
- Test the `/health` endpoint directly

### Port Conflicts
If ports 8000 or 3000 are in use:
- **Backend**: Set `FLASK_PORT` environment variable
- **Frontend**: Use a different port for your static server

## Model and Feature Engineering

This project now includes the complete ML pipeline from the legacy repository:

### CatBoost Models
- **cb_loco_train_dublin_melbourne_nyc_test_zurich.cbm** - Current active model (LOCO trained on Dublin, Melbourne, NYC, tested on Zurich)
- **cb_model.cbm** - Original pedestrian volume prediction model
- **cb_model_four_city.cbm** - Four-city trained model
- **cb_model_multi_city.cbm** - Multi-city trained model

Models are stored in `api/models/` and tracked with Git LFS.

### Feature Engineering Pipeline
The `api/feature_engineering/` module provides:
- **feature_pipeline.py** - Unified feature extraction pipeline
- **centrality_features.py** - Network centrality calculations
- **highway_features.py** - Road type and highway features  
- **landuse_features.py** - Land use and urban context features
- **time_features.py** - Temporal features (hour, weekend, time of day)

### OSM Network Integration
- **osm_tiles.py** - OpenStreetMap network extraction utilities

## API Architecture

The Flask API integrates the full ML pipeline:
- Real CatBoost model predictions for `/predict` endpoint
- Batch inference through `/predict-batch` 
- Network simulation capabilities via `/simulate`
- Full feature engineering pipeline with geospatial data processing

## Next Steps

- [ ] Add authentication if needed
- [ ] Implement caching for better performance
- [ ] Add comprehensive error handling  
- [ ] Write unit tests
- [ ] Add monitoring and logging
