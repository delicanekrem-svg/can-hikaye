"""Instagram Graph API ile hikaye (STORIES) paylaşır."""
import os
import time
import requests

SURUM = os.environ.get("GRAPH_SURUM", "v25.0")
GRAPH = f"https://graph.facebook.com/{SURUM}"


def _kontrol(r):
    if not r.ok:
        raise RuntimeError(f"Instagram API hatası {r.status_code}: {r.text[:500]}")
    return r.json()


def hikaye_paylas(ig_kullanici_id: str, token: str, gorsel_url: str) -> str:
    # 1) Kapsayıcı oluştur — Instagram görseli bu adresten kendisi indirir
    kap = _kontrol(requests.post(f"{GRAPH}/{ig_kullanici_id}/media", data={
        "image_url": gorsel_url, "media_type": "STORIES", "access_token": token}, timeout=60))["id"]

    # 2) Hazır olmasını bekle
    for _ in range(30):
        durum = _kontrol(requests.get(f"{GRAPH}/{kap}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30))
        if durum.get("status_code") == "FINISHED":
            break
        if durum.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Kapsayıcı hatası: {durum}")
        time.sleep(5)
    else:
        raise RuntimeError("Kapsayıcı zamanında hazır olmadı.")

    # 3) Yayınla
    return _kontrol(requests.post(f"{GRAPH}/{ig_kullanici_id}/media_publish", data={
        "creation_id": kap, "access_token": token}, timeout=60))["id"]
