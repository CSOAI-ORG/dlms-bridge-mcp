import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

def test_parse():
    p=server.parse_dlms("OBIS 1.8.0 reading 12345 kWh"); assert "energy import" in p.reading_type.lower(); assert p.is_consumption
def test_govern():
    assert any("GDPR" in f for f in server.govern_energy("1.8.0 100 kWh").frameworks)
