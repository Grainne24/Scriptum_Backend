"""
Test what the API is actually returning
"""
import requests

API_URL = "https://scriptum-api.onrender.com" 

def test_analysed_endpoint():
    print("Testing /books/analysed endpoint...\n")
    
    try:
        response = requests.get(f"{API_URL}/books/analysed?limit=1")
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
    test_analysed_endpoint()