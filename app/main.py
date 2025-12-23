'''
    This creates the FastAPI
'''
from fastapi import APIRouter, Query
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

@router.get("/books")
async def get_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None
):
    
    conn = get_db_connection()  # Your database connection function
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    offset = (page - 1) * page_size
    
    if search:
        # Search in title and author
        search_query = f"%{search}%"
        cur.execute("""
            SELECT 
                gutenberg_id as id,
                title,
                author,
                subjects,
                languages,
                download_count,
                cover_image_url,
                copyright,
                media_type
            FROM books
            WHERE title ILIKE %s OR author ILIKE %s
            ORDER BY download_count DESC NULLS LAST
            LIMIT %s OFFSET %s
        """, (search_query, search_query, page_size, offset))
        
        books = cur.fetchall()
        
        # Get total count for search
        cur.execute("""
            SELECT COUNT(*) as count
            FROM books
            WHERE title ILIKE %s OR author ILIKE %s
        """, (search_query, search_query))
        
    else:
        # Get all books
        cur.execute("""
            SELECT 
                gutenberg_id as id,
                title,
                author,
                subjects,
                languages,
                download_count,
                cover_image_url,
                copyright,
                media_type
            FROM books
            ORDER BY download_count DESC NULLS LAST
            LIMIT %s OFFSET %s
        """, (page_size, offset))
        
        books = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) as count FROM books")
    
    count_result = cur.fetchone()
    total_count = count_result['count']
    
    cur.close()
    conn.close()

    total_pages = (total_count + page_size - 1) // page_size
    has_next = page < total_pages
    has_previous = page > 1
    
    return {
        "count": total_count,
        "next": f"/books?page={page + 1}&page_size={page_size}" if has_next else None,
        "previous": f"/books?page={page - 1}&page_size={page_size}" if has_previous else None,
        "results": [
            {
                "id": book['id'],
                "title": book['title'],
                "authors": [{"name": book['author'], "birth_year": None, "death_year": None}],
                "subjects": book['subjects'],
                "languages": book['languages'],
                "download_count": book['download_count'],
                "formats": {"image/jpeg": book['cover_image_url']} if book['cover_image_url'] else {},
                "copyright": book['copyright'],
                "media_type": book['media_type']
            }
            for book in books
        ]
    }
app.include_router(books.router)
app.include_router(stylometry.router)
