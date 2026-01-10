"""
AI Shopping Agent - Simplified Backend API
FastAPI server with Claude integration for natural language product search
No pydantic dependency - uses Python built-in types
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import anthropic
import os
import json
from datetime import datetime

app = FastAPI(title="AI Shopping Agent API")

# Enable CORS so your React frontend can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Claude client
# Set your API key as environment variable: export ANTHROPIC_API_KEY='your-key'
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Mock product database - Replace with real database later
MOCK_PRODUCTS = [
    {
        "id": 1,
        "name": "Levi's 501 Original Straight Jeans",
        "brand": "Levi's",
        "price": 45.0,
        "color": "Black",
        "fit": "Straight",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1542272454315-7f6fabb87e2d?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example1",
        "description": "Classic straight fit jeans"
    },
    {
        "id": 2,
        "name": "Wrangler Texas Stretch Jeans",
        "brand": "Wrangler",
        "price": 42.0,
        "color": "Black",
        "fit": "Straight",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example2",
        "description": "Comfortable stretch denim"
    },
    {
        "id": 3,
        "name": "Lee Brooklyn Straight Jeans",
        "brand": "Lee",
        "price": 48.0,
        "color": "Black",
        "fit": "Straight",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1605518216938-7c31b7b14ad0?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example3",
        "description": "Modern straight leg"
    },
    {
        "id": 4,
        "name": "Nudie Jeans Grim Tim",
        "brand": "Nudie Jeans",
        "price": 89.0,
        "color": "Black",
        "fit": "Slim",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example4",
        "description": "Premium slim fit"
    },
    {
        "id": 5,
        "name": "H&M Regular Fit Jeans",
        "brand": "H&M",
        "price": 29.0,
        "color": "Black",
        "fit": "Regular",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example5",
        "description": "Affordable everyday jeans"
    },
    {
        "id": 6,
        "name": "Calvin Klein Straight Leg Jeans",
        "brand": "Calvin Klein",
        "price": 49.0,
        "color": "Black",
        "fit": "Straight",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1582552938357-32b906ae53c4?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example6",
        "description": "Designer straight fit"
    },
    {
        "id": 7,
        "name": "Zara Slim Fit Jeans",
        "brand": "Zara",
        "price": 35.0,
        "color": "Blue",
        "fit": "Slim",
        "category": "jeans",
        "image_url": "https://images.unsplash.com/photo-1598554747436-c9293d6a588f?w=300&h=400&fit=crop",
        "affiliate_link": "https://tradedoubler.com/click?p=123&a=456&url=example7",
        "description": "Trendy slim fit"
    },
]

def parse_query_with_claude(query: str) -> dict:
    """Use Claude to parse natural language query into structured parameters"""
    
    prompt = f"""You are a shopping assistant. Parse this product search query into structured parameters.

Query: "{query}"

Extract these fields if mentioned:
- color (e.g., black, blue, red)
- max_price (numerical value)
- min_price (numerical value)
- fit (e.g., straight, slim, skinny, regular, relaxed)
- category (e.g., jeans, shirts, shoes, jackets)
- brand (e.g., Levi's, Nike, Adidas)
- size (e.g., S, M, L, 32, 34)

Respond ONLY with JSON in this exact format (use null for missing values):
{{
    "color": "value or null",
    "max_price": number or null,
    "min_price": number or null,
    "fit": "value or null",
    "category": "value or null",
    "brand": "value or null",
    "size": "value or null"
}}"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract JSON from response
        response_text = message.content[0].text
        # Remove markdown code blocks if present
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        # Parse JSON
        parsed_data = json.loads(response_text)
        
        return parsed_data
    
    except Exception as e:
        print(f"Error parsing with Claude: {e}")
        # Return empty dict on error
        return {
            "color": None,
            "max_price": None,
            "min_price": None,
            "fit": None,
            "category": None,
            "brand": None,
            "size": None
        }

def filter_products(parsed: dict, products: list) -> list:
    """Filter products based on parsed query parameters"""
    
    filtered = products.copy()
    
    # Filter by category
    if parsed.get("category"):
        filtered = [p for p in filtered if parsed["category"].lower() in p["category"].lower()]
    
    # Filter by color
    if parsed.get("color"):
        filtered = [p for p in filtered if parsed["color"].lower() in p["color"].lower()]
    
    # Filter by price
    if parsed.get("max_price"):
        filtered = [p for p in filtered if p["price"] <= parsed["max_price"]]
    if parsed.get("min_price"):
        filtered = [p for p in filtered if p["price"] >= parsed["min_price"]]
    
    # Filter by fit
    if parsed.get("fit"):
        filtered = [p for p in filtered if parsed["fit"].lower() in p["fit"].lower()]
    
    # Filter by brand
    if parsed.get("brand"):
        filtered = [p for p in filtered if parsed["brand"].lower() in p["brand"].lower()]
    
    # Sort by price (cheapest first)
    filtered.sort(key=lambda x: x["price"])
    
    return filtered

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "AI Shopping Agent API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/search")
async def search_products(request: Request):
    """
    Main search endpoint - takes natural language query and returns matching products
    
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
        
        # Step 1: Parse query using Claude
        parsed_query = parse_query_with_claude(query)
        
        # Step 2: Filter products based on parsed parameters
        results = filter_products(parsed_query, MOCK_PRODUCTS)
        
        # Step 3: Return results
        return {
            "query": query,
            "parsed_query": parsed_query,
            "total_results": len(results),
            "products": results
        }
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/api/products")
def get_all_products():
    """Get all products (for testing)"""
    return {
        "total": len(MOCK_PRODUCTS),
        "products": MOCK_PRODUCTS
    }

@app.get("/api/products/{product_id}")
def get_product(product_id: int):
    """Get a specific product by ID"""
    product = next((p for p in MOCK_PRODUCTS if p["id"] == product_id), None)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product

# Run with: uvicorn main:app --reload
# Access API docs at: http://localhost:8000/docs