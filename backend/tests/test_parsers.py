"""Tests for document parsers."""

import pytest
from app.parsers.code_parser import CodeParser
from app.parsers.markdown_parser import MarkdownParser, ConfigParser
from app.parsers.schematic_parser import SchematicParser
from app.parsers import get_parser


# ── Code Parser ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_code_parser_c():
    code = b"""
#include <stdio.h>
#include "spi_driver.h"

void SPI_Init(SPI_Config *config) {
    config->baudrate = 1000000;
    config->mode = SPI_MODE_0;
}

int SPI_Transfer(uint8_t *tx, uint8_t *rx, size_t len) {
    for (int i = 0; i < len; i++) {
        rx[i] = tx[i];
    }
    return 0;
}
"""
    parser = CodeParser()
    result = await parser.parse(code, "spi_driver.c")

    assert result.doc_type == "source_code"
    assert result.metadata["language"] == "c"
    assert "spi_driver.h" in result.references
    assert len(result.chunks) >= 2  # header + functions


@pytest.mark.asyncio
async def test_code_parser_python():
    code = b"""
from pathlib import Path
import json

class Config:
    def __init__(self, path):
        self.path = path

    def load(self):
        return json.loads(Path(self.path).read_text())

def main():
    config = Config("config.json")
    data = config.load()
"""
    parser = CodeParser()
    result = await parser.parse(code, "config.py")

    assert result.metadata["language"] == "python"
    assert any("json" in r or "pathlib" in r for r in result.references)
    assert len(result.chunks) >= 2


# ── Markdown Parser ───────────────────────────────────────

@pytest.mark.asyncio
async def test_markdown_parser():
    md = b"""# SPI Communication Protocol

## Overview
SPI is a synchronous serial communication protocol.

## Configuration
See `spi_driver.c` for implementation details.

### Baud Rate
Default baud rate is 1MHz.
"""
    parser = MarkdownParser()
    result = await parser.parse(md, "spi_protocol.md")

    assert result.doc_type == "document"
    assert result.title == "SPI Communication Protocol"
    assert "spi_driver.c" in result.references
    assert len(result.chunks) >= 2  # Multiple sections


# ── Config Parser ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_parser():
    ini = b"""
[SPI]
baudrate = 1000000
mode = 0
cs_pin = PA4

[UART]
baudrate = 115200
"""
    parser = ConfigParser()
    result = await parser.parse(ini, "hardware.ini")

    assert result.doc_type == "document"
    assert len(result.chunks) == 1
    assert "baudrate" in result.chunks[0].content


# ── Schematic Parser ──────────────────────────────────────

@pytest.mark.asyncio
async def test_schematic_parser_kicad():
    # Simplified KiCad S-expression snippet
    sch = b"""
(kicad_sch (version 20230121)
  (symbol "Device:R" (property "Reference" "R1" (property "Value" "10K")))
  (symbol "MCU_ST:STM32F407" (property "Reference" "U1" (property "Value" "STM32F407VG")))
  (label "SPI1_MOSI")
  (label "SPI1_CLK")
  (global_label "I2C1_SDA")
)
"""
    parser = SchematicParser()
    result = await parser.parse(sch, "main_board.kicad_sch")

    assert result.doc_type == "schematic"
    assert result.metadata["format"] == "kicad"
    assert len(result.references) > 0  # Should find STM32 and SPI references


# ── Parser Registry ───────────────────────────────────────

def test_get_parser_by_extension():
    assert get_parser("main.c") is not None
    assert get_parser("readme.md") is not None
    assert get_parser("schematic.kicad_sch") is not None
    assert get_parser("config.ini") is not None
    assert get_parser("unknown.xyz") is None
