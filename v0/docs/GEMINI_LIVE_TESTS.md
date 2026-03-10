# Gemini Live Smoke Tests Setup Guide

This guide will help you set up and run live integration tests with the real Gemini API.

## ⚠️ Important Warnings

- **These tests cost money** - they make real API calls to Google Gemini
- **Rate limits apply** - Gemini has usage quotas and rate limits
- **Test responsibly** - Start with single tests before running the full suite

## 🔧 Setup Instructions

### Step 1: Get Your Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Create a new API key
4. Copy the key (it looks like: `AIzaSyA...`)

### Step 2: Configure Environment Variable

Choose your platform:

**Windows PowerShell:**
```powershell
$env:ISTINA_GEMINI_API_KEY="your-actual-api-key-here"
```

**Windows Command Prompt:**
```cmd
set ISTINA_GEMINI_API_KEY=your-actual-api-key-here
```

**Linux/macOS:**
```bash
export ISTINA_GEMINI_API_KEY="your-actual-api-key-here"
```

**Or create a .env file:**
```bash
# Add to .env file in project root
ISTINA_GEMINI_API_KEY=your-actual-api-key-here
```

### Step 3: Verify Setup

Run the setup checker:
```bash
python check_live_setup.py
```

You should see:
```
✅ API Key: Found
   Key length: 39 characters
   Starts with: AIzaSyA...

🚀 Ready to run live tests!
```

## 🧪 Running Live Tests

### Check Test Status
See which tests will run:
```bash
pytest tests/test_providers/test_gemini_live_smoke.py --collect-only
```

### Run Single Test (Recommended First)
Start with the basic functionality test:
```bash
pytest tests/test_providers/test_gemini_live_smoke.py::TestGeminiLiveIntegration::test_live_analysis_basic_functionality -v -s
```

### Run All Live Tests
Once the single test works:
```bash
pytest tests/test_providers/test_gemini_live_smoke.py -v -s
```

### Run Specific Test Categories
```bash
# Just the parsing validation
pytest tests/test_providers/test_gemini_live_smoke.py::TestGeminiLiveIntegration::test_live_detailed_parsing_validation -v -s

# Just the rate limiting test  
pytest tests/test_providers/test_gemini_live_smoke.py::TestGeminiLiveIntegration::test_live_rate_limiting_functionality -v -s
```

## 📊 What The Tests Do

### 1. `test_live_analysis_basic_functionality`
- Makes real API calls to Gemini
- Tests complete parsing pipeline
- Verifies BiasScore structure
- **Cost: ~2 API calls**

### 2. `test_live_rate_limiting_functionality` 
- Tests rate limiting with 3 sequential requests
- Verifies timing and throttling
- **Cost: ~6 API calls**

### 3. `test_live_repository_integration`
- Tests analysis + storage + retrieval workflow
- Validates data persistence
- **Cost: ~2 API calls**

### 4. `test_live_detailed_parsing_validation`
- Tests with different content types (neutral vs opinion)
- Validates parsing robustness
- **Cost: ~4 API calls**

**Total test suite cost: ~14 API calls**

## 🔍 Expected Output

When tests run successfully, you'll see:
```
🔥 LIVE TEST: Testing with real Gemini API
Article: Local Government Reviews Infrastructure Spending
API Key present: Yes

📊 Analysis completed in 2.34s
   Bias Label: center
   Confidence: 0.6
   Rhetorical Flags: []
   Claims Found: 3
   Raw response keys: ['bias_call', 'claims_call', 'model']

✅ Live analysis successful!
```

## 🚨 Troubleshooting

### Tests Get Skipped
```
SKIPPED [100%] LIVE TEST: Set ISTINA_GEMINI_API_KEY...
```
**Solution:** API key not configured. Check Step 2 above.

### Authentication Error
```
ProviderError: Gemini API returned status 403
```
**Solution:** Invalid API key. Get a new one from Google AI Studio.

### Rate Limit Error
```
ProviderError: Gemini API returned status 429
```
**Solution:** Wait a few minutes and try again. Reduce test frequency.

### Network Error
```
httpx.NetworkError: ...
```
**Solution:** Check internet connection. Try again later.

## 🏃‍♂️ Quick Start Commands

```bash
# 1. Check setup
python check_live_setup.py

# 2. Run one test to verify everything works
pytest tests/test_providers/test_gemini_live_smoke.py::TestGeminiLiveIntegration::test_live_analysis_basic_functionality -v -s

# 3. If successful, run all tests
pytest tests/test_providers/test_gemini_live_smoke.py -v -s
```

## 💡 Tips for Development

- **Start small**: Run single tests first
- **Set conservative rate limits**: Use low RPM for testing
- **Monitor costs**: Keep track of API usage in Google Cloud Console
- **Test incrementally**: Don't run full suites repeatedly during development
- **Use mocked tests**: Use `test_gemini_provider.py` for most development work

Happy testing! 🚀