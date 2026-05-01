"""Basic smoke tests for Pydantic schemas."""

import uuid
from datetime import datetime

from app.models.schemas import DocumentCreate, SearchQuery, RelationCreate


def test_document_create_valid():
    doc = DocumentCreate(
        title="SPI Driver",
        doc_type="source_code",
        content="#include <spi.h>",
        tags=["spi", "driver"],
    )
    assert doc.title == "SPI Driver"
    assert doc.doc_type == "source_code"
    assert len(doc.tags) == 2


def test_search_query_defaults():
    q = SearchQuery(query="SPI initialization")
    assert q.limit == 10
    assert q.doc_type is None
    assert q.tags == []


def test_relation_create_valid():
    r = RelationCreate(
        source_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        relation_type="depends_on",
        description="main.c includes spi_driver.h",
    )
    assert r.confidence == 1.0
    assert r.relation_type == "depends_on"
