import socket
import requests

def check_ip_status():
    ip = requests.get('https://api.ipify.org').text
    rbl_check = requests.get(f"https://www.google.com/appsstatus/dashboard/?checkip={ip}")
    return "blocked" if "421" in rbl_check.text else "clean"

print(check_ip_status())