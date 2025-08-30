# Standalone Pedestrian Web

A standalone web application for predicting pedestrian volume with an interactive map interface.

## Project Structure

```
/
├── api/                    # Flask backend API
│   ├── app.py             # Main Flask application
│   └── requirements.txt   # Python dependencies
├── frontend/              # Web frontend
│   ├── index.html         # Main HTML page
│   ├── script.js          # Frontend application logic
│   ├── styles.css         # Styling
│   ├── lib/
│   │   └── api.js         # API client library
│   └── .env.local         # Environment configuration
└── README.md
```

## Local Development

This project consists of two services that run independently:
- **Backend**: Flask API server on port 8000
- **Frontend**: Static web files served locally

### Backend Setup

1. **Navigate to API directory**:
   ```bash
   cd api
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .venv
   ```

3. **Activate virtual environment**:
   - **macOS/Linux**:
     ```bash
     source .venv/bin/activate
     ```
   - **Windows**:
     ```bash
     .venv\Scripts\activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the Flask server**:
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
   
   You can use any static file server. Here are a few options:

   **Option A: Python HTTP server**:
   ```bash
   # Python 3
   python -m http.server 3000
   
   # Python 2
   python -m SimpleHTTPServer 3000
   ```

   **Option B: Node.js http-server**:
   ```bash
   # Install globally (one time)
   npm install -g http-server
   
   # Serve files
   http-server -p 3000 -c-1
   ```

   **Option C: Live Server (VS Code extension)**:
   - Install the "Live Server" extension in VS Code
   - Right-click on `index.html` and select "Open with Live Server"

   The frontend will be available at `http://localhost:3000` (or whatever port you chose)

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

# Test with bbox
curl "http://127.0.0.1:8000/predict?place=Tel Aviv"
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

## Next Steps

- [ ] Integrate full ML pipeline from legacy `app.py`
- [ ] Add authentication if needed
- [ ] Implement caching for better performance
- [ ] Add comprehensive error handling
- [ ] Write unit tests
