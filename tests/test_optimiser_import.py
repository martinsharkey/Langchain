"""
Test the GoldShark optimiser-XML ingester: a minimal MS-spreadsheet XML with two
parameter passes must map into the adjustment_ledger with backtest PF + trades.
Pure DB + parser logic, no MT5.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.experience_db import ExperienceDatabase
from src.learning.goldshark_optimiser_import import ingest_optimiser_xml

_XML = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office">
<DocumentProperties xmlns="urn:schemas-microsoft-com:office:office">
<Title>GoldShark2 XAUUSD,M1 2026.01.01-2026.05.21</Title></DocumentProperties>
<Worksheet ss:Name="Report"><Table>
<Row>
 <Cell><Data ss:Type="String">Pass</Data></Cell>
 <Cell><Data ss:Type="String">Result</Data></Cell>
 <Cell><Data ss:Type="String">Profit</Data></Cell>
 <Cell><Data ss:Type="String">Expected Payoff</Data></Cell>
 <Cell><Data ss:Type="String">Profit Factor</Data></Cell>
 <Cell><Data ss:Type="String">Recovery Factor</Data></Cell>
 <Cell><Data ss:Type="String">Sharpe Ratio</Data></Cell>
 <Cell><Data ss:Type="String">Custom</Data></Cell>
 <Cell><Data ss:Type="String">Equity DD %</Data></Cell>
 <Cell><Data ss:Type="String">Trades</Data></Cell>
 <Cell><Data ss:Type="String">InpOsMAFast</Data></Cell>
 <Cell><Data ss:Type="String">InpLongOsMAMin</Data></Cell>
</Row>
<Row>
 <Cell><Data ss:Type="Number">1</Data></Cell>
 <Cell><Data ss:Type="Number">1500</Data></Cell>
 <Cell><Data ss:Type="Number">1500</Data></Cell>
 <Cell><Data ss:Type="Number">2.5</Data></Cell>
 <Cell><Data ss:Type="Number">1.8</Data></Cell>
 <Cell><Data ss:Type="Number">3.0</Data></Cell>
 <Cell><Data ss:Type="Number">0.5</Data></Cell>
 <Cell><Data ss:Type="Number">0</Data></Cell>
 <Cell><Data ss:Type="Number">12</Data></Cell>
 <Cell><Data ss:Type="Number">80</Data></Cell>
 <Cell><Data ss:Type="Number">12</Data></Cell>
 <Cell><Data ss:Type="Number">1.2</Data></Cell>
</Row>
<Row>
 <Cell><Data ss:Type="Number">2</Data></Cell>
 <Cell><Data ss:Type="Number">-50</Data></Cell>
 <Cell><Data ss:Type="Number">-50</Data></Cell>
 <Cell><Data ss:Type="Number">-0.5</Data></Cell>
 <Cell><Data ss:Type="Number">0.4</Data></Cell>
 <Cell><Data ss:Type="Number">0.1</Data></Cell>
 <Cell><Data ss:Type="Number">-0.2</Data></Cell>
 <Cell><Data ss:Type="Number">0</Data></Cell>
 <Cell><Data ss:Type="Number">40</Data></Cell>
 <Cell><Data ss:Type="Number">30</Data></Cell>
 <Cell><Data ss:Type="Number">14</Data></Cell>
 <Cell><Data ss:Type="Number">0.5</Data></Cell>
</Row>
</Table></Worksheet></Workbook>
"""


def _db():
    return ExperienceDatabase(db_path=os.path.join(tempfile.mkdtemp(), "t.db"))


def _write_xml():
    p = os.path.join(tempfile.mkdtemp(), "ReportOptimizer-test.xml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_XML)
    return p


def test_optimiser_xml_ingests_passes():
    db = _db()
    r = ingest_optimiser_xml(_write_xml(), db, min_trades=10)
    assert r["symbol"] == "XAUUSD"
    assert r["parsed"] == 2, f"both passes (>=10 trades) should parse: {r}"
    # each pass maps InpOsMAFast->osma_fast and InpLongOsMAMin->osma_min_long
    hist = db.adjustment_history(symbol="XAUUSD", param="osma_min_long")
    assert len(hist) == 2
    # the winning pass (PF 1.8) is adopted; the losing pass (PF 0.4) is not
    pfs = sorted(h["backtest_pf"] for h in hist)
    assert pfs == [0.4, 1.8]


def test_optimiser_min_trades_filter():
    db = _db()
    # pass1 Trades=80, pass2 Trades=30; min_trades=50 keeps only pass1
    r = ingest_optimiser_xml(_write_xml(), db, min_trades=50)
    assert r["parsed"] == 1, f"min_trades filter should drop low-sample passes: {r}"
