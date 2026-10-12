"""Trimmed copies of real upstream response shapes."""

COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
}

SUBMISSIONS_AAPL = {
    "cik": "320193",
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "accessionNumber": ["0000320193-25-000079", "0000320193-25-000073", "0001140361-25-012345"],
            "filingDate": ["2025-10-31", "2025-10-30", "2025-04-03"],
            "reportDate": ["2025-09-27", "2025-10-30", "2025-04-01"],
            "form": ["10-K", "8-K", "4"],
            "items": ["", "2.02,9.01", ""],
            "primaryDocument": ["aapl-20250927.htm", "aapl-20251030.htm", "xslF345X05/wk-form4.xml"],
            "primaryDocDescription": ["10-K", "8-K", "FORM 4"],
        },
        "files": [],
    },
}

TIINGO_AAPL = [
    {"date": "2025-10-30T00:00:00.000Z", "adjOpen": 271.0, "adjHigh": 274.1, "adjLow": 268.5, "adjClose": 271.4, "adjVolume": 69886500},
    {"date": "2025-10-31T00:00:00.000Z", "adjOpen": 276.9, "adjHigh": 277.3, "adjLow": 269.2, "adjClose": 270.4, "adjVolume": 86167100},
]

YAHOO_AAPL = {
    "chart": {
        "result": [
            {
                "timestamp": [1761831000, 1761917400, 1762180200],
                "indicators": {
                    "quote": [
                        {
                            "open": [271.0, 276.9, None],
                            "high": [274.1, 277.3, None],
                            "low": [268.5, 269.2, None],
                            "close": [271.4, 270.4, None],
                            "volume": [69886500, 86167100, None],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}

YAHOO_NOT_FOUND = {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found"}}}
