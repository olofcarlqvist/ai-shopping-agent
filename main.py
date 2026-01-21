"""
AI Shopping Agent - Web Search Backend
FastAPI server with Claude integration for real-time product search
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import anthropic
import os
import json
import re
from datetime import datetime

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

def search_products_with_claude(query: str) -> list:
    """
    Use Claude with web search to find real products matching the query
    Returns a list of product dictionaries
    """
    
    prompt = """Search the web and find 6-8 products for: """ + '"' + query + '"' + """

CRITICAL: You MUST respond with ONLY a valid JSON array. No explanations, no markdown, no text before or after. Just pure JSON.

Your response must start with [ and end with ]. Each product must have these exact fields:
- name (string)
- brand (string)
- price (number, USD)
- color (string)
- fit (string)
- category (string)
- image_url (string, valid URL)
- product_url (string, valid URL)
- retailer (string)

Do NOT say "I'll search" or "Let me find". Do NOT explain anything. ONLY output the JSON array.

Correct response format:
[{"name":"Levi's 501 Original Jeans","brand":"Levi's","price":69.50,"color":"Black","fit":"Straight","category":"jeans","image_url":"https://levi.com/image.jpg","product_url":"https://levi.com/501","retailer":"Levi's"}]"""

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
        # Look for [...] pattern
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        print("Cleaned response (first 200 chars):", response_text[:200], "...")
        
        # Parse JSON
        products = json.loads(response_text)
        
        # Ensure it's a list
        if not isinstance(products, list):
            print("Response is not a list")
            return []
        
        # Add unique IDs to products
        for i, product in enumerate(products):
            product["id"] = i + 1
            
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
        
        print("Successfully parsed", len(products), "products")
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
        "service": "AI Shopping Agent API (Web Search)",
        "version": "2.0.1",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/search")
async def search_products(request: Request):
    """
    Main search endpoint - takes natural language query and returns real products from web search
    
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
        
        print("Searching for:", query)
        
        # Search for products using Claude with web search
        products = search_products_with_claude(query)
        
        if not products:
            return {
                "query": query,
                "total_results": 0,
                "products": [],
                "message": "No products found. Try a different search."
            }
        
        # Return results
        return {
            "query": query,
            "total_results": len(products),
            "products": products
        }
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    except Exception as e:
        print("Search error:", str(e))
        raise HTTPException(status_code=500, detail="Search failed: " + str(e))
    