"""
Test what the API is actually returning
"""
import requests

API_URL = "https://scriptum-api.onrender.com" 

def test_analyzed_endpoint():
    print("Testing /books/analyzed endpoint...\n")
    
    try:
        response = requests.get(f"{API_URL}/books/analyzed?limit=1")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}\n")
        
        if response.status_code == 200:
            data = response.json()
            if data:
                print("First book structure:")
                for key, value in data[0].items():
                    print(f"  {key}: {type(value).__name__} = {str(value)[:50]}")
            else:
                print("No books returned!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_analyzed_endpoint()