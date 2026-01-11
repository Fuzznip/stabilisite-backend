import subprocess
import json

API_URL = "http://localhost:8000/v2/challenges"
TASK_ID = "15b5f739-e103-4bc3-b22e-30eaf5762830"
TRIGGER_ID = "f1904b22-7a1b-4cc6-9df1-9fd7bea0fe2d"
PARENT_CHALLENGE_ID = "b995c343-a4d1-4301-a840-d8acdc358297"

def curl_post(url, data):
    """Make a POST request using curl"""
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', url, '-H', 'Content-Type: application/json', '-d', json.dumps(data)],
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout:
        try:
            response = json.loads(result.stdout)
            if 'error' in response:
                print(f"    API Error: {response['error']}")
                return None
            return response
        except:
            print(f"    Failed to parse response: {result.stdout}")
            return None
    return None

payload = {
    "task_id": TASK_ID,
    "trigger_id": TRIGGER_ID,
    "parent_challenge_id": PARENT_CHALLENGE_ID,
    "quantity": 1,
    "require_all": False,
}

response = curl_post(API_URL, payload)

print("Status:", response.status_code)

try:
    print("Response:", response.json())
except ValueError:
    print("Raw response:", response.text)
