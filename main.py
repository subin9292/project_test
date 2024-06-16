from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import pandas as pd
import logging
from app import models, database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Static files configuration
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates configuration
templates = Jinja2Templates(directory="templates")

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

# Excel file path
file_path = 'data/location_data.xlsx'

# Read Excel file
df = pd.read_excel(file_path)
df_selected = df[['1단계', '2단계', '격자 X', '격자 Y', '경도(시)', '경도(분)', '경도(초)', '위도(시)', '위도(분)', '위도(초)']]
df_unique = df_selected.drop_duplicates(subset=['1단계', '2단계'])

# Extract unique regions
region_list = df_unique['1단계'].unique().tolist()

# Root endpoint - redirects to default region (서울 in this example)
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, lat: float = 37.5665, lon: float = 126.9780, db: Session = Depends(database.get_db)):
    place = "서울"
    comments = []
    region_result = df_unique[
        (df_unique['위도(시)'] + df_unique['위도(분)'] / 60 + df_unique['위도(초)'] / 3600 == lat) & 
        (df_unique['경도(시)'] + df_unique['경도(분)'] / 60 + df_unique['경도(초)'] / 3600 == lon)
    ]
    if not region_result.empty:
        place = region_result.iloc[0]['1단계']
        comments = db.query(models.Comment).filter(models.Comment.region == place).all()
    logger.info(f"Root access with lat: {lat}, lon: {lon}, resolved place: {place}")
    return templates.TemplateResponse("main.html", {
        "request": request,
        "comments": comments,
        "region": place,
        "regions": region_list,
        "lat": lat,
        "lon": lon,
        "place": place
    })

# Endpoint to display comments by region
@app.get("/comments/{region}", response_class=HTMLResponse)
async def read_comments_by_region(request: Request, region: str, db: Session = Depends(database.get_db)):
    comments = db.query(models.Comment).filter(models.Comment.region == region).all()
    logger.info(f"Fetched comments for region: {region}, Count: {len(comments)}")
    return templates.TemplateResponse("main.html", {
        "request": request,
        "comments": comments,
        "region": region,
        "regions": region_list
    })

# Endpoint to create comments for a specific region
@app.post("/comments/{region}/add", response_class=RedirectResponse)
async def create_comment_by_region(region: str, name: str = Form(...), comment: str = Form(...), db: Session = Depends(database.get_db)):
    logger.info(f"Received new comment for region: {region} - Name: {name}, Comment: {comment}")
    db_comment = models.Comment(name=name, comment=comment, region=region)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return RedirectResponse(url=f"/comments/{region}", status_code=303)

# Endpoint serving location_search.html
@app.get("/location_search", response_class=HTMLResponse)
async def location_search(request: Request):
    return templates.TemplateResponse("location_search.html", {"request": request})

# Endpoint to serve main.html directly (not typically needed but included for completeness)
@app.get("/main.html", response_class=HTMLResponse)
async def read_main():
    with open("templates/main.html", "r", encoding="utf-8") as file:
        return HTMLResponse(content=file.read(), status_code=200)

# Endpoint to serve location_search.html directly (not typically needed but included for completeness)
@app.get("/location_search.html", response_class=HTMLResponse)
async def read_location_search():
    with open("templates/location_search.html", "r", encoding="utf-8") as file:
        return HTMLResponse(content=file.read(), status_code=200)

# Search endpoint for locations
@app.get("/search")
def search(query: str):
    query = query.lower()
    results = df_unique[(df_unique['1단계'].str.contains(query, case=False, na=False)) | 
                        (df_unique['2단계'].str.contains(query, case=False, na=False))]
    
    places = results[['1단계', '2단계']].drop_duplicates().apply(lambda row: " ".join(row.dropna()), axis=1).tolist()
    logger.info(f"Search query: {query}, Results: {places}")
    return {"places": places}

# Coordinates endpoint for locations
@app.get("/coordinates")
def coordinates(place: str):
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
        logger.info(f"Coordinates for {place} - X: {nx}, Y: {ny}, Lat: {lat}, Lon: {lon}")
        return {"coordinates": {"lat": lat, "lon": lon}}
    else:
        logger.error(f"Location not found for {place}")
        raise HTTPException(status_code=404, detail="Location not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=5500, reload=True)
