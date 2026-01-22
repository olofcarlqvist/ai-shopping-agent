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

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Claude client
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Create a database connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print("Database connection error:", str(e))
        return None

def search_database(query: str) -> list:
    """
    Search the PostgreSQL database for products matching the query
    Returns a list of product dictionaries
    """
    conn = get_db_connection()
    if not conn:
        print("No database connection available")
        return []
    
    try:
        cursor = conn.cursor()
        
        # Parse query for keywords
        query_lower = query.lower()
        search_terms = query_lower.split()
        
        # Build SQL query with flexible matching
        # Search in name, brand, color, category, fit
        sql = """
            SELECT 
                id,
                name,
                brand,
                price,
                color,
                fit,
                category,
                image_url,
                product_url,
                retailer
            FROM products
            WHERE 
                LOWER(name) LIKE %s OR
                LOWER(brand) LIKE %s OR
                LOWER(color) LIKE %s OR
                LOWER(category) LIKE %s OR
                LOWER(fit) LIKE %s
            LIMIT 20
        """
        
        # Create search pattern
        search_pattern = f"%{query_lower}%"
        
        cursor.execute(sql, (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))
        results = cursor.fetchall()
        
        # Convert to list of dicts
        products = []
        for row in results:
            products.append(dict(row))
        
        print(f"Database search found {len(products)} products")
        
        cursor.close()
        conn.close()
        
        return products
        
    except Exception as e:
        print("Database search error:", str(e))
        if conn:
            conn.close()
        return []

def search_products_with_claude(query: str) -> list:
    """
    Fallback: Use Claude with web search to find real products matching the query
    Returns a list of product dictionaries
    """
    
    prompt = """Find real products for: """ + '"' + query + '"' + """

Search the web and return 6 products as a JSON array. Each product needs:
- name: Product name
- brand: Brand
- price: Price in USD (number)
- color: Color
- fit: Fit type or "Regular"
- category: Type (jeans, shoes, etc)
- image_url: Image URL
- product_url: Product page URL
- retailer: Store name

Important: Return ONLY the JSON array. No text before or after. Start with [ and end with ].

Example: [{"name":"Levi's 501 Jeans","brand":"Levi's","price":69.50,"color":"Black","fit":"Straight","category":"jeans","image_url":"https://example.com/img.jpg","product_url":"https://example.com/product","retailer":"Levi's"}]"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search"
            }],
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract the response text from all content blocks
        response_text = ""
        for block in message.content:
            if block.type == "text":
                response_text += block.text
        
        if not response_text.strip():
            print("No text response from Claude")
            return []
        
        # Clean up the response (remove markdown code blocks if present)
        response_text = response_text.strip()
        
        # Remove markdown code blocks
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = response_text.strip()
        
        # Try to find JSON array in the response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        print("Web search - Cleaned response (first 200 chars):", response_text[:200], "...")
        
        # Parse JSON
        products = json.loads(response_text)
        
        # Ensure it's a list
        if not isinstance(products, list):
            print("Response is not a list")
            return []
        
        # Add unique IDs to products and ensure all fields exist
        for i, product in enumerate(products):
            product["id"] = f"web_{i + 1}"
            
            # Ensure all required fields exist with defaults
            product.setdefault("name", "Unknown Product")
            product.setdefault("brand", "Unknown")
            product.setdefault("price", 0.0)
            product.setdefault("color", "N/A")
            product.setdefault("fit", "Regular")
            product.setdefault("category", "clothing")
            product.setdefault("retailer", "Online Store")
            product.setdefault("image_url", "https://via.placeholder.com/300x400?text=No+Image")
            product.setdefault("product_url", "#")
        
        print("Web search found", len(products), "products")
        return products
    
    except json.JSONDecodeError as e:
        print("JSON parsing error:", str(e))
        if 'response_text' in locals():
            print("Response text (first 500 chars):", response_text[:500])
        return []
    except Exception as e:
        print("Error searching with Claude:", str(e))
        return []

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "AI Shopping Agent API (Hybrid: Database + Web Search)",
        "version": "3.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/search")
async def search_products(request: Request):
    """
    Main search endpoint - Hybrid approach:
    1. Search PostgreSQL database first (fast, reliable)
    2. If no results, fallback to Claude web search
    
    Example request:
    POST /api/search
    {
        "query": "Black jeans under 50 dollars in straight fit"
    }
    """
    
    try:
        body = await request.json()
        query = body.get("query", "")
        
        if not query or len(query.strip()) == 0:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        print(f"\n{'='*50}")
        print(f"Search Query: {query}")
        print(f"{'='*50}")
        
        # STEP 1: Search database first
        print("Step 1: Searching database...")
        db_products = search_database(query)
        
        if db_products and len(db_products) > 0:
            # Found results in database!
            print(f"✅ Database returned {len(db_products)} products")
            return {
                "query": query,
                "total_results": len(db_products),
                "products": db_products,
                "source": "database"
            }
        
        # STEP 2: No results in database, fallback to web search
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
        
        # Return web search results
        print(f"✅ Web search returned {len(web_products)} products")
        return {
            "query": query,
            "total_results": len(web_products),
            "products": web_products,
            "source": "web_search"
        }
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    except Exception as e:
        print("Search error:", str(e))
        raise HTTPException(status_code=500, detail="Search failed: " + str(e))
    