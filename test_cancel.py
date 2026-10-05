import requests

url = 'http://127.0.0.1:8000/cancel-order/fake-id?username=admin&password=fake'
response = requests.delete(url)
print("Status Code:", response.status_code)
print("Response Body:", response.text)
