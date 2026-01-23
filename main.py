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
        
        # Build SQL query with flexible matching
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
                affiliate_link
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
        
        # Convert to list of dicts and map affiliate_link to retailer
        products = []
        for row in results:
            product = dict(row)
            # Map affiliate_link to retailer for frontend compatibility
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
        
        # Clean up the response
        response_text = response_text.strip()
        response
        