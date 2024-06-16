from fastapi import FastAPI, HTTPException, Request, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import pandas as pd
from app import models, database

app = FastAPI()

# 정적 파일 설정
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿 설정
templates = Jinja2Templates(directory="templates")

# 데이터베이스 테이블 생성
models.Base.metadata.create_all(bind=database.engine)

# 엑셀 파일 경로
file_path = 'data/location_data.xlsx'

# 엑셀 파일 읽기
df = pd.read_excel(file_path)
df_selected = df[['1단계', '2단계', '격자 X', '격자 Y', '경도(시)', '경도(분)', '경도(초)', '위도(시)', '위도(분)', '위도(초)']]
df_unique = df_selected.drop_duplicates(subset=['1단계', '2단계'])

# 고유 지역 추출
region_list = df_unique['1단계'].unique().tolist()

# 루트 엔드포인트 - 기본 lat와 lon을 사용하여 리디렉션
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(database.get_db)):
    # 청주시 서원구의 위도와 경도
    lat = 36.642434
    lon = 127.489031
    place = "청주시 서원구"
    comments = db.query(models.Comment).filter(models.Comment.region == place).all()
    return templates.TemplateResponse("main.html", {
        "request": request,
        "comments": comments,
        "region": place,
        "regions": region_list,
        "lat": lat,
        "lon": lon,
        "place": place
    })

# 지역별 댓글 표시 엔드포인트
@app.get("/comments/{region}", response_class=HTMLResponse)
async def read_comments_by_region(request: Request, region: str, lat: float = None, lon: float = None, place: str = None, db: Session = Depends(database.get_db)):
    comments = db.query(models.Comment).filter(models.Comment.region == region).all()
    return templates.TemplateResponse("main.html", {
        "request": request,
        "comments": comments,
        "region": region,
        "regions": region_list,
        "lat": lat,
        "lon": lon,
        "place": place
    })

# 특정 지역에 댓글 작성 엔드포인트
@app.post("/comments/{region}/add", response_class=RedirectResponse)
async def create_comment_by_region(region: str, name: str = Form(...), comment: str = Form(...), lat: float = None, lon: float = None, db: Session = Depends(database.get_db)):
    db_comment = models.Comment(name=name, comment=comment, region=region)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    # 특정 지역의 댓글 페이지로 리디렉션
    return RedirectResponse(url=f"/comments/{region}?lat={lat}&lon={lon}&place={region}", status_code=303)

# location_search.html 제공 엔드포인트
@app.get("/location_search", response_class=HTMLResponse)
async def location_search(request: Request):
    return templates.TemplateResponse("location_search.html", {"request": request})

# main.html 직접 제공 엔드포인트 (일반적으로 필요하지 않지만 포함)
@app.get("/main.html", response_class=HTMLResponse)
async def read_main():
    with open("templates/main.html", "r", encoding="utf-8") as file:
        return HTMLResponse(content=file.read(), status_code=200)

# location_search.html 직접 제공 엔드포인트 (일반적으로 필요하지 않지만 포함)
@app.get("/location_search.html", response_class=HTMLResponse)
async def read_location_search():
    with open("templates/location_search.html", "r", encoding="utf-8") as file:
        return HTMLResponse(content=file.read(), status_code=200)

# 위치 검색 엔드포인트
@app.get("/search")
def search(query: str):
    query = query.lower()
    results = df_unique[(df_unique['1단계'].str.contains(query, case=False, na=False)) | 
                        (df_unique['2단계'].str.contains(query, case=False, na=False))]
    
    places = results[['1단계', '2단계']].drop_duplicates().apply(lambda row: " ".join(row.dropna()), axis=1).tolist()
    return {"places": places}

# 위치 좌표 엔드포인트
@app.get("/coordinates")
def coordinates(lat: float = None, lon: float = None, place: str = None):
    if place:
        place_parts = place.split()
        if len(place_parts) == 1:
            results = df_unique[df_unique['1단계'].str.contains(place_parts[0], case=False, na=False)]
        elif len(place_parts) == 2:
            results = df_unique[(df_unique['1단계'].str.contains(place_parts[0], case=False, na=False)) & 
                                (df_unique['2단계'].str.contains(place_parts[1], case=False, na=False))]
        else:
            raise HTTPException(status_code=400, detail="Invalid place format")
        
        if not results.empty:
            result = results.iloc[0]
            nx, ny = result['격자 X'], result['격자 Y']
            lat = result['위도(시)'] + result['위도(분)'] / 60 + result['위도(초)'] / 3600
            lon = result['경도(시)'] + result['경도(분)'] / 60 + result['경도(초)'] / 3600
            return {"coordinates": {"lat": lat, "lon": lon}}
        else:
            raise HTTPException(status_code=404, detail="Location not found")
    elif lat is not None and lon is not None:
        results = df_unique[(df_unique['위도(시)'] + df_unique['위도(분)'] / 60 + df_unique['위도(초)'] / 3600 == lat) &
                            (df_unique['경도(시)'] + df_unique['경도(분)'] / 60 + df_unique['경도(초)'] / 3600 == lon)]
        if not results.empty:
            result = results.iloc[0]
            place = result['1단계']
            if pd.notna(result['2단계']):
                place += ' ' + result['2단계']
            return {"place": place}
        else:
            raise HTTPException(status_code=404, detail="Location not found")
    else:
        raise HTTPException(status_code=400, detail="Either 'place' or both 'lat' and 'lon' must be provided")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=5500, reload=True)
