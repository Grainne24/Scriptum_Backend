'''
    This file interacts with the Gutendex API to search and download books from Gutenberg
'''

import httpx 
from typing import Optional, Dict, List
import re

class GutendexService:
    
    BASE_URL = "https://gutendex.com/books/"  
    
    #This returns list of book with its metadata
    async def search_books(
        self, 
        search: Optional[str] = None,
        author: Optional[str] = None,
        title: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:

        params = {}
        
        # Build search query
        if search:
            params["search"] = search
        elif author:
            params["search"] = author
        elif title:
            params["search"] = title
            
        #This makes a HTTP GET request to the Gutendex API
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                response = await client.get(
                    self.BASE_URL, 
                    params=params, 
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                
                #This extract the book data and formats it
                books = []
                for book in data.get("results", [])[:limit]:
                    authors_list = book.get("authors", [])
                    author_names = [author.get("name", "Unknown") for author in authors_list]
                    
                    books.append({
                        "gutenberg_id": book.get("id"),
                        "title": book.get("title", "Unknown Title"),
                        "authors": author_names,
                        "author": author_names[0] if author_names else "Unknown",
                        "cover_url": cover_url,
                        "subjects": book.get("subjects", []),
                        "languages": book.get("languages", []),
                        "download_count": book.get("download_count", 0),
                        "formats": book.get("formats", {})
                    })
                
                return books
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                raise
            except Exception as e:
                print(f"Error searching Gutendex: {e}")
                raise
    
    #This gets the book metadat by its Gutenberg ID which returns the book directory or None
    async def get_book_by_id(self, gutenberg_id: int) -> Optional[Dict]:
        url = f"{self.BASE_URL}{gutenberg_id}/"
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                book = response.json()
                
                authors_list = book.get("authors", [])
                author_names = [author.get("name", "Unknown") for author in authors_list]

                formats = data.get("formats", {})
                cover_url = formats.get("image/jpeg") or formats.get("image/png")

                subjects = data.get("subjects", [])
                    year = None
                    for subject in subjects:
                        if "century" in subject.lower():
                            #Try to extract year from subjects
                            pass
                
                return {
                    "gutenberg_id": book.get("id"),
                    "title": book.get("title", "Unknown Title"),
                    "authors": author_names,
                    "author": author_names[0] if author_names else "Unknown",
                    "cover_url": cover_url,
                    "subjects": book.get("subjects", []),
                    "languages": book.get("languages", []),
                    "download_count": book.get("download_count", 0),
                    "formats": book.get("formats", {})
                }
            except:
                return None
    
    #This downloads the whole book script if its available
    async def get_book_text(self, gutenberg_id: int) -> Optional[str]:
        # Try multiple URL formats for text files
        urls_to_try = [
            f"https://www.gutenberg.org/files/{gutenberg_id}/{gutenberg_id}-0.txt",
            f"https://www.gutenberg.org/cache/epub/{gutenberg_id}/pg{gutenberg_id}.txt",
        ]
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for url in urls_to_try:
                try:
                    print(f"Trying to fetch text from: {url}")
                    response = await client.get(url, timeout=60.0)
                    response.raise_for_status()
                    
                    # Clean the text (remove Project Gutenberg header/footer)
                    text = response.text
                    print(text)
                    text = self._clean_gutenberg_text(text)
                    print ("===================================================")
                    print(text)
                    
                    if len(text) > 1000:  # Make sure we got actual content
                        print(f"Successfully fetched {len(text)} characters")
                        return text
                except Exception as e:
                    print(f"Failed to fetch from {url}: {e}")
                    continue
            
            print(f"Could not fetch text for Gutenberg ID {gutenberg_id}")
            return None
    
    def _clean_gutenberg_text(self, text: str) -> str:
        # Split text into lines for easier processing
        lines = text.split('\n')
        
        # Find the start marker
        start_idx = 0
        for i, line in enumerate(lines):
            if 'START OF' in line.upper() and 'PROJECT GUTENBERG' in line.upper():
                start_idx = i + 1  # Start from the line after the marker
                print(f"Found START marker at line {i}: {line[:60]}...")
                break
        
        # Find the end marker
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if 'END OF' in lines[i].upper() and 'PROJECT GUTENBERG' in lines[i].upper():
                end_idx = i  # End at the line before the marker
                print(f"Found END marker at line {i}: {lines[i][:60]}...")
                break
        
        # Extract the content between markers
        content_lines = lines[start_idx:end_idx]
        text = '\n'.join(content_lines)
        
        # Additional cleaning - remove common prefatory material
        # Remove "Produced by..." lines
        text = re.sub(r'Produced by[^\n]*\n', '', text, flags=re.IGNORECASE)
        
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = text.strip()
        
        print(f"Final text length: {len(text)} characters, {len(text.split())} words")
        
        return text

# Create singleton instance
gutendex_service = GutendexService()
