#!/usr/bin/env python3
"""Quick setup checker for Gemini live tests."""

import os

def check_gemini_setup():
    """Check if Gemini API key is configured."""
    
    print("🔍 Checking Gemini Live Test Setup...")
    print()
    
    # Check for API key
    api_key = (
        os.getenv("ISTINA_GEMINI_API_KEY") or 
        os.getenv("GEMINI_API_KEY") or 
        os.getenv("gemini_api_key")
    )
    
    if api_key:
        print("✅ API Key: Found")
        print(f"   Key length: {len(api_key)} characters")
        print(f"   Starts with: {api_key[:8]}...")
    else:
        print("❌ API Key: Not found")
        print()
        print("To set up your API key:")
        print("1. Get API key from: https://makersuite.google.com/app/apikey")
        print("2. Set environment variable:")
        print("   export ISTINA_GEMINI_API_KEY='your-key-here'")
        print("   # OR")
        print("   $env:ISTINA_GEMINI_API_KEY='your-key-here'  # PowerShell")
        print()
        print("3. Run live tests:")
        print("   pytest tests/test_providers/test_gemini_live_smoke.py -v -s")
        return False
    
    print()
    print("🚀 Ready to run live tests!")
    print("Commands:")
    print("  # Run all live tests")
    print("  pytest tests/test_providers/test_gemini_live_smoke.py -v -s")
    print()
    print("  # Run just basic functionality test")
    print("  pytest tests/test_providers/test_gemini_live_smoke.py::TestGeminiLiveIntegration::test_live_analysis_basic_functionality -v -s")
    print()
    print("⚠️  Note: These tests make real API calls and cost money!")
    
    return True

if __name__ == "__main__":
    check_gemini_setup()