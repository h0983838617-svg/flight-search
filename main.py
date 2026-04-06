import os
import requests
from fastapi import FastAPI, Query

app = FastAPI()

def extract_itineraries(flight_groups: list) -> list:
    """從 SerpApi 的航班群組中提取並正規化整個行程的資料"""
    result = []
    
    for group in flight_groups:
        # 1. 價格與總時長是在「整個行程 (group)」這一層
        price = group.get("price", float('inf')) # 找不到價格設為無限大，避免排到最前面
        duration = group.get("total_duration", "Unknown")
        
        # 2. 取得實際的飛行段落 (segments)
        segments = group.get("flights", [])
        if not segments:
            continue
            
        # 3. 航空公司名稱 (通常取第一段航班的航空公司代表)
        airline = segments[0].get("airline", "Unknown")
        
        # 4. 出發資訊：看「第一段」航程
        first_segment = segments[0]
        departure_airport = first_segment.get("departure_airport", {}).get("id", "")
        departure_time = first_segment.get("departure_airport", {}).get("time", "")
        
        # 5. 抵達資訊：看「最後一段」航程 (解決轉機問題)
        last_segment = segments[-1]
        arrival_airport = last_segment.get("arrival_airport", {}).get("id", "")
        arrival_time = last_segment.get("arrival_airport", {}).get("time", "")
        
        # 6. 計算轉機次數 (幫助你過濾太折騰的航班)
        layovers = len(segments) - 1
        
        result.append({
            "airline": airline,
            "departure_time": departure_time,
            "departure_airport": departure_airport,
            "arrival_time": arrival_time,
            "arrival_airport": arrival_airport,
            "duration": duration,
            "layovers": layovers,
            "price": price
        })
        
    return result

@app.get("/search")
def search_flights(
    departure_id: str = Query(..., description="Departure airport IATA code (e.g., TPE)"),
    arrival_id: str = Query(..., description="Arrival airport IATA code (e.g., NRT)"),
    outbound_date: str = Query(..., description="Outbound date (YYYY-MM-DD)"),
    return_date: str = Query(..., description="Return date (YYYY-MM-DD)")
):
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        return {"error": "SERPAPI_KEY environment variable is not set"}

    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "api_key": api_key,
        "hl": "zh-TW",     # 強制回傳繁體中文 (可選)
        "currency": "TWD"  # 強制使用台幣計價 (可選)
    }

    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch flights: {str(e)}"}

    all_flights = []
    
    # 直接合併 best_flights 和 other_flights 一起處理
    best_flights = data.get("best_flights", [])
    other_flights = data.get("other_flights", [])
    
    all_flights.extend(extract_itineraries(best_flights))
    all_flights.extend(extract_itineraries(other_flights))

    # 濾除沒有正確抓到價格的航班 (價格為 inf 的)
    valid_flights = [f for f in all_flights if f["price"] != float('inf')]

    # 依照價格排序，取得前三便宜的機票
    valid_flights.sort(key=lambda x: x["price"])
    cheapest_3 = valid_flights[:3]

    # 取出 Google Flights 原始搜尋連結
    google_flights_link = data.get("search_link", "")

    return {
        "flights": cheapest_3,
        "google_flights_link": google_flights_link
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
