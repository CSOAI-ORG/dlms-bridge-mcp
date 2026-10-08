#!/usr/bin/env python3
"""
DLMS/COSEM Bridge MCP — CSOAI Layer-0 legacy-bridge family.
Bridge smart-meter / energy data (DLMS/COSEM OBIS) to ONE OS: parse → map → govern
(energy-data privacy · smart-meter security · NIS2 critical infra). Sibling of cobol-bridge-mcp.
Tools: parse_dlms · map_to_modern · govern_energy
"""
from mcp.server.mcpserver import MCPServer as FastMCP  # mcp 2.x: FastMCP renamed MCPServer
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import re

mcp = FastMCP("DLMS Bridge", instructions="Bridge DLMS/COSEM smart-meter data to ONE OS — parse, map, govern (energy privacy / IEC 62056 / NIS2).")

import hashlib as _hl, time as _t, json as _j, os as _os
_SIGIL_LOG = _os.environ.get("SIGIL_LOG", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "bridge_sigil.log"))
def _sigil(op, body):
    try:
        prev = ""
        if _os.path.exists(_SIGIL_LOG):
            with open(_SIGIL_LOG) as f:
                ls = f.readlines()
                if ls: prev = _j.loads(ls[-1]).get("digest", "")
        ts = int(_t.time()); dg = _hl.sha256(f"{op}|{ts}|{prev[:8]}|{body}".encode()).hexdigest()[:16]
        _os.makedirs(_os.path.dirname(_SIGIL_LOG), exist_ok=True)
        with open(_SIGIL_LOG, "a") as f: f.write(_j.dumps({"ts": ts, "op": op, "body": body, "prev_digest": prev, "digest": dg}) + "\n")
        return dg
    except Exception: return ""

# OBIS codes (C.D groups) → reading type
OBIS = {"1.8": "Active energy import (kWh)", "2.8": "Active energy export (kWh)",
        "1.7": "Instantaneous import power (kW)", "32.7": "Voltage L1", "31.7": "Current L1",
        "0.9.1": "Clock/time", "96.1": "Device ID"}


class DLMSParsed(BaseModel):
    obis: Optional[str] = None
    reading_type: str = "unknown"
    value: Optional[str] = None
    unit: Optional[str] = None
    is_consumption: bool = False


@mcp.tool()
def parse_dlms(data: str) -> DLMSParsed:
    """Parse a DLMS/COSEM reading (OBIS code + value); classify the meter reading."""
    obis = None
    m = re.search(r"\b(\d{1,3}(?:[-.]\d{1,3}){2,5})\b", data)
    if m: obis = m.group(1)
    rtype = "unknown"
    if obis:
        for k, v in OBIS.items():
            if ("." + k + ".") in ("." + obis.replace("-", ".") + ".") or obis.replace("-", ".").find("." + k + ".") >= 0 or k in obis.replace("-", "."):
                rtype = v; break
    val = re.search(r"(\d+\.?\d*)\s*(kWh|kW|V|A)\b", data)
    return DLMSParsed(obis=obis, reading_type=rtype,
                      value=val.group(1) if val else None, unit=val.group(2) if val else None,
                      is_consumption=("energy" in rtype.lower() or "power" in rtype.lower()))


@mcp.tool()
def map_to_modern(data: str) -> Dict[str, Any]:
    """Map a smart-meter reading to a modern energy-telemetry event for ONE OS."""
    p = parse_dlms(data)
    return {"source": "DLMS/COSEM", "obis": p.obis, "reading": p.reading_type,
            "value": p.value, "unit": p.unit, "kind": "consumption" if p.is_consumption else "status",
            "target": "modern energy telemetry"}


class Governance(BaseModel):
    risk_flags: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    attestable: bool = True
    note: str = ""


@mcp.tool()
def govern_energy(data: str) -> Governance:
    """Governance: energy-data privacy + smart-meter/grid security surface (attestable for CSOAI)."""
    _sigil("G", "dlms|govern_energy")
    p = parse_dlms(data)
    flags = []
    if p.is_consumption:
        flags.append("Consumption data is PERSONAL DATA — reveals occupancy/behaviour (GDPR); minimise granularity + consent")
    flags.append("Meter is OT/critical infra — secure association (HLS), encrypt (IEC 62056), no rogue commands")
    return Governance(risk_flags=flags,
                      frameworks=["IEC 62056 (DLMS/COSEM)", "NIS2 (energy / critical infra)", "GDPR (consumption = personal data)", "IEC 62443 (OT)"],
                      note="CSOAI governs the bridge: each meter reading/command SIGIL-signed = a verifiable, privacy-respecting energy trail.")


# ---------------------------------------------------------------------------
# MCP 2026-07-28 wire - header-add migration (2026-10-08)
# ---------------------------------------------------------------------------
# stdio carries no HTTP headers, so Mcp-Method / Mcp-Name are not applicable to
# this transport at runtime. When dlms-bridge-mcp is exposed over HTTP, route the ingress
# through the vendored mcp2026_shim (ShimASGI): it validates Mcp-Method /
# Mcp-Name, injects params._meta.protocolVersion = "2026-07-28" into every
# request, strips Mcp-Session-Id and answers legacy initialize / server-discover
# locally (the session header is never emitted - stateless wire).
# Refs: MIGRATION_NOTE.md, MCP_2026_WIRE_MIGRATION_PLAN_2026-10-07.md (3) + (4).
# ---------------------------------------------------------------------------


def http_app():
    """ASGI app for HTTP exposure, wrapped in the 2026-07-28 wire shim.

    stdio (``mcp.run()``) needs no shim; this is the enable path once the
    server is fronted by an HTTP transport. Bodies are buffered, so responses
    are requested in JSON mode rather than SSE.
    """
    from mcp2026_shim import WIRE_2026, ShimASGI, ShimConfig

    return ShimASGI(
        mcp.streamable_http_app(json_response=True),
        ShimConfig(
            protocol_version=WIRE_2026,
            server_info={"name": "dlms-bridge-mcp", "version": "0.1.0"},
        ),
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
