#!/usr/bin/env python3
"""
Test script to verify n8n webhook connectivity
Usage: python test_webhook.py /path/to/resume.pdf
"""

import sys
import requests
import os

def test_webhook(resume_path, provider="claude"):
    """Test the n8n resume parser webhook"""
    
    webhook_url = os.getenv('N8N_WEBHOOK_URL', 'http://localhost:5678/webhook/parse-resume')
    
    print(f"Testing webhook: {webhook_url}")
    print(f"Provider: {provider}")
    print(f"Resume: {resume_path}")
    print("-" * 50)
    
    try:
        # Open and send file
        with open(resume_path, 'rb') as f:
            files = {'file': (os.path.basename(resume_path), f)}
            data = {'provider': provider}
            
            print("Sending request...")
            response = requests.post(webhook_url, files=files, data=data, timeout=30)
            
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
        print("Usage: python test_webhook.py /path/to/resume.pdf [provider]")
        print("Example: python test_webhook.py resume.pdf claude")
        sys.exit(1)
    
    resume_path = sys.argv[1]
    provider = sys.argv[2] if len(sys.argv) > 2 else "claude"
    
    if not os.path.exists(resume_path):
        print(f"Error: File not found: {resume_path}")
        sys.exit(1)
    
    success = test_webhook(resume_path, provider)
    sys.exit(0 if success else 1)
