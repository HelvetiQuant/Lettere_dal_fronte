import requests

BASE_URL = "http://decoratialvalormilitare.istitutonastroazzurro.org"
SEARCH_URL = f"{BASE_URL}/XMLHttp/getDatas.php"

params = {
    "all_arma": "0",
    "id_arma": "1",
    "nome": "",
    "cognome": "A",
    "anno_nascita": "",
    "anno_decorazione": "",
    "tipo_decorazione": "",
    "anno_volume": "",
}

resp = requests.post(SEARCH_URL, data=params, timeout=30,
                    headers={"Content-Type": "application/x-www-form-urlencoded",
                            "User-Agent": "Mozilla/5.0"})
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('Content-Type')}")
print(f"Length: {len(resp.text)}")
print("---FIRST 3000 CHARS---")
print(resp.text[:3000])
print("---LAST 1000 CHARS---")
print(resp.text[-1000:])
