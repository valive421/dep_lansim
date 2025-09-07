import requests
ip = requests.get('https://api.ipify.org').text
print("Your public IP is:", ip)