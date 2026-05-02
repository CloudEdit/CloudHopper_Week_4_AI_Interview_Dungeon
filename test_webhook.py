#!/usr/bin/env python3
"""
Test script to verify n8n webhook connectivity.
Usage: python test_webhook.py '<resume_text>' [provider]
"""

import sys
import requests
import os


def test_webhook(resume_text, provider="claude"):
    """Test the n8n resume parser webhook with plain text"""

    webhook_url = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook-test/parse-resume')

    print(f"Testing webhook: {webhook_url}")
    print(f"Provider: {provider}")
    print(f"Resume text length: {len(resume_text)} characters")
    print("-" * 50)

    try:
        data = {
            'resumeText': resume_text,
            'provider': provider
        }

        print("Sending request...")
        response = requests.post(webhook_url, json=data, timeout=30)

        print(f"Status Code: {response.status_code}")
        print("-" * 50)

        if response.status_code == 200:
            result = response.json()

            print("✅ SUCCESS!")
            print("-" * 50)
            print("Parsed Resume Data:")
            print(f"  Skills: {len(result.get('skills', []))} found")
            print(f"  Experience: {len(result.get('experience', []))} entries")
            print(f"  Education: {len(result.get('education', []))} entries")

            if result.get('skills'):
                print(f"\n  Top Skills: {', '.join(result['skills'][:5])}")

            if result.get('error'):
                print(f"\n⚠️  Warning: {result['error']}")

            return True
        else:
            print("❌ FAILED!")
            print(response.text)
            return False

    except requests.exceptions.Timeout:
        print("❌ TIMEOUT - Webhook took too long to respond")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ CONNECTION ERROR - Is n8n running?")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_webhook.py '<resume_text>' [provider]")
        print("Example: python test_webhook.py 'Senior Developer with 5 years Python experience...' claude")
        sys.exit(1)

    resume_text = sys.argv[1]
    provider = sys.argv[2] if len(sys.argv) > 2 else "claude"

    success = test_webhook(resume_text, provider)
    sys.exit(0 if success else 1)
