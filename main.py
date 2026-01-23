"""
AI Shopping Agent - Hybrid Backend (Database + Web Search)
FastAPI server with PostgreSQL database primary search and Claude web search fallback
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import anthropic
import os
import json
import re
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="AI Shopping Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print("Database connection error:", str(e))
        return None

def search_database(query: str):
    conn = get_db_connection()
    if not conn:
        print("No database connection available")
        return []
    
    try:
        cursor = conn.cursor()
        query_lower = query.lower()
        sql = """
            SELECT id, name, brand, price, color, fit, category, image_url, product_url, affiliate_link
            FROM products
            WHERE LOWER(name) LIKE %s OR LOWER(brand) LIKE %s OR LOWER(color) LIKE %s OR LOWER(category) LIKE %s OR LOWER(fit) LIKE %s
            LIMIT 20
        """
        search_pattern = f"%{query_lower}%"
        cursor.execute(sql, (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))
        results = cursor.fetchall()
        
        products = []
        for row in results:
            product = dict(row)
            product['retailer'] = product.get('brand', 'Online Store')
            products.append(product)
        
        print(f"Database search found {len(products)} products")
        cursor.close()
        conn.close()
        return products
        
    except Exception as e:
        print("Database search error:", str(e))
        if conn:
            conn.close()
        return []

def search_products_with_claude(query: str):
    prompt = f'Find real products for: "{query}"\n\nSearch the web and return 6 products as a JSON array. Each product needs: name, brand, price (USD number), color, fit, category, image_url, product_url, retailer. Return ONLY the JSON array. Start with [ and end with ].'
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = ""
        for block in message.content:
            if block.type == "text":
                response_text += block.text
        
        if not response_text.strip():
            return []
        
        response_text = response_text.strip()
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = response_text.strip()
        
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        products = json.loads(response_text)
        
        if not isinstance(products, list):
            return []
        
        for i, product in enumerate(products):
            product["id"] = f"web_{i + 1}"
            product.setdefault("name", "Unknown Product")
            product.setdefault("brand", "Unknown")
            product.setdefault("price", 0.0)
            product.setdefault("color", "N/A")
            product.setdefault("fit", "Regular")
            product.setdefault("category", "clothing")
            product.setdefault("retailer", "Online Store")
            product.setdefault("image_url", "https://via.placeholder.com/300x400?text=No+Image")
            product.setdefault("product_url", "#")
        
        return products
    except Exception as e:
        print("Error searching with Claude:", str(e))
        return []

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "AI Shopping Agent API (Hybrid: Database + Web Search)",
        "version": "3.0.1",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/search")
async def search_products(request: Request):
    try:
        body = await request.json()
        query = body.get("query", "")
        
        if not query or len(query.strip()) == 0:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        print(f"\n{'='*50}")
        print(f"Search Query: {query}")
        print(f"{'='*50}")
        print("Step 1: Searching database...")
        
        db_products = search_database(query)
        
        if db_products and len(db_products) > 0:
            print(f"✅ Database returned {len(db_products)} products")
            return {
                "query": query,
                "total_results": len(db_products),
                "products": db_products,
                "source": "database"
            }
        
        print("⚠️ No database results. Falling back to web search...")
        web_products = search_products_with_claude(query)
        
        if not web_products or len(web_products) == 0:
            return {
                "query": query,
                "total_results": 0,
                "products": [],
                "source": "none",
                "message": "No products found in database or web search. Try a different search."
            }
        
        print(f"✅ Web search returned {len(web_products)} products")
        return {
            "query": query,
            "total_results": len(web_products),
            "products": web_products,
            "source": "web_search"
        }
    except Exception as e:
        print("Search error:", str(e))
        raise HTTPException(status_code=500, detail="Search failed: " + str(e))
    