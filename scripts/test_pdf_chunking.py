#!/usr/bin/env python3
"""Test PDF semantic chunking."""
import asyncio
from app.parsers.pdf_parser import PDFParser
import io

import pymupdf

# Create test PDF
doc = pymupdf.open()
width, height = 595, 842

# Page 1: Title (large font, not bold - should NOT be heading)
page = doc.new_page(width=width, height=height)
page.insert_text((100, 100), "Test Document", fontsize=24)
page.insert_text((100, 150), "A test PDF for semantic chunking", fontsize=12)

# Page 2: Chapter 1
page = doc.new_page(width=width, height=height)
page.insert_text((100, 100), "1. Introduction", fontsize=16)
page.insert_text((100, 130), "This is the introduction section.", fontsize=12)
page.insert_text((100, 150), "It provides an overview.", fontsize=12)

# Page 3: Chapter 2 with subsections
page = doc.new_page(width=width, height=height)
page.insert_text((100, 100), "2. Main Content", fontsize=16)
page.insert_text((120, 130), "2.1 First Subsection", fontsize=14)
page.insert_text((120, 155), "Subsection content.", fontsize=12)
page.insert_text((120, 200), "2.2 Second Subsection", fontsize=14)
page.insert_text((120, 225), "More content here.", fontsize=12)

buf = io.BytesIO()
doc.save(buf)
page_count = len(doc)
buf.seek(0)
print(f"PDF: {page_count} pages")
doc.close()


async def test():
    parser = PDFParser()
    result = await parser.parse(buf.getvalue(), "test.pdf")
    print(f"\nTitle: {result.title}")
    print(f"Chunks: {len(result.chunks)}")
    print()

    for i, c in enumerate(result.chunks):
        h = c.metadata.get("heading") or "(none)"
        pages = f"p{c.metadata.get('start_page')}-{c.metadata.get('end_page')}"
        content = c.content[:70].replace("\n", " ")
        print(f"Chunk {i+1}: [{c.metadata.get('type')}] heading={repr(h)} ({pages})")
        print(f"  Content: {content}...")
        print()


async def test():
    parser = PDFParser()
    result = await parser.parse(buf.getvalue(), "test.pdf")
    print(f"\nTitle: {result.title}")
    print(f"Chunks: {len(result.chunks)}")
    print()

    for i, c in enumerate(result.chunks):
        h = c.metadata.get("heading") or "(none)"
        pages = f"p{c.metadata.get('start_page')}-{c.metadata.get('end_page')}"
        content = c.content[:70].replace("\n", " ")
        print(f"Chunk {i+1}: [{c.metadata.get('type')}] heading={repr(h)} ({pages})")
        print(f"  Content: {content}...")
        print()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
