"""Local country lookup with explicit unknown/unavailable outcomes."""
import ipaddress
from pathlib import Path
import re
import threading

from fastapi import FastAPI, HTTPException, Response
import maxminddb

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
DATABASE = Path('/data/GeoLite2-Country.mmdb')
_reader = None
_generation = None
_lock = threading.Lock()


def lookup(ip=None):
    global _reader, _generation
    with _lock:
        try:
            stat = DATABASE.stat()
            generation = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
            if generation != _generation:
                if _reader is not None:
                    _reader.close()
                _reader, _generation = None, None
                opened = maxminddb.open_database(str(DATABASE))
                if opened.metadata().database_type not in {'GeoLite2-Country','GeoIP2-Country'}:
                    opened.close()
                    raise ValueError('Invalid country database')
                _reader, _generation = opened, generation
            return _reader.get(ip) if ip is not None else None
        except (OSError, ValueError, maxminddb.errors.InvalidDatabaseError):
            raise HTTPException(503, 'Country database unavailable') from None


@app.get('/healthz')
def healthz():
    lookup()
    return {'status':'ok'}


@app.get('/v1/ip/country/{ip}')
def get_country(ip: str):
    try:
        address = ipaddress.ip_address(ip)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
    except ValueError:
        raise HTTPException(400, 'Invalid IP address') from None
    record = lookup(str(address))
    if not record or 'country' not in record or 'iso_code' not in record['country']:
        raise HTTPException(404, 'Country unknown')
    country = record['country']['iso_code']
    if not isinstance(country,str) or not re.fullmatch('[A-Z]{2}',country):
        raise HTTPException(503, 'Invalid country record')
    return Response(content=country, media_type='text/plain', headers={'Cache-Control':'no-store'})
