"""Schematic file parser: handles .sch (KiCad/Altium text format) and PDF schematics."""

import re

from app.parsers.base import BaseParser, ParseResult, ParsedChunk


class SchematicParser(BaseParser):
    """Parse EDA schematic files (.sch, .schdoc, .kicad_sch)."""

    def supported_extensions(self) -> set[str]:
        return {".sch", ".schdoc", ".kicad_sch", ".brd", ".pcbdoc"}

    async def parse(self, data: bytes, filename: str) -> ParseResult:
        ext = filename.rsplit(".", 1)[-1].lower()

        if ext == "kicad_sch":
            return await self._parse_kicad(data, filename)
        elif ext in ("sch", "schdoc"):
            return await self._parse_altium_or_generic(data, filename)
        else:
            # PCB files: extract what we can as text
            return await self._parse_generic(data, filename)

    async def _parse_kicad(self, data: bytes, filename: str) -> ParseResult:
        """Parse KiCad 6+ .kicad_sch (S-expression format)."""
        text = data.decode("utf-8", errors="replace")

        components = []
        nets = set()
        labels = []

        # Extract symbols (components)
        for m in re.finditer(
            r'\(symbol\s+"([^"]+)".*?\(property\s+"Reference"\s+"([^"]+)".*?\(property\s+"Value"\s+"([^"]+)"',
            text, re.DOTALL
        ):
            lib_symbol, ref, value = m.groups()
            components.append({"designator": ref, "value": value, "lib": lib_symbol})

        # Extract net labels
        for m in re.finditer(r'\(label\s+"([^"]+)"', text):
            labels.append(m.group(1))
            nets.add(m.group(1))

        # Extract global labels (power, signals)
        for m in re.finditer(r'\(global_label\s+"([^"]+)"', text):
            labels.append(m.group(1))
            nets.add(m.group(1))

        # Build structured description
        comp_desc = "\n".join(
            f"  {c['designator']}: {c['value']} ({c['lib']})" for c in components
        )
        nets_desc = ", ".join(sorted(nets))

        summary = (
            f"# Schematic: {filename}\n\n"
            f"## Components ({len(components)}):\n{comp_desc}\n\n"
            f"## Nets/Signals ({len(nets)}):\n{nets_desc}\n"
        )

        # Build chunks by component groups
        chunks = self._chunk_by_modules(components, labels, filename)
        if not chunks:
            chunks = [ParsedChunk(content=summary, metadata={"type": "schematic_full"})]

        refs = self._extract_code_references(components, labels)

        return ParseResult(
            title=filename,
            doc_type="schematic",
            content=summary,
            chunks=chunks,
            metadata={
                "format": "kicad",
                "components_count": len(components),
                "nets_count": len(nets),
                "components": [c["designator"] for c in components],
                "signals": sorted(nets),
            },
            references=refs,
        )

    async def _parse_altium_or_generic(self, data: bytes, filename: str) -> ParseResult:
        """Parse Altium .sch/.schdoc or generic text-based schematic files."""
        # Try as text first
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = ""

        components = []
        nets = set()

        # Generic patterns for component-like entries
        # Altium text format often has: Designator=R1, Value=10K, etc.
        for m in re.finditer(r"Designator=(\w+)", text, re.IGNORECASE):
            designator = m.group(1)
            # Try to find corresponding value nearby
            value_match = re.search(
                rf"Designator={re.escape(designator)}.*?(?:Value|Comment)=([^\n|]+)",
                text, re.IGNORECASE | re.DOTALL
            )
            value = value_match.group(1).strip() if value_match else "?"
            components.append({"designator": designator, "value": value})

        # Net names
        for m in re.finditer(r"(?:NetName|Net)=(\w+)", text, re.IGNORECASE):
            nets.add(m.group(1))

        # Also look for common signal patterns in any text
        for m in re.finditer(
            r"\b(SPI\d?_\w+|I2C\d?_\w+|UART\d?_\w+|GPIO_\w+|ADC\d?_\w+|TIM\d+_\w+)\b", text
        ):
            nets.add(m.group(1))

        if not components and not nets:
            # Binary format or unrecognizable - store raw text
            content = f"# Schematic: {filename}\n\n(Binary or unrecognized format)\n\nRaw text preview:\n{text[:3000]}"
            return ParseResult(
                title=filename,
                doc_type="schematic",
                content=content,
                chunks=[ParsedChunk(content=content, metadata={"type": "schematic_raw"})],
                metadata={"format": "unknown"},
            )

        comp_desc = "\n".join(f"  {c['designator']}: {c['value']}" for c in components)
        summary = (
            f"# Schematic: {filename}\n\n"
            f"## Components ({len(components)}):\n{comp_desc}\n\n"
            f"## Signals:\n{', '.join(sorted(nets))}\n"
        )

        chunks = self._chunk_by_modules(components, list(nets), filename)
        if not chunks:
            chunks = [ParsedChunk(content=summary, metadata={"type": "schematic_full"})]

        return ParseResult(
            title=filename,
            doc_type="schematic",
            content=summary,
            chunks=chunks,
            metadata={
                "format": "altium",
                "components_count": len(components),
                "components": [c["designator"] for c in components],
                "signals": sorted(nets),
            },
            references=self._extract_code_references(components, list(nets)),
        )

    async def _parse_generic(self, data: bytes, filename: str) -> ParseResult:
        """Fallback for PCB and other binary-ish EDA files."""
        try:
            text = data.decode("utf-8", errors="replace")[:5000]
        except Exception:
            text = "(Binary file)"

        return ParseResult(
            title=filename,
            doc_type="schematic",
            content=f"# EDA File: {filename}\n\n{text}",
            chunks=[ParsedChunk(
                content=f"EDA file: {filename}\n{text[:2000]}",
                metadata={"type": "eda_file", "file": filename},
            )],
            metadata={"format": "eda_binary"},
        )

    def _chunk_by_modules(
        self, components: list[dict], labels: list[str], filename: str
    ) -> list[ParsedChunk]:
        """Group components by prefix (e.g., U=ICs, R=resistors, C=caps) into chunks."""
        groups: dict[str, list[dict]] = {}
        for c in components:
            # Group by first letter of designator (U, R, C, L, etc.)
            prefix = re.match(r"([A-Za-z]+)", c["designator"])
            key = prefix.group(1) if prefix else "OTHER"
            groups.setdefault(key, []).append(c)

        chunks = []
        prefix_names = {"U": "ICs", "R": "Resistors", "C": "Capacitors", "L": "Inductors",
                        "D": "Diodes", "Q": "Transistors", "J": "Connectors", "SW": "Switches"}

        for prefix, comps in groups.items():
            name = prefix_names.get(prefix, f"Group {prefix}")
            desc = "\n".join(f"  {c['designator']}: {c.get('value', '?')}" for c in comps)
            chunks.append(ParsedChunk(
                content=f"## {name} ({len(comps)} components)\n{desc}",
                metadata={
                    "type": "component_group",
                    "group": prefix,
                    "file": filename,
                    "designators": [c["designator"] for c in comps],
                },
            ))

        # Signal names as a separate chunk
        if labels:
            chunks.append(ParsedChunk(
                content=f"## Signals and Nets\n{', '.join(sorted(set(labels)))}",
                metadata={"type": "signals", "file": filename},
            ))

        return chunks

    def _extract_code_references(
        self, components: list[dict], labels: list[str]
    ) -> list[str]:
        """Extract references that might link to source code files."""
        refs = []
        # IC part numbers often correspond to driver file names
        for c in components:
            val = c.get("value", "")
            if re.match(r"STM32|ESP32|ATmega|PIC|nRF|MAX|LM|TI|AD[0-9]", val, re.IGNORECASE):
                refs.append(val.lower())
        # Signal names often appear in code as #define or function names
        for label in labels:
            if re.match(r"(SPI|I2C|UART|USART|CAN|USB|ADC|DAC|TIM|GPIO)", label):
                refs.append(label.lower())
        return list(set(refs))
