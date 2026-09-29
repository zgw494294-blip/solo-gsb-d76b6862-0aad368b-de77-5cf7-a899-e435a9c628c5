"""FastAPI 入口：提供定位计算接口并托管离线静态前端。"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .locating import solve, validate_payload

app = FastAPI(title='离线测距定位', version='1.0.0')

STATIC_DIR = Path(__file__).resolve().parent.parent / 'static'


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.post('/api/locate')
async def locate(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=422,
            content={'detail': {'_': '请求体不是有效的 JSON'}},
        )

    n, beacons, errors = validate_payload(payload)
    if errors:
        return JSONResponse(status_code=422, content={'detail': errors})

    return JSONResponse(solve(n, beacons))


@app.get('/')
def index():
    return FileResponse(STATIC_DIR / 'index.html')


app.mount('/', StaticFiles(directory=STATIC_DIR), name='static')
