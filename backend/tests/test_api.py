"""
Integration tests for the REST API.
These tests require a running PostgreSQL + MinIO + Ollama.

Run with: pytest tests/test_api.py -v
(Make sure docker-compose services are up first)
"""

import pytest
import httpx

BASE_URL = "http://localhost:8000"


@pytest.fixture
def client():
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_get_document(client):
    # Create
    resp = await client.post("/api/documents/", json={
        "title": "Test Document",
        "doc_type": "document",
        "content": "This is a test document about SPI communication.",
        "tags": ["test", "spi"],
    })
    assert resp.status_code == 201
    doc = resp.json()
    doc_id = doc["id"]
    assert doc["title"] == "Test Document"

    # Get
    resp = await client.get(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["content"] == "This is a test document about SPI communication."
    assert "test" in detail["tags"]

    # List
    resp = await client.get("/api/documents/")
    assert resp.status_code == 200
    docs = resp.json()
    assert any(d["id"] == doc_id for d in docs)

    # Delete
    resp = await client.delete(f"/api/documents/{doc_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_create_relation(client):
    # Create two docs
    resp1 = await client.post("/api/documents/", json={
        "title": "main.c", "doc_type": "source_code", "content": "#include <spi.h>",
    })
    resp2 = await client.post("/api/documents/", json={
        "title": "spi.h", "doc_type": "source_code", "content": "void SPI_Init();",
    })
    doc1 = resp1.json()
    doc2 = resp2.json()

    # Create relation
    resp = await client.post("/api/relations/", json={
        "source_id": doc1["id"],
        "target_id": doc2["id"],
        "relation_type": "depends_on",
        "description": "main.c includes spi.h",
    })
    assert resp.status_code == 201
    rel = resp.json()
    assert rel["relation_type"] == "depends_on"

    # Get relations
    resp = await client.get(f"/api/relations/{doc1['id']}")
    assert resp.status_code == 200
    rels = resp.json()
    assert len(rels) >= 1

    # Cleanup
    await client.delete(f"/api/documents/{doc1['id']}")
    await client.delete(f"/api/documents/{doc2['id']}")


@pytest.mark.asyncio
async def test_upload_file(client):
    content = b"#include <stdio.h>\nvoid main() { printf(\"hello\"); }"
    files = {"file": ("hello.c", content, "text/x-c")}
    resp = await client.post("/api/upload/", files=files, data={"tags": "test,hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_type"] == "source_code"

    # Cleanup
    await client.delete(f"/api/documents/{data['document_id']}")


@pytest.mark.asyncio
async def test_search(client):
    # Create a doc with content
    resp = await client.post("/api/documents/", json={
        "title": "SPI Protocol Guide",
        "doc_type": "document",
        "content": "SPI is a synchronous serial communication protocol used for short-distance communication.",
    })
    doc = resp.json()

    # Search (may not find via vector if embeddings aren't ready, but API should not error)
    resp = await client.post("/api/search/", json={"query": "SPI protocol", "limit": 5})
    assert resp.status_code == 200

    # Cleanup
    await client.delete(f"/api/documents/{doc['id']}")
