from fastapi import FastAPI, Response
import maxminddb

app = FastAPI()
_reader = None

def get_reader():
    global _reader
    if _reader is None:
        _reader = maxminddb.open_database("/data/GeoLite2-Country.mmdb")
    return _reader

@app.get("/v1/ip/country/{ip}")
def get_country(ip: str):
    try:
        record = get_reader().get(ip)
        if record and "country" in record:
            return Response(content=record["country"]["iso_code"], media_type="text/plain")
    except Exception:
        pass
    return Response(content="", media_type="text/plain")
