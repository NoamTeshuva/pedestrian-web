# Scripts Directory

Utility scripts for managing the Pedestrian Volume Prediction application.

## upload_to_vultr.py

Upload ML models to Vultr Object Storage.

### Prerequisites

```bash
pip install boto3
```

### Setup

1. **Create Vultr Object Storage bucket** (see VULTR_STORAGE_GUIDE.md)

2. **Set environment variables:**

```bash
export VULTR_ACCESS_KEY="your-access-key-here"
export VULTR_SECRET_KEY="your-secret-key-here"
export VULTR_ENDPOINT="https://ewr1.vultrobjects.com"  # Your region
export VULTR_BUCKET="pedestrian-models"
```

### Usage

**Upload all models:**
```bash
python scripts/upload_to_vultr.py
```

**Upload specific file:**
```bash
python scripts/upload_to_vultr.py --file api/models/cb_model.cbm
```

**Verify existing uploads:**
```bash
python scripts/upload_to_vultr.py --verify-only
```

### What it does

- Finds all `.cbm` model files in `api/models/`
- Uploads them to `models/` prefix in Vultr bucket
- Verifies successful upload
- Reports any failures

### After Upload

Once models are uploaded to Vultr:

1. **Update Render environment variables:**
   - Go to Render Dashboard → Your Service → Environment
   - Add `VULTR_ACCESS_KEY` (secret)
   - Add `VULTR_SECRET_KEY` (secret)
   - Set `USE_VULTR_STORAGE=true`

2. **Redeploy on Render:**
   - Models will now be fetched from Vultr on startup
   - Cached in `/tmp/models/` during container lifetime

3. **(Optional) Remove models from Git:**
   ```bash
   # Models are on Vultr now, no need in repo
   git rm --cached api/models/*.cbm
   echo "api/models/*.cbm" >> .gitignore
   git commit -m "chore: move models to Vultr storage"
   ```

## Security Notes

- Never commit credentials to git
- Use environment variables only
- Keep `.env` files in `.gitignore`
- Rotate access keys periodically
