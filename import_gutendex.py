"""
Bulk import script to populate the database with all books from Gutendex API.
"""

import requests
import psycopg2
from psycopg2.extras import execute_values
import time
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

def fetch_all_books(max_books=10000):
    all_books = []
    url = "https://gutendex.com/books/"
    
    while url and len(all_books) < max_books:
        print(f"Fetching: {url}")
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            all_books.extend(data['results'])
            url = data.get('next')

            if len(all_books) >= max_books:
                all_books = all_books[:max_books]
                print(f"Reached limit of {max_books} books")
                break
            
            print(f"Fetched {len(all_books)} books so far..")
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")
            print("Waiting before fetching again")
            time.sleep(5)
            continue
    
    return all_books

def prepare_book_data(book):
    author = book.get('authors', [{}])[0].get('name', 'Unknown') if book.get('authors') else 'Unknown'
    
    pub_year = None
    if book.get('authors') and book['authors'][0].get('birth_year'):
        pub_year = book['authors'][0].get('birth_year')
    
    text_file = book.get('formats', {}).get('text/plain; charset=utf-8') or \
                book.get('formats', {}).get('text/plain') or \
                book.get('formats', {}).get('text/html')

    cover_url = book.get('formats', {}).get('image/jpeg')

    book_id = str(uuid.uuid4())
    
    return (
        book_id,
        book.get('id'),
        book.get('title', 'Unknown Title'),
        author, 
        pub_year,  
        None, 
        text_file,
        cover_url,
        f"Project Gutenberg (ID: {book.get('id')})"
    )

def bulk_insert_books(books, batch_size=500):
    print("\nConnecting to database")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("Checking database schema")
    try:
        cur.execute("""
            ALTER TABLE books 
            ADD COLUMN IF NOT EXISTS gutenberg_id INTEGER UNIQUE;
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_gutenberg_id 
            ON books(gutenberg_id);
        """)
        conn.commit()
        print("Schema updated successfully")
    except Exception as e:
        print(f"Schema update error (might already exist): {e}")
        conn.rollback()

    print("\nPreparing book data")
    book_data = [prepare_book_data(book) for book in books]

    print(f"\nInserting {len(book_data)} books in batches of {batch_size}")
    inserted_count = 0
    updated_count = 0
    
    for i in range(0, len(book_data), batch_size):
        batch = book_data[i:i + batch_size]
        batch_num = i//batch_size + 1
        total_batches = (len(book_data) + batch_size - 1) // batch_size
        
        try:
            execute_values(
                cur,
                """
                INSERT INTO books (book_id, gutenberg_id, title, author, 
                                 publication_year, isbn, text_file_path, 
                                 cover_url, text_source)
                VALUES %s
                ON CONFLICT (gutenberg_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    cover_url = COALESCE(EXCLUDED.cover_url, books.cover_url),
                    text_file_path = COALESCE(EXCLUDED.text_file_path, books.text_file_path)
                """,
                batch
            )
            
            conn.commit()
            inserted_count += len(batch)
            print(f"Batch {batch_num}/{total_batches} complete ({inserted_count}/{len(book_data)} books)")
            
        except Exception as e:
            print(f"Error inserting batch {batch_num}: {e}")
            conn.rollback()
    
    cur.execute("SELECT COUNT(*) FROM books WHERE gutenberg_id IS NOT NULL")
    total_gutenberg_books = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"Import Complete")
    print(f"{'='*60}")
    print(f"Total books processed: {len(book_data)}")
    print(f"Total Gutenberg books in database: {total_gutenberg_books}")
    print(f"{'='*60}")

if __name__ == "__main__":
    print("="*60)
    print("Scriptum - Gutendex Bulk Import")
    print("="*60)
    
    try:
        books = fetch_all_books()
        
        # Insert into database
        bulk_insert_books(books)
        
    except KeyboardInterrupt:
        print("\n\nImport cancelled by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise
